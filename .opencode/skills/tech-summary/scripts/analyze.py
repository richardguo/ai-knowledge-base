"""
Analyzer 核心脚本 - 读取 Collector 输出，调用 LLM 深度分析，生成结构化结果

流程:
  1. 从 knowledge/processed/ 查找 collector-*-status.json，筛选 status=completed
  2. 从状态文件的 raw_output_file 定位输入数据
  3. 并发调用 LLM 对每个项目进行深度分析（最大 5 并发）
  4. 合并去重、排序，输出到 knowledge/processed/analyzer-*.json
  5. 全程维护状态文件和检查点，支持断点续传
"""

import argparse
import json
import logging
import re
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

MAX_CONCURRENT = 5
MIN_CONCURRENT = 1
LLM_MAX_RETRIES = 5
CHECKPOINT_INTERVAL = 5
RATE_LIMIT_BACKOFF = [5, 10, 20, 40, 80]

GMT8 = timezone(timedelta(hours=8))

ANALYSIS_PROMPT = """请对以下项目进行深度分析，直接输出JSON，不要输出思考过程。

项目：{title} | 作者：{author} | 语言：{language} | 标签：{topics} | 热度：{popularity}({popularity_type})

描述：{description}

README：{readme}

已有摘要：{summary}

请直接输出如下JSON（不要markdown代码块，不要解释）：
{{"summary":"200-300字中文技术摘要","highlights":["亮点1","亮点2","亮点3"],"relevance_score":7,"tags":["tag-1","tag-2"],"category":"框架","maturity":"生产"}}

评分:9-10改变格局,7-8直接帮助,5-6值得了解,1-4可忽略
tags:1-3个英文小写连字符(如large-language-model,agent-framework,python)
category:框架/工具/论文/实践
maturity:实验/测试/生产"""


def _find_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".git").exists() or (parent / "AGENTS.md").exists():
            return parent
    return current.parent


PROJECT_ROOT = _find_project_root()


def _setup_logger(timestamp: str) -> logging.Logger:
    logger = logging.getLogger("analyzer")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.INFO)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    log_path = PROJECT_ROOT / "logs" / f"analyzer-{timestamp}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def _load_config() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        print(f"❌ 找不到 .env 文件: {env_path}", file=sys.stderr)
        sys.exit(1)

    load_dotenv(env_path)

    import os

    api_base = os.getenv("LLM_API_BASE", "")
    api_key = os.getenv("LLM_API_KEY", "")
    model_id = os.getenv("LLM_MODEL_ID", "")

    if not api_base or not api_key:
        print("❌ .env 中缺少 LLM_API_BASE 或 LLM_API_KEY", file=sys.stderr)
        sys.exit(1)

    return {"api_base": api_base, "api_key": api_key, "model_id": model_id}


def _now_gmt8() -> str:
    return datetime.now(GMT8).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _timestamp_gmt8() -> str:
    return datetime.now(GMT8).strftime("%Y-%m-%d-%H%M%S")


def _generate_task_id() -> str:
    return f"{_timestamp_gmt8()}-{uuid.uuid4().hex[:8]}"


def discover_input_files(
    processed_dir: Path,
    source_filter: str | None = None,
    logger: logging.Logger | None = None,
) -> list[tuple[Path, dict[str, Any]]]:
    """从 processed 目录查找 collector 状态文件，每种数据源只取最新的一条。

    Args:
        processed_dir: knowledge/processed/ 目录。
        source_filter: 数据源过滤，如 "search" 或 "trending"。None 表示全部。
        logger: 日志记录器。

    Returns:
        完成状态的 (输入文件路径, 状态数据) 元组列表，每种数据源最多一条。
    """
    if not processed_dir.exists():
        if logger:
            logger.error("knowledge/processed/ 目录不存在")
        return []

    by_source: dict[str, tuple[Path, dict[str, Any]]] = {}

    for status_file in sorted(
        processed_dir.glob("collector-*-status.json"),
        key=lambda p: p.name,
        reverse=True,
    ):
        try:
            data = json.loads(status_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            if logger:
                logger.warning(f"状态文件读取失败: {status_file} - {e}")
            continue

        if data.get("status") != "completed":
            if logger:
                logger.debug(f"跳过未完成状态: {status_file.name} (status={data.get('status')})")
            continue

        sources = data.get("sources", [])
        source_name = sources[0] if sources else ""
        if not source_name:
            continue

        if source_filter and source_filter not in source_name:
            continue

        if source_name in by_source:
            continue

        output_files = data.get("output_files", [])
        if not output_files:
            if logger:
                logger.warning(f"状态文件缺少 output_files: {status_file.name}")
            continue

        raw_path = Path(output_files[0])
        if not raw_path.is_absolute():
            raw_path = PROJECT_ROOT / raw_path

        if not raw_path.exists():
            if logger:
                logger.warning(f"原始文件不存在: {raw_path}")
            continue

        by_source[source_name] = (raw_path, data)
        if logger:
            logger.info(f"发现已完成数据源: {source_name} -> {raw_path.name}")

    return list(by_source.values())


def load_input_data(
    raw_path: Path, logger: logging.Logger | None = None
) -> dict[str, Any] | None:
    """加载并验证输入文件。

    Args:
        raw_path: 输入文件路径。
        logger: 日志记录器。

    Returns:
        验证通过返回数据字典，否则返回 None。
    """
    try:
        data = json.loads(raw_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        if logger:
            logger.error(f"JSON 解析失败: {raw_path} - {e}")
        return None

    if "items" not in data or not isinstance(data["items"], list):
        if logger:
            logger.error(f"缺少 items 数组: {raw_path}")
        return None

    if "source" not in data:
        if logger:
            logger.error(f"缺少 source 字段: {raw_path}")
        return None

    if not data["items"]:
        if logger:
            logger.warning(f"items 为空: {raw_path}")
        return None

    if "collected_at" not in data:
        data["collected_at"] = _now_gmt8()

    return data


class RateLimitController:
    """动态并发控制器：检测到限流时自动降低并发，成功后逐步恢复。"""

    def __init__(self, max_concurrent: int = MAX_CONCURRENT, min_concurrent: int = MIN_CONCURRENT):
        self.max_concurrent = max_concurrent
        self.min_concurrent = min_concurrent
        self._current_concurrent = max_concurrent
        self._lock = threading.Lock()
        self._success_streak = 0
        self._semaphore = threading.Semaphore(max_concurrent)

    def acquire(self, timeout: float | None = None) -> bool:
        """获取执行槽位。"""
        return self._semaphore.acquire(timeout=timeout)

    def release(self) -> None:
        """释放执行槽位。"""
        self._semaphore.release()

    def report_rate_limited(self) -> None:
        """报告遇到限流，降低并发。"""
        with self._lock:
            self._success_streak = 0
            if self._current_concurrent > self.min_concurrent:
                old_val = self._current_concurrent
                self._current_concurrent = max(
                    self.min_concurrent,
                    self._current_concurrent - 1
                )
                self._semaphore.acquire(blocking=False)
                print(
                    f"  ⚠️ 限流检测，降低并发: {old_val} → {self._current_concurrent}",
                    file=sys.stderr,
                )

    def report_success(self) -> None:
        """报告调用成功，连续成功后恢复并发。"""
        with self._lock:
            self._success_streak += 1
            if self._success_streak >= 3 and self._current_concurrent < self.max_concurrent:
                old_val = self._current_concurrent
                self._current_concurrent = min(
                    self.max_concurrent,
                    self._current_concurrent + 1
                )
                self._success_streak = 0
                self._semaphore.release()
                print(
                    f"  ✅ 连续成功，恢复并发: {old_val} → {self._current_concurrent}",
                    file=sys.stderr,
                )

    @property
    def current_concurrent(self) -> int:
        with self._lock:
            return self._current_concurrent

    def get_backoff_time(self, attempt: int) -> float:
        """获取限流退避时间。"""
        if attempt < len(RATE_LIMIT_BACKOFF):
            return RATE_LIMIT_BACKOFF[attempt]
        return RATE_LIMIT_BACKOFF[-1]


def call_llm(
    item: dict[str, Any],
    config: dict[str, str],
    rate_limiter: RateLimitController | None = None,
) -> dict[str, Any]:
    """调用 LLM 对单个项目进行深度分析。

    Args:
        item: 项目数据字典。
        config: LLM 配置。
        rate_limiter: 限流控制器。

    Returns:
        analysis 字典，失败时返回带默认值的字典。
    """
    if rate_limiter:
        rate_limiter.acquire()

    try:
        return _call_llm_internal(item, config, rate_limiter)
    finally:
        if rate_limiter:
            rate_limiter.release()


def _call_llm_internal(
    item: dict[str, Any],
    config: dict[str, str],
    rate_limiter: RateLimitController | None = None,
) -> dict[str, Any]:
    """call_llm 的内部实现。"""
    prompt = ANALYSIS_PROMPT.format(
        title=item.get("title", ""),
        author=item.get("author", ""),
        language=item.get("language", ""),
        topics=", ".join(item.get("topics", [])),
        popularity=item.get("popularity", 0),
        popularity_type=item.get("popularity_type", ""),
        description=item.get("description", "")[:500] or "无",
        readme=item.get("readme", "")[:3000] or "无",
        summary=item.get("summary", "无"),
    )

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config["model_id"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 3000,
        "temperature": 0.7,
    }
    url = config["api_base"].rstrip("/") + "/chat/completions"

    for attempt in range(LLM_MAX_RETRIES):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            if response.status_code == 200:
                result = response.json()
                choices = result.get("choices", [])
                if not choices:
                    print(
                        f"  ⚠️ HTTP 200 但 choices 为空 (attempt {attempt + 1}/{LLM_MAX_RETRIES})",
                        file=sys.stderr,
                    )
                    continue
                msg = choices[0].get("message", {})
                content = msg.get("content", "")
                if not content:
                    content = msg.get("reasoning_content", "")
                content = content.strip()
                if not content:
                    print(
                        f"  ⚠️ HTTP 200 但 content 为空 (attempt {attempt + 1}/{LLM_MAX_RETRIES})",
                        file=sys.stderr,
                    )
                    continue
                if rate_limiter:
                    rate_limiter.report_success()
                return _parse_llm_response(content)
            if response.status_code == 429:
                wait = rate_limiter.get_backoff_time(attempt) if rate_limiter else RATE_LIMIT_BACKOFF[min(attempt, len(RATE_LIMIT_BACKOFF) - 1)]
                if rate_limiter:
                    rate_limiter.report_rate_limited()
                print(
                    f"  ⏳ API 限流 (attempt {attempt + 1}/{LLM_MAX_RETRIES})，{wait}s 后重试",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            print(
                f"  ❌ LLM API 错误: HTTP {response.status_code} (attempt {attempt + 1}/{LLM_MAX_RETRIES})",
                file=sys.stderr,
            )
            continue
        except requests.exceptions.RequestException as e:
            wait = 2 ** attempt
            print(
                f"  ❌ 请求异常 ({attempt + 1}/{LLM_MAX_RETRIES}): {e}，{wait}s 后重试",
                file=sys.stderr,
            )
            if attempt < LLM_MAX_RETRIES - 1:
                time.sleep(wait)

    print(
        f"  ❌ {item.get('title', 'unknown')} 分析失败，{LLM_MAX_RETRIES} 次重试耗尽",
        file=sys.stderr,
    )
    return _default_analysis()


def _parse_llm_response(content: str) -> dict[str, Any]:
    """解析 LLM 返回的 JSON 分析结果。

    Args:
        content: LLM 返回的文本内容。

    Returns:
        解析后的 analysis 字典。
    """
    cleaned = content.strip()
    code_block_pattern = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```")
    code_blocks = code_block_pattern.findall(cleaned)
    if code_blocks:
        for block in reversed(code_blocks):
            try:
                parsed = json.loads(block)
                if "summary" in parsed or "relevance_score" in parsed:
                    return _validate_analysis(parsed)
            except json.JSONDecodeError:
                continue

    json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", cleaned)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            if "summary" in parsed or "relevance_score" in parsed:
                return _validate_analysis(parsed)
        except json.JSONDecodeError:
            pass

    greedy_match = re.search(r"\{[\s\S]*\}", cleaned)
    if greedy_match:
        try:
            parsed = json.loads(greedy_match.group())
            if "summary" in parsed or "relevance_score" in parsed:
                return _validate_analysis(parsed)
        except json.JSONDecodeError:
            pass

    print(f"  JSON 解析失败, content前300字: {cleaned[:300]}", file=sys.stderr)
    return _default_analysis()


def _validate_analysis(parsed: dict[str, Any]) -> dict[str, Any]:
    """校验并规范化分析结果。

    Args:
        parsed: 从 LLM 响应中解析的字典。

    Returns:
        规范化后的 analysis 字典。
    """

    summary = parsed.get("summary", "")
    if not summary or len(summary) < 50:
        return _default_analysis()

    highlights = parsed.get("highlights", [])
    if isinstance(highlights, str):
        highlights = [highlights]

    relevance_score = parsed.get("relevance_score", 5)
    try:
        relevance_score = max(1, min(10, int(relevance_score)))
    except (ValueError, TypeError):
        relevance_score = 5

    tags = parsed.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    tags = [t.lower().replace("_", "-").replace(" ", "-") for t in tags if t][:3]

    category = parsed.get("category", "工具")
    if category not in ("框架", "工具", "论文", "实践"):
        category = "工具"

    maturity = parsed.get("maturity", "测试")
    if maturity not in ("实验", "测试", "生产"):
        maturity = "测试"

    return {
        "summary": summary,
        "highlights": highlights[:5] if highlights else ["分析结果不完整"],
        "relevance_score": relevance_score,
        "tags": tags or ["uncategorized"],
        "category": category,
        "maturity": maturity,
    }


def _default_analysis() -> dict[str, Any]:
    return {
        "summary": "分析生成失败",
        "highlights": [],
        "relevance_score": 1,
        "tags": ["uncategorized"],
        "category": "工具",
        "maturity": "实验",
    }


def create_status_file(
    status_path: Path,
    task_id: str,
    input_files: list[str],
    output_file: str,
    items_total: int,
) -> dict[str, Any]:
    """创建分析状态文件。

    Args:
        status_path: 状态文件路径。
        task_id: 任务 ID。
        input_files: 输入文件路径列表。
        output_file: 输出文件路径。
        items_total: 总条目数。

    Returns:
        状态数据字典。
    """
    data: dict[str, Any] = {
        "agent": "analyzer",
        "task_id": task_id,
        "status": "started",
        "input_files": input_files,
        "output_file": output_file,
        "items_total": items_total,
        "items_processed": 0,
        "items_failed": 0,
        "items_deduplicated": 0,
        "error_count": 0,
        "start_time": _now_gmt8(),
        "end_time": None,
        "processed_urls": [],
    }
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def update_status(status_path: Path, data: dict[str, Any], **kwargs: Any) -> None:
    """更新状态文件。

    Args:
        status_path: 状态文件路径。
        data: 状态数据字典。
        **kwargs: 要更新的字段。
    """
    for key, value in kwargs.items():
        data[key] = value
    status_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def save_checkpoint(
    processed_dir: Path,
    timestamp: str,
    checkpoint_num: int,
    items_processed: int,
    next_index: int,
    processed_data: list[dict[str, Any]],
) -> Path:
    """保存检查点文件。

    Args:
        processed_dir: 输出目录。
        timestamp: 任务时间戳。
        checkpoint_num: 检查点编号。
        items_processed: 已处理条目数。
        next_index: 下一条目的索引。
        processed_data: 已分析的数据列表。

    Returns:
        检查点文件路径。
    """
    checkpoint_path = (
        processed_dir / f"analyzer-{timestamp}-checkpoint-{checkpoint_num}.json"
    )
    checkpoint_data = {
        "checkpoint_number": checkpoint_num,
        "items_processed": items_processed,
        "next_item_index": next_index,
        "processed_data": processed_data,
        "created_at": _now_gmt8(),
    }
    checkpoint_path.write_text(
        json.dumps(checkpoint_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return checkpoint_path


def find_latest_checkpoint(
    processed_dir: Path, timestamp: str
) -> dict[str, Any] | None:
    """查找最新的检查点文件。

    Args:
        processed_dir: 输出目录。
        timestamp: 任务时间戳。

    Returns:
        检查点数据字典，未找到返回 None。
    """
    checkpoints = sorted(
        processed_dir.glob(f"analyzer-{timestamp}-checkpoint-*.json"),
        key=lambda p: p.name,
    )
    if not checkpoints:
        return None
    try:
        return json.loads(checkpoints[-1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def cleanup_temp_files(processed_dir: Path, timestamp: str) -> None:
    """清理检查点和进度文件。

    Args:
        processed_dir: 输出目录。
        timestamp: 任务时间戳。
    """
    for pattern in [
        f"analyzer-{timestamp}-checkpoint-*.json",
        f"analyzer-{timestamp}-progress.json",
    ]:
        for f in processed_dir.glob(pattern):
            try:
                f.unlink()
            except OSError:
                pass


def merge_and_deduplicate(
    all_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """合并多数据源条目并去重，同 URL 不同来源保留双条目但复用分析结果。

    Args:
        all_items: 来自所有数据源的条目列表。

    Returns:
        合并去重后的条目列表，search 在前按 popularity 降序，trending 在后。
    """
    url_analysis: dict[str, dict[str, Any]] = {}
    search_items: list[dict[str, Any]] = []
    trending_items: list[dict[str, Any]] = []

    for item in all_items:
        url = item.get("url", "")
        source = item.get("source", "")

        if url in url_analysis and "analysis" in item:
            item["analysis"] = url_analysis[url]
        elif "analysis" in item:
            url_analysis[url] = item["analysis"]

        if source == "github-search":
            search_items.append(item)
        else:
            trending_items.append(item)

    search_items.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    return search_items + trending_items


def process_items(
    items: list[dict[str, Any]],
    config: dict[str, str],
    status_path: Path,
    status_data: dict[str, Any],
    processed_dir: Path,
    timestamp: str,
    logger: logging.Logger,
) -> list[dict[str, Any]]:
    """并发处理所有条目，带进度回显、检查点和断点续传。

    Args:
        items: 待分析条目列表。
        config: LLM 配置。
        status_path: 状态文件路径。
        status_data: 状态数据字典。
        processed_dir: 输出目录。
        timestamp: 任务时间戳。
        logger: 日志记录器。

    Returns:
        已分析的条目列表。
    """
    processed_urls: set[str] = set(status_data.get("processed_urls", []))
    results: dict[int, dict[str, Any]] = {}
    checkpoint_num = 0
    items_since_checkpoint = 0
    rate_limiter = RateLimitController()

    resume_checkpoint = find_latest_checkpoint(processed_dir, timestamp)
    if resume_checkpoint:
        for item_data in resume_checkpoint.get("processed_data", []):
            idx = _find_item_index(items, item_data.get("url", ""), item_data.get("source", ""))
            if idx >= 0 and idx not in results:
                results[idx] = item_data
                processed_urls.add(item_data["url"])
        logger.info(
            f"从检查点恢复: 已有 {len(results)} 条结果"
        )

    pending_indices = [i for i in range(len(items)) if i not in results]
    total = len(items)
    done_count = len(results)
    failed_count = status_data.get("items_failed", 0)

    if not pending_indices:
        logger.info("所有条目已处理完毕（来自检查点）")
        return [results[i] for i in sorted(results.keys())]

    logger.info(f"待分析: {len(pending_indices)}/{total} 条（初始并发 {MAX_CONCURRENT}）")

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        future_to_index = {}
        for i in pending_indices:
            future = executor.submit(call_llm, items[i], config, rate_limiter)
            future_to_index[future] = i

        for future in as_completed(future_to_index):
            i = future_to_index[future]
            item = items[i]
            title = item.get("title", "")
            source = item.get("source", "")
            popularity = item.get("popularity", 0)

            try:
                analysis = future.result()
            except Exception as e:
                logger.error(f"[{done_count + 1}/{total}] ❌ {title}: {e}")
                analysis = _default_analysis()
                failed_count += 1

            is_dedup = item.get("url", "") in processed_urls
            processed_urls.add(item.get("url", ""))

            result_item = {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "source": source,
                "popularity": item.get("popularity", 0),
                "popularity_type": item.get("popularity_type", ""),
                "author": item.get("author", ""),
                "created_at": item.get("created_at", ""),
                "updated_at": item.get("updated_at", ""),
                "language": item.get("language", ""),
                "topics": item.get("topics", []),
                "description": item.get("description", ""),
                "readme": item.get("readme", ""),
                "summary": analysis.get("summary", ""),
                "collected_at": item.get("collected_at", ""),
                "analysis": analysis,
            }
            results[i] = result_item
            done_count += 1
            items_since_checkpoint += 1

            score = analysis.get("relevance_score", "?")
            cat = analysis.get("category", "?")
            tags = ",".join(analysis.get("tags", []))

            if is_dedup:
                print(
                    f"[{done_count}/{total}] ⏭️ {title} (已分析，复用结果)",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[{done_count}/{total}] ✅ {title} - 评分:{score} 分类:{cat} 标签:{tags}",
                    file=sys.stderr,
                )

            update_status(
                status_path,
                status_data,
                items_processed=done_count,
                items_failed=failed_count,
                processed_urls=list(processed_urls),
            )

            if items_since_checkpoint >= CHECKPOINT_INTERVAL:
                checkpoint_num += 1
                save_checkpoint(
                    processed_dir,
                    timestamp,
                    checkpoint_num,
                    done_count,
                    i + 1,
                    [results[idx] for idx in sorted(results.keys())],
                )
                items_since_checkpoint = 0

    return [results[i] for i in sorted(results.keys())]


def _find_item_index(
    items: list[dict[str, Any]], url: str, source: str
) -> int:
    """在条目列表中查找匹配项的索引。

    Args:
        items: 条目列表。
        url: 项目 URL。
        source: 数据来源。

    Returns:
        匹配的索引，未找到返回 -1。
    """
    for i, item in enumerate(items):
        if item.get("url") == url and item.get("source") == source:
            return i
    return -1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyzer - 深度分析 Collector 采集的 AI 技术项目"
    )
    parser.add_argument(
        "--input",
        "-i",
        nargs="+",
        help="输入文件路径（可传 1-2 个 raw 文件），不传则自动发现",
    )
    parser.add_argument(
        "--source",
        "-s",
        choices=["search", "trending"],
        help="仅处理指定数据源（自动发现模式下使用）",
    )
    parser.add_argument(
        "--resume_run",
        action="store_true",
        help="从断点续传",
    )
    args = parser.parse_args()

    config = _load_config()
    timestamp = _timestamp_gmt8()
    logger = _setup_logger(timestamp)
    processed_dir = PROJECT_ROOT / "knowledge" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"🚀 Analyzer 启动 (timestamp={timestamp})")
    logger.info(f"🔧 LLM: base={config['api_base']}, model={config['model_id']}")

    if args.input:
        input_files = [(Path(p), {}) for p in args.input]
        for p, _ in input_files:
            if not p.is_absolute():
                p = PROJECT_ROOT / p
            if not p.exists():
                logger.error(f"❌ 输入文件不存在: {p}")
                sys.exit(1)
    else:
        input_files = discover_input_files(processed_dir, args.source, logger)
        if not input_files:
            logger.error(
                "❌ 找不到已完成的 Collector 数据，请先运行 Collector 采集数据"
            )
            sys.exit(1)

    logger.info(f"📋 发现 {len(input_files)} 个数据源")

    all_items: list[dict[str, Any]] = []
    input_file_paths: list[str] = []
    collected_ats: dict[str, str] = {}

    for raw_path, status_data in input_files:
        data = load_input_data(raw_path, logger)
        if data is None:
            logger.warning(f"跳过无效输入: {raw_path}")
            continue

        items = data["items"]
        source = data.get("source", "unknown")
        collected_at = data.get("collected_at", _now_gmt8())
        logger.info(f"📋 {source}: {len(items)} 条")

        for item in items:
            item["source"] = source
            item["collected_at"] = collected_at
        all_items.extend(items)
        input_file_paths.append(str(raw_path))
        collected_ats[source] = collected_at

    if not all_items:
        logger.error("❌ 无有效数据可分析")
        sys.exit(1)

    output_path = processed_dir / f"analyzer-{timestamp}.json"
    status_path = processed_dir / f"analyzer-{timestamp}-status.json"

    existing_status = None
    existing_status_data = None
    if args.resume_run:
        status_files = sorted(
            processed_dir.glob("analyzer-*-status.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for sf in status_files:
            try:
                sd = json.loads(sf.read_text(encoding="utf-8"))
                if sd.get("status") in ("started", "running"):
                    existing_status = sf
                    existing_status_data = sd
                    timestamp = re.search(
                        r"analyzer-(\d{4}-\d{2}-\d{2}-\d{6})", sf.name
                    ).group(1)
                    status_path = sf
                    output_path = processed_dir / f"analyzer-{timestamp}.json"
                    break
            except (json.JSONDecodeError, OSError, AttributeError):
                continue

    if existing_status_data:
        status_data = existing_status_data
        logger.info(f"📂 续传任务: {timestamp}")
    else:
        status_data = create_status_file(
            status_path,
            _generate_task_id(),
            input_file_paths,
            str(output_path),
            len(all_items),
        )

    update_status(status_path, status_data, status="running")

    print(
        f"📋 发现 {len(input_files)} 个数据源，共 {len(all_items)} 条待分析",
        file=sys.stderr,
    )

    try:
        analyzed_items = process_items(
            all_items,
            config,
            status_path,
            status_data,
            processed_dir,
            timestamp,
            logger,
        )

        merged_items = merge_and_deduplicate(analyzed_items)

        output_data = {
            "analyzed_at": _now_gmt8(),
            "version": "1.0",
            "input_files": input_file_paths,
            "collected_ats": collected_ats,
            "items": merged_items,
        }
        output_path.write_text(
            json.dumps(output_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        failed = status_data.get("items_failed", 0)
        dedup = status_data.get("items_deduplicated", 0)
        success = len(merged_items) - failed

        update_status(
            status_path,
            status_data,
            status="completed",
            end_time=_now_gmt8(),
        )

        cleanup_temp_files(processed_dir, timestamp)

        print(
            f"🎉 全部分析完成: {success}/{len(merged_items)} 成功, "
            f"{failed} 失败 → 输出: {output_path}",
            file=sys.stderr,
        )

        print(str(output_path))

    except Exception as e:
        logger.error(f"❌ 分析任务失败: {e}")
        update_status(
            status_path,
            status_data,
            status="failed",
            error_count=status_data.get("error_count", 0) + 1,
        )
        failed_path = processed_dir / f"analyzer-{timestamp}-failed.json"
        failed_data = {**status_data, "errors": [str(e)]}
        failed_path.write_text(
            json.dumps(failed_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

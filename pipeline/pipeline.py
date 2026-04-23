"""四步知识库自动化流水线.

采集 -> 分析 -> 整理 -> 保存

Usage:
    python pipeline/pipeline.py --sources github,rss --limit 20
    python pipeline/pipeline.py --sources github --limit 5
    python pipeline/pipeline.py --sources rss --limit 10
    python pipeline/pipeline.py --sources github --limit 5 --dry-run
    python pipeline/pipeline.py --verbose
"""

import argparse
import asyncio
import base64
import json
import logging
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from model_client import LLMError, chat_with_retry, get_default_provider

GMT8 = timezone(timedelta(hours=8))

DEFAULT_KEYWORDS = [
    "AI",
    "LLM",
    "agent",
    "large language model",
    "RAG",
    "machine learning",
]

RSS_FEEDS = [
    "https://hnrss.org/newest?q=AI+OR+LLM+OR+agent&points=50",
]

ANALYSIS_PROMPT = """请对以下内容进行深度分析，直接输出JSON，不要输出思考过程。

标题：{title}
来源：{source}
描述：{description}

请直接输出如下JSON（不要markdown代码块，不要解释）：
{{"summary":"200-300字中文技术摘要","highlights":["亮点1","亮点2","亮点3"],"relevance_score":7,"tags":["tag-1","tag-2"],"category":"框架","maturity":"生产"}}

评分:9-10改变格局,7-8直接帮助,5-6值得了解,1-4可忽略
tags:1-3个英文小写连字符(如large-language-model,agent-framework)
category:框架/工具/论文/实践
maturity:实验/测试/生产"""


def setup_logging(verbose: bool = False) -> logging.Logger:
    """配置日志记录器.

    Args:
        verbose: 是否启用详细日志.

    Returns:
        配置好的 Logger 实例.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stderr,
    )
    return logging.getLogger("pipeline")


def find_project_root() -> Path:
    """查找项目根目录.

    Returns:
        包含 .git 或 AGENTS.md 的目录路径.
    """
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".git").exists() or (parent / "AGENTS.md").exists():
            return parent
    return current.parent


def now_gmt8() -> str:
    """生成当前 GMT+8 的 ISO 8601 时间字符串."""
    return datetime.now(GMT8).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def timestamp_gmt8() -> str:
    """生成当前 GMT+8 的时间戳字符串."""
    return datetime.now(GMT8).strftime("%Y-%m-%d-%H%M%S")


def generate_slug(title: str) -> str:
    """从标题生成 URL 友好的 slug.

    Args:
        title: 项目标题.

    Returns:
        URL 友好的 slug.
    """
    title_lower = title.lower()
    title_clean = re.sub(r"[^a-z0-9-]", "-", title_lower)
    title_clean = re.sub(r"-+", "-", title_clean)
    return title_clean.strip("-")


class Step1Collector:
    """采集步骤 - 从 GitHub Search API 和 RSS 源采集 AI 相关内容."""

    def __init__(self, config: dict[str, str], limit: int, logger: logging.Logger):
        """初始化采集器.

        Args:
            config: 配置字典，包含 GITHUB_TOKEN 等.
            limit: 每个数据源的采集数量限制.
            logger: 日志记录器.
        """
        self.config = config
        self.limit = limit
        self.logger = logger
        self.github_token = config.get("github_token", "")

    def run(self, sources: list[str], dry_run: bool = False) -> list[dict[str, Any]]:
        """执行采集.

        Args:
            sources: 数据源列表，如 ["github", "rss"].
            dry_run: 是否为干跑模式.

        Returns:
            采集到的条目列表.
        """
        items: list[dict[str, Any]] = []

        if "github" in sources:
            github_items = self._collect_github(dry_run)
            items.extend(github_items)

        if "rss" in sources:
            rss_items = self._collect_rss(dry_run)
            items.extend(rss_items)

        return items

    def _collect_github(self, dry_run: bool = False) -> list[dict[str, Any]]:
        """从 GitHub Search API 采集.

        Args:
            dry_run: 是否为干跑模式.

        Returns:
            采集到的 GitHub 仓库列表.
        """
        if dry_run:
            self.logger.info("[Step1] GitHub 干跑模式，跳过采集")
            return []

        if not self.github_token:
            self.logger.error("[Step1] 缺少 GITHUB_TOKEN，跳过 GitHub 采集")
            return []

        self.logger.info(f"[Step1] 开始 GitHub 采集，限制 {self.limit} 条")

        now = datetime.now(GMT8)
        pushed_after = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        query = f"{' OR '.join(DEFAULT_KEYWORDS[:3])} pushed:>{pushed_after}"

        url = "https://api.github.com/search/repositories"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": min(self.limit, 100),
        }

        try:
            with httpx.Client(timeout=30) as client:
                response = client.get(url, headers=headers, params=params)

            if response.status_code != 200:
                self.logger.error(f"[Step1] GitHub API 错误: {response.status_code}")
                return []

            data = response.json()
            raw_items = data.get("items", [])
            self.logger.info(f"[Step1] GitHub 返回 {len(raw_items)} 条")

            items: list[dict[str, Any]] = []
            for item in raw_items[: self.limit]:
                owner = item.get("owner", {}).get("login", "")
                repo_name = item.get("name", "")

                readme = self._fetch_readme(
                    owner, repo_name, client if "client" in dir() else None
                )

                processed = {
                    "title": repo_name,
                    "url": item.get("html_url", ""),
                    "source": "github-search",
                    "popularity": item.get("stargazers_count", 0),
                    "popularity_type": "total_stars",
                    "author": owner,
                    "created_at": self._to_gmt8(item.get("created_at", "")),
                    "updated_at": self._to_gmt8(item.get("updated_at", "")),
                    "language": item.get("language") or "N/A",
                    "topics": item.get("topics", []),
                    "description": item.get("description") or "",
                    "readme": readme,
                    "summary": "",
                    "collected_at": now_gmt8(),
                }
                items.append(processed)

            return items

        except Exception as e:
            self.logger.error(f"[Step1] GitHub 采集异常: {e}")
            return []

    def _fetch_readme(
        self, owner: str, repo: str, client: httpx.Client | None = None
    ) -> str:
        """获取 README 内容.

        Args:
            owner: 仓库所有者.
            repo: 仓库名称.
            client: httpx 客户端.

        Returns:
            README 内容字符串，截断到 5000 字符.
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/readme"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        try:
            if client:
                response = client.get(url, headers=headers)
            else:
                with httpx.Client(timeout=30) as c:
                    response = c.get(url, headers=headers)

            if response.status_code != 200:
                return ""

            data = response.json()
            content = data.get("content", "")
            content = content.replace("\n", "")
            decoded = base64.b64decode(content).decode("utf-8", errors="replace")
            return decoded[:5000]

        except Exception:
            return ""

    def _collect_rss(self, dry_run: bool = False) -> list[dict[str, Any]]:
        """从 RSS 源采集.

        Args:
            dry_run: 是否为干跑模式.

        Returns:
            采集到的 RSS 条目列表.
        """
        if dry_run:
            self.logger.info("[Step1] RSS 干跑模式，跳过采集")
            return []

        self.logger.info(f"[Step1] 开始 RSS 采集，限制 {self.limit} 条")

        items: list[dict[str, Any]] = []
        collected_count = 0

        for feed_url in RSS_FEEDS:
            if collected_count >= self.limit:
                break

            try:
                with httpx.Client(timeout=30) as client:
                    response = client.get(feed_url)

                if response.status_code != 200:
                    self.logger.warning(f"[Step1] RSS 获取失败: {feed_url}")
                    continue

                feed_items = self._parse_rss(response.text)
                self.logger.info(f"[Step1] RSS {feed_url} 返回 {len(feed_items)} 条")

                for item in feed_items:
                    if collected_count >= self.limit:
                        break

                    processed = {
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "source": "rss",
                        "popularity": 0,
                        "popularity_type": "none",
                        "author": item.get("author", ""),
                        "created_at": now_gmt8(),
                        "updated_at": now_gmt8(),
                        "language": "N/A",
                        "topics": [],
                        "description": item.get("description", ""),
                        "readme": "",
                        "summary": "",
                        "collected_at": now_gmt8(),
                    }
                    items.append(processed)
                    collected_count += 1

            except Exception as e:
                self.logger.error(f"[Step1] RSS 采集异常: {feed_url} - {e}")
                continue

        return items

    def _parse_rss(self, content: str) -> list[dict[str, str]]:
        """解析 RSS 内容（简易正则解析）.

        Args:
            content: RSS XML 内容.

        Returns:
            解析后的条目列表.
        """
        items: list[dict[str, str]] = []

        item_pattern = re.compile(r"<item>(.*?)</item>", re.DOTALL)
        title_pattern = re.compile(r"<title><!\[CDATA\[(.*?)\]\]></title>", re.DOTALL)
        title_pattern2 = re.compile(r"<title>(.*?)</title>", re.DOTALL)
        link_pattern = re.compile(r"<link>(.*?)</link>", re.DOTALL)
        desc_pattern = re.compile(
            r"<description><!\[CDATA\[(.*?)\]\]></description>", re.DOTALL
        )
        desc_pattern2 = re.compile(r"<description>(.*?)</description>", re.DOTALL)

        for match in item_pattern.finditer(content):
            item_content = match.group(1)

            title_match = title_pattern.search(item_content) or title_pattern2.search(
                item_content
            )
            title = title_match.group(1).strip() if title_match else ""

            link_match = link_pattern.search(item_content)
            link = link_match.group(1).strip() if link_match else ""

            desc_match = desc_pattern.search(item_content) or desc_pattern2.search(
                item_content
            )
            description = desc_match.group(1).strip() if desc_match else ""

            if title and link:
                items.append(
                    {
                        "title": title,
                        "link": link,
                        "description": description,
                        "author": "",
                    }
                )

        return items

    def _to_gmt8(self, utc_str: str) -> str:
        """UTC ISO 8601 时间字符串转 GMT+8 +08:00 格式.

        Args:
            utc_str: UTC 时间字符串.

        Returns:
            GMT+8 时间字符串.
        """
        if not utc_str:
            return now_gmt8()

        try:
            utc_str = utc_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(utc_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_gmt8 = dt.astimezone(GMT8)
            return dt_gmt8.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        except ValueError:
            return now_gmt8()


class Step2Analyzer:
    """分析步骤 - 调用 LLM 对每条内容进行摘要/评分/标签分析."""

    MAX_CONCURRENT = 5

    def __init__(self, config: dict[str, str], logger: logging.Logger):
        """初始化分析器.

        Args:
            config: 配置字典，包含 LLM 配置.
            logger: 日志记录器.
        """
        self.config = config
        self.logger = logger
        self.provider = None

        try:
            self.provider = get_default_provider()
        except LLMError as e:
            self.logger.error(f"[Step2] LLM Provider 初始化失败: {e}")

    def run(
        self, items: list[dict[str, Any]], dry_run: bool = False
    ) -> list[dict[str, Any]]:
        """执行分析.

        Args:
            items: 待分析的条目列表.
            dry_run: 是否为干跑模式.

        Returns:
            分析后的条目列表.
        """
        if dry_run:
            self.logger.info("[Step2] 干跑模式，跳过分析")
            for item in items:
                item["analysis"] = self._default_analysis()
            return items

        if not self.provider:
            self.logger.error("[Step2] LLM Provider 未初始化，使用默认分析")
            for item in items:
                item["analysis"] = self._default_analysis()
            return items

        self.logger.info(
            f"[Step2] 开始分析 {len(items)} 条内容（并发 {self.MAX_CONCURRENT}）"
        )

        results: dict[int, dict[str, Any]] = {}
        total = len(items)

        with ThreadPoolExecutor(max_workers=self.MAX_CONCURRENT) as executor:
            future_to_index = {
                executor.submit(self._analyze_item, item): i
                for i, item in enumerate(items)
            }

            for future in as_completed(future_to_index):
                i = future_to_index[future]
                item = items[i]
                title = item.get("title", "")

                try:
                    analysis = future.result()
                except Exception as e:
                    self.logger.error(
                        f"[Step2] 分析失败 [{i + 1}/{total}]: {title} - {e}"
                    )
                    analysis = self._default_analysis()

                item["analysis"] = analysis
                results[i] = item

                score = analysis.get("relevance_score", "?")
                tags = ",".join(analysis.get("tags", []))
                print(
                    f"[Step2] [{i + 1}/{total}] ✅ {title[:30]} - 评分:{score} 标签:{tags}",
                    file=sys.stderr,
                )

        return [results[i] for i in sorted(results.keys())]

    def _analyze_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """分析单个条目.

        Args:
            item: 待分析的条目.

        Returns:
            分析结果字典.
        """
        prompt = ANALYSIS_PROMPT.format(
            title=item.get("title", ""),
            source=item.get("source", ""),
            description=(item.get("description", "") or item.get("readme", ""))[:1000],
        )

        try:
            response = chat_with_retry(
                provider=self.provider,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.7,
            )
            return self._parse_analysis(response.content)
        except LLMError as e:
            self.logger.warning(f"[Step2] LLM 调用失败: {e}")
            return self._default_analysis()

    def _parse_analysis(self, content: str) -> dict[str, Any]:
        """解析 LLM 返回的分析结果.

        Args:
            content: LLM 返回的文本内容.

        Returns:
            解析后的分析字典.
        """
        cleaned = content.strip()

        code_block_pattern = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```")
        code_blocks = code_block_pattern.findall(cleaned)
        if code_blocks:
            for block in reversed(code_blocks):
                try:
                    parsed = json.loads(block)
                    if "summary" in parsed or "relevance_score" in parsed:
                        return self._validate_analysis(parsed)
                except json.JSONDecodeError:
                    continue

        json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", cleaned)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                if "summary" in parsed or "relevance_score" in parsed:
                    return self._validate_analysis(parsed)
            except json.JSONDecodeError:
                pass

        return self._default_analysis()

    def _validate_analysis(self, parsed: dict[str, Any]) -> dict[str, Any]:
        """校验并规范化分析结果.

        Args:
            parsed: 从 LLM 响应中解析的字典.

        Returns:
            规范化后的分析字典.
        """
        summary = parsed.get("summary", "")
        if not summary or len(summary) < 50:
            return self._default_analysis()

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

    def _default_analysis(self) -> dict[str, Any]:
        """返回默认分析结果."""
        return {
            "summary": "分析生成失败",
            "highlights": [],
            "relevance_score": 1,
            "tags": ["uncategorized"],
            "category": "工具",
            "maturity": "实验",
        }


class Step3Organizer:
    """整理步骤 - 去重 + 格式标准化 + 校验."""

    def __init__(self, logger: logging.Logger):
        """初始化整理器.

        Args:
            logger: 日志记录器.
        """
        self.logger = logger

    def run(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """执行整理.

        Args:
            items: 待整理的条目列表.

        Returns:
            整理后的条目列表.
        """
        self.logger.info(f"[Step3] 开始整理 {len(items)} 条内容")

        deduplicated = self._deduplicate(items)
        self.logger.info(f"[Step3] 去重后 {len(deduplicated)} 条")

        filtered = self._filter_by_score(deduplicated)
        self.logger.info(f"[Step3] 过滤后 {len(filtered)} 条（评分>=6）")

        standardized = self._standardize(filtered)

        return standardized

    def _deduplicate(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """按 URL 去重.

        Args:
            items: 待去重的条目列表.

        Returns:
            去重后的条目列表.
        """
        seen_urls: set[str] = set()
        result: list[dict[str, Any]] = []

        for item in items:
            url = item.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                result.append(item)

        return result

    def _filter_by_score(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """过滤评分低于 6 的条目.

        Args:
            items: 待过滤的条目列表.

        Returns:
            过滤后的条目列表.
        """
        return [
            item
            for item in items
            if item.get("analysis", {}).get("relevance_score", 0) >= 6
        ]

    def _standardize(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """标准化格式.

        Args:
            items: 待标准化的条目列表.

        Returns:
            标准化后的条目列表.
        """
        result: list[dict[str, Any]] = []

        for item in items:
            analysis = item.get("analysis", {})

            standardized = {
                "id": str(uuid.uuid4()),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "source": item.get("source", ""),
                "collected_at": item.get("collected_at", now_gmt8()),
                "processed_at": now_gmt8(),
                "summary": analysis.get("summary", ""),
                "highlights": analysis.get("highlights", []),
                "relevance_score": analysis.get("relevance_score", 0),
                "tags": analysis.get("tags", []),
                "category": analysis.get("category", "工具"),
                "maturity": analysis.get("maturity", "测试"),
            }

            result.append(standardized)

        return result


class Step4Saver:
    """保存步骤 - 将文章保存为独立 JSON 文件."""

    def __init__(self, output_dir: Path, logger: logging.Logger):
        """初始化保存器.

        Args:
            output_dir: 输出目录.
            logger: 日志记录器.
        """
        self.output_dir = output_dir
        self.logger = logger

    def run(self, items: list[dict[str, Any]], dry_run: bool = False) -> list[Path]:
        """执行保存.

        Args:
            items: 待保存的条目列表.
            dry_run: 是否为干跑模式.

        Returns:
            保存的文件路径列表.
        """
        if dry_run:
            self.logger.info("[Step4] 干跑模式，跳过保存")
            return []

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"[Step4] 开始保存 {len(items)} 条内容到 {self.output_dir}")

        saved_paths: list[Path] = []

        for item in items:
            path = self._save_item(item)
            if path:
                saved_paths.append(path)

        self._update_index(items)

        self.logger.info(f"[Step4] 保存完成，共 {len(saved_paths)} 个文件")
        return saved_paths

    def _save_item(self, item: dict[str, Any]) -> Path | None:
        """保存单个条目.

        Args:
            item: 待保存的条目.

        Returns:
            保存的文件路径.
        """
        try:
            title = item.get("title", "")
            slug = generate_slug(title)
            collected_date = item.get("collected_at", "")[:10]
            filename = f"{collected_date}-{slug}.json"
            path = self.output_dir / filename

            path.write_text(
                json.dumps(item, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            return path

        except Exception as e:
            self.logger.error(f"[Step4] 保存失败: {item.get('title', '')} - {e}")
            return None

    def _update_index(self, items: list[dict[str, Any]]) -> None:
        """更新索引文件.

        Args:
            items: 所有已保存的条目列表.
        """
        index_path = self.output_dir / "index.json"

        existing_index: dict[str, Any] = {
            "version": "1.0",
            "last_updated": "",
            "total_entries": 0,
            "entries": [],
        }

        if index_path.exists():
            try:
                existing_index = json.loads(index_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        existing_urls: set[str] = {
            entry.get("url", "") for entry in existing_index.get("entries", [])
        }

        for item in items:
            url = item.get("url", "")
            if url in existing_urls:
                continue

            entry = {
                "id": item["id"],
                "title": item["title"],
                "source": item["source"],
                "category": item["category"],
                "relevance_score": item["relevance_score"],
                "url": url,
                "file_path": str(
                    self.output_dir
                    / f"{item['collected_at'][:10]}-{generate_slug(item['title'])}.json"
                ),
                "tags": item["tags"],
                "collected_at": item["collected_at"],
            }
            existing_index["entries"].append(entry)

        existing_index["last_updated"] = now_gmt8()
        existing_index["total_entries"] = len(existing_index["entries"])

        index_path.write_text(
            json.dumps(existing_index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def load_config(project_root: Path) -> dict[str, str]:
    """加载环境配置.

    Args:
        project_root: 项目根目录.

    Returns:
        配置字典.
    """
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    import os

    return {
        "github_token": os.getenv("GITHUB_TOKEN", ""),
        "llm_api_base": os.getenv("LLM_API_BASE", ""),
        "llm_api_key": os.getenv("LLM_API_KEY", ""),
        "llm_model_id": os.getenv("LLM_MODEL_ID", ""),
    }


def parse_args() -> argparse.Namespace:
    """解析命令行参数.

    Returns:
        解析后的参数对象.
    """
    parser = argparse.ArgumentParser(
        description="四步知识库自动化流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--sources",
        type=str,
        default="github",
        help="数据源，逗号分隔，如 github,rss（默认: github）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="每个数据源的采集数量限制（默认: 20）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="干跑模式，不实际采集和分析",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="详细日志",
    )
    parser.add_argument(
        "--raw-dir",
        type=str,
        default="knowledge/raw",
        help="原始数据目录（默认: knowledge/raw）",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="knowledge/articles",
        help="输出目录（默认: knowledge/articles）",
    )

    return parser.parse_args()


def main() -> int:
    """主函数.

    Returns:
        退出码.
    """
    args = parse_args()

    logger = setup_logging(args.verbose)

    project_root = find_project_root()
    config = load_config(project_root)

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]

    logger.info("=" * 60)
    logger.info("知识库自动化流水线启动")
    logger.info(f"数据源: {sources}")
    logger.info(f"限制: {args.limit}")
    logger.info(f"干跑模式: {args.dry_run}")
    logger.info("=" * 60)

    raw_dir = project_root / args.raw_dir
    output_dir = project_root / args.output_dir

    raw_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n[Step 1/4] 采集", file=sys.stderr)
    collector = Step1Collector(config, args.limit, logger)
    items = collector.run(sources, args.dry_run)

    if not items:
        logger.warning("未采集到任何内容")
        return 0

    raw_path = raw_dir / f"pipeline-{timestamp_gmt8()}.json"
    raw_data = {
        "collected_at": now_gmt8(),
        "source": ",".join(sources),
        "version": "1.0",
        "items": items,
    }
    raw_path.write_text(
        json.dumps(raw_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"[Step1] 采集完成，保存到 {raw_path}")

    print("\n[Step 2/4] 分析", file=sys.stderr)
    analyzer = Step2Analyzer(config, logger)
    analyzed_items = analyzer.run(items, args.dry_run)

    print("\n[Step 3/4] 整理", file=sys.stderr)
    organizer = Step3Organizer(logger)
    organized_items = organizer.run(analyzed_items)

    print("\n[Step 4/4] 保存", file=sys.stderr)
    saver = Step4Saver(output_dir, logger)
    saved_paths = saver.run(organized_items, args.dry_run)

    print("\n" + "=" * 60, file=sys.stderr)
    print(f"流水线完成", file=sys.stderr)
    print(f"  采集: {len(items)} 条", file=sys.stderr)
    print(f"  分析: {len(analyzed_items)} 条", file=sys.stderr)
    print(f"  整理: {len(organized_items)} 条", file=sys.stderr)
    print(f"  保存: {len(saved_paths)} 条", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

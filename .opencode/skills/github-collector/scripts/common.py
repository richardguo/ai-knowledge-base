"""
GitHub Collector 公共模块 - 提供共享的工具函数和配置
"""

import base64
import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

TARGET_TOPICS = {
    "ai", "llm", "agent", "ml", "machine-learning", "large-language-model",
    "generative-ai", "deeplearning", "deep-learning", "transformer",
    "rlhf", "reinforcement-learning", "nlp", "neural-network",
    "artificial-intelligence", "language-model", "openai", "anthropic",
    "claude", "chatgpt", "gpt", "huggingface", "transformers",
}

EXCLUDE_PATTERNS = {
    "awesome-", "curated list", "book", "course", "roadmap",
    "interview", "cheatsheet",
}

DESC_KEYWORDS = [
    "ai", "llm", "agent", "machine learning",
    "deep learning", "nlp", "language model", "ml",
]

GMT8 = timezone(timedelta(hours=8))


def setup_logger(name: str, log_dir: str, timestamp: str) -> logging.Logger:
    """创建同时输出到 stderr 和日志文件的 logger。

    Args:
        name: logger 名称。
        log_dir: 日志文件目录。
        timestamp: 时间戳字符串，用于日志文件命名。

    Returns:
        配置好的 Logger 实例。
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z"
    )

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.INFO)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    log_path = Path(log_dir) / f"collector-{timestamp}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def find_project_root() -> Path:
    """查找项目根目录。

    Returns:
        包含 .git 或 AGENTS.md 的目录路径。
    """
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".git").exists() or (parent / "AGENTS.md").exists():
            return parent
    return current.parent


def load_env() -> dict[str, str]:
    """从项目根目录 .env 读取配置。

    Returns:
        包含 GITHUB_TOKEN 和 LLM 配置的字典。

    Raises:
        SystemExit: 找不到 .env 或缺少必要配置时退出。
    """
    project_root = find_project_root()
    env_path = project_root / ".env"

    if not env_path.exists():
        print(f"错误: 找不到 .env 文件: {env_path}", file=sys.stderr)
        sys.exit(1)

    load_dotenv(env_path)

    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        print("错误: .env 中缺少 GITHUB_TOKEN", file=sys.stderr)
        sys.exit(1)

    config = {
        "github_token": github_token,
        "llm_api_base": os.getenv("LLM_API_BASE", ""),
        "llm_api_key": os.getenv("LLM_API_KEY", ""),
        "llm_model_id": os.getenv("LLM_MODEL_ID", ""),
    }

    return config


def github_api_get(
    url: str,
    token: str,
    params: dict | None = None,
    max_retries: int = 3,
    logger: logging.Logger | None = None
) -> requests.Response | None:
    """带认证和重试的 GitHub API GET 请求。

    Args:
        url: API URL。
        token: GitHub token。
        params: 查询参数。
        max_retries: 最大重试次数。
        logger: 日志记录器。

    Returns:
        Response 对象，失败返回 None。
    """
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)

            if logger:
                logger.debug(f"API请求: {url} -> HTTP {response.status_code}")

            if response.status_code == 429:
                reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
                current_time = int(time.time())
                wait_seconds = max(reset_time - current_time, 60)
                if logger:
                    logger.warning(f"API限流，等待 {wait_seconds} 秒")
                time.sleep(wait_seconds)
                continue

            if response.status_code >= 500:
                wait = 2 ** attempt
                if logger:
                    logger.warning(f"服务器错误，{wait}秒后重试 (尝试 {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue

            remaining = int(response.headers.get("X-RateLimit-Remaining", 1000))
            if remaining < 5:
                reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
                current_time = int(time.time())
                wait_seconds = max(reset_time - current_time, 0)
                if logger and wait_seconds > 0:
                    logger.info(f"API配额即将耗尽，等待 {wait_seconds} 秒")
                if wait_seconds > 0:
                    time.sleep(wait_seconds)

            if response.status_code >= 400:
                if logger:
                    logger.error(f"API请求失败: {url} -> HTTP {response.status_code}")
                return None

            return response

        except requests.exceptions.RequestException as e:
            wait = 2 ** attempt
            if logger:
                logger.warning(f"网络错误: {e}，{wait}秒后重试 (尝试 {attempt + 1}/{max_retries})")
            time.sleep(wait)

    if logger:
        logger.error(f"API请求失败，已达到最大重试次数: {url}")
    return None


def fetch_readme(owner: str, repo: str, token: str, logger: logging.Logger | None = None) -> str:
    """获取 README 内容。

    Args:
        owner: 仓库所有者。
        repo: 仓库名称。
        token: GitHub token。
        logger: 日志记录器。

    Returns:
        README 内容字符串，截断到 5000 字符，失败返回空字符串。
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    response = github_api_get(url, token, logger=logger)

    if not response:
        if logger:
            logger.warning(f"README 获取失败: {owner}/{repo}")
        return ""

    try:
        data = response.json()
        content = data.get("content", "")
        content = content.replace("\n", "")
        decoded = base64.b64decode(content).decode("utf-8", errors="replace")
        return decoded[:5000]
    except Exception as e:
        if logger:
            logger.warning(f"README 解码失败: {owner}/{repo} - {e}")
        return ""


def fetch_repo_details(
    owner: str,
    repo: str,
    token: str,
    logger: logging.Logger | None = None
) -> dict[str, Any]:
    """获取仓库详情。

    Args:
        owner: 仓库所有者。
        repo: 仓库名称。
        token: GitHub token。
        logger: 日志记录器。

    Returns:
        包含 created_at, updated_at, topics 的字典。
    """
    url = f"https://api.github.com/repos/{owner}/{repo}"
    response = github_api_get(url, token, logger=logger)

    now_gmt8 = generate_collected_at()

    if not response:
        if logger:
            logger.warning(f"仓库详情获取失败: {owner}/{repo}")
        return {
            "created_at": now_gmt8,
            "updated_at": now_gmt8,
            "topics": [],
        }

    try:
        data = response.json()
        return {
            "created_at": to_gmt8(data.get("created_at", "")),
            "updated_at": to_gmt8(data.get("updated_at", "")),
            "topics": data.get("topics", []),
        }
    except Exception as e:
        if logger:
            logger.warning(f"仓库详情解析失败: {owner}/{repo} - {e}")
        return {
            "created_at": now_gmt8,
            "updated_at": now_gmt8,
            "topics": [],
        }


def to_gmt8(utc_str: str) -> str:
    """UTC ISO 8601 时间字符串转 GMT+8 +08:00 格式。

    Args:
        utc_str: UTC 时间字符串，如 "2026-04-16T17:56:15Z" 或 "2026-04-16T17:56:15+00:00"。

    Returns:
        GMT+8 时间字符串，如 "2026-04-17T01:56:15+08:00"。
    """
    if not utc_str:
        return generate_collected_at()

    try:
        utc_str = utc_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(utc_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_gmt8 = dt.astimezone(GMT8)
        return dt_gmt8.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    except ValueError:
        return generate_collected_at()


def is_excluded(name: str, description: str) -> bool:
    """判断是否应排除该项目。

    Args:
        name: 仓库名称。
        description: 项目描述。

    Returns:
        True 表示应排除，False 表示保留。
    """
    name_lower = name.lower()
    desc_lower = description.lower() if description else ""
    for pattern in EXCLUDE_PATTERNS:
        if pattern in name_lower or pattern in desc_lower:
            return True
    return False


def matches_ai(topics: list[str], description: str) -> bool:
    """判断是否匹配 AI/LLM/Agent 相关主题。

    Args:
        topics: 仓库 topics 列表。
        description: 项目描述。

    Returns:
        True 表示匹配，应纳入。
    """
    if any(t.lower() in TARGET_TOPICS for t in topics):
        return True
    desc_lower = description.lower() if description else ""
    return any(kw in desc_lower for kw in DESC_KEYWORDS)


def generate_timestamp() -> str:
    """生成当前 GMT+8 的 YYYY-MM-DD-HHMMSS 字符串。

    Returns:
        时间戳字符串。
    """
    now = datetime.now(GMT8)
    return now.strftime("%Y-%m-%d-%H%M%S")


def generate_collected_at() -> str:
    """生成当前 GMT+8 的 ISO 8601 +08:00 时间字符串。

    Returns:
        ISO 8601 时间字符串。
    """
    now = datetime.now(GMT8)
    return now.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def generate_task_id() -> str:
    """生成任务 ID。

    Returns:
        格式为 {YYYY-MM-DD-HHMMSS}-uuidv4 的任务 ID。
    """
    timestamp = generate_timestamp()
    unique_id = str(uuid.uuid4())[:8]
    return f"{timestamp}-{unique_id}"


def create_status_file(
    status_path: Path,
    task_id: str,
    source: str,
    raw_output_file: str,
    status: str = "started"
) -> dict[str, Any]:
    """创建状态文件。

    Args:
        status_path: 状态文件路径。
        task_id: 任务 ID。
        source: 数据源名称。
        raw_output_file: 中间文件路径。
        status: 初始状态。

    Returns:
        状态数据字典。
    """
    data = {
        "agent": "collector",
        "task_id": task_id,
        "status": status,
        "sources": [source],
        "output_files": [],
        "raw_output_file": raw_output_file,
        "quality": "ok",
        "error_count": 0,
        "start_time": generate_collected_at(),
        "raw_items_url": [],
        "end_time": "",
    }

    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        __import__("json").dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return data


def update_status_file(
    status_path: Path,
    data: dict[str, Any],
    status: str | None = None,
    raw_items_url: list[str] | None = None,
    quality: str | None = None,
    error_count: int | None = None,
    end_time: str | None = None,
) -> None:
    """更新状态文件。

    Args:
        status_path: 状态文件路径。
        data: 状态数据字典。
        status: 新状态。
        raw_items_url: 已处理 URL 列表。
        quality: 质量判定。
        error_count: 错误计数。
        end_time: 结束时间。
    """
    if status is not None:
        data["status"] = status
    if raw_items_url is not None:
        data["raw_items_url"] = raw_items_url
    if quality is not None:
        data["quality"] = quality
    if error_count is not None:
        data["error_count"] = error_count
    if end_time is not None:
        data["end_time"] = end_time

    status_path.write_text(
        __import__("json").dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def read_raw_file(raw_path: Path) -> dict[str, Any]:
    """读取中间文件。

    Args:
        raw_path: 中间文件路径。

    Returns:
        文件内容字典，文件不存在返回空结构。
    """
    if not raw_path.exists():
        return {"items": []}

    try:
        content = raw_path.read_text(encoding="utf-8")
        return __import__("json").loads(content)
    except Exception:
        return {"items": []}


def write_raw_file(
    raw_path: Path,
    collected_at: str,
    source: str,
    items: list[dict[str, Any]],
    since: str | None = None
) -> None:
    """写入中间文件。

    Args:
        raw_path: 中间文件路径。
        collected_at: 采集时间。
        source: 数据源名称。
        items: 项目列表。
        since: Trending 时间范围（可选）。
    """
    data = {
        "collected_at": collected_at,
        "source": source,
        "version": "1.0",
        "items": items,
    }
    if since:
        data["since"] = since

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        __import__("json").dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def merge_items(
    existing_items: list[dict[str, Any]],
    new_item: dict[str, Any]
) -> list[dict[str, Any]]:
    """合并项目列表，按 URL 去重，新数据覆盖旧数据。

    Args:
        existing_items: 已有项目列表。
        new_item: 新项目。

    Returns:
        合并后的项目列表。
    """
    url = new_item.get("url", "")
    merged = [item for item in existing_items if item.get("url") != url]
    merged.append(new_item)
    return merged


def find_resume_status(
    processed_dir: Path,
    source: str,
    logger: logging.Logger | None = None
) -> tuple[Path, dict[str, Any]] | None:
    """查找可恢复的状态文件。

    Args:
        processed_dir: 状态文件目录。
        source: 数据源名称。
        logger: 日志记录器。

    Returns:
        (状态文件路径, 状态数据) 元组，未找到返回 None。
    """
    if not processed_dir.exists():
        return None

    status_files = sorted(
        processed_dir.glob("collector-*-status.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    for status_file in status_files:
        try:
            content = status_file.read_text(encoding="utf-8")
            data = __import__("json").loads(content)

            if source in data.get("sources", []):
                if data.get("status") not in ["completed", "failed"]:
                    if logger:
                        logger.info(f"找到未完成任务: {status_file}")
                    return (status_file, data)
        except Exception:
            continue

    return None


def parse_timestamp_from_filename(filename: str) -> str | None:
    """从状态文件名解析时间戳。

    Args:
        filename: 文件名，如 "collector-search-2026-04-20-100000-status.json"
            或 "collector-trending-2026-04-20-100000-status.json"。

    Returns:
        时间戳字符串，如 "2026-04-20-100000"。
    """
    match = re.search(r"collector-(?:search|trending)-(\d{4}-\d{2}-\d{2}-\d{6})", filename)
    if match:
        return match.group(1)
    return None


def get_project_root() -> Path:
    """获取项目根目录。

    Returns:
        项目根目录路径。
    """
    return find_project_root()

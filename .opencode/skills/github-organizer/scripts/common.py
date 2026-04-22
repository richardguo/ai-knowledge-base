"""
GitHub Organizer 公共模块 - 提供共享的工具函数
"""

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


GMT8 = timezone(timedelta(hours=8))


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

    log_path = Path(log_dir) / f"organizer-{timestamp}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def load_env() -> dict[str, str]:
    """从项目根目录 .env 读取配置。

    Returns:
        包含环境变量的字典。
    """
    project_root = find_project_root()
    env_path = project_root / ".env"

    if not env_path.exists():
        return {}

    result = {}
    with open(env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                result[key.strip()] = value.strip().strip('"\'')
    return result


def generate_task_id() -> str:
    """生成任务 ID。

    Returns:
        任务 ID 字符串。
    """
    import uuid
    return str(uuid.uuid4())


def to_gmt8(timestamp_str: str) -> str:
    """将 ISO 8601 时间戳转换为 GMT+8 格式。

    Args:
        timestamp_str: ISO 8601 时间戳字符串。

    Returns:
        GMT+8 格式时间戳字符串。
    """
    if not timestamp_str:
        return ""

    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_gmt8 = dt.astimezone(GMT8)
        return dt_gmt8.strftime('%Y-%m-%dT%H:%M:%S+08:00')
    except Exception:
        return timestamp_str


def generate_collected_at() -> str:
    """生成采集时间戳（GMT+8）。

    Returns:
        ISO 8601 GMT+8 格式时间戳。
    """
    now = datetime.now(GMT8)
    return now.strftime('%Y-%m-%dT%H:%M:%S+08:00')


def generate_timestamp() -> str:
    """生成时间戳字符串。

    Returns:
        时间戳字符串。
    """
    now = datetime.now(GMT8)
    return now.strftime('%Y-%m-%d-%H%M%S')

"""工作流状态持久化模块。

提供基于 JSON 文件的状态保存和恢复功能。
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from workflows.state import KBState

CHECKPOINT_DIR = Path("knowledge/checkpoints")
CHECKPOINT_FILE = CHECKPOINT_DIR / "latest.json"


def ensure_checkpoint_dir() -> None:
    """确保 checkpoint 目录存在。"""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


def save_checkpoint(state: KBState, checkpoint_name: str = "latest") -> Path:
    """保存工作流状态到 JSON 文件。

    Args:
        state: 当前工作流状态。
        checkpoint_name: checkpoint 文件名（不含扩展名）。默认 "latest"。

    Returns:
        Path: 保存的文件路径。
    """
    ensure_checkpoint_dir()

    filepath = CHECKPOINT_DIR / f"{checkpoint_name}.json"

    checkpoint_data = {
        "state": state,
        "saved_at": datetime.now().isoformat(),
        "version": 1,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)

    print(f"[Checkpoint] 状态已保存到: {filepath}")
    return filepath


def load_checkpoint(checkpoint_name: str = "latest") -> KBState | None:
    """从 JSON 文件加载工作流状态。

    Args:
        checkpoint_name: checkpoint 文件名（不含扩展名）。默认 "latest"。

    Returns:
        KBState | None: 加载的状态，如果文件不存在则返回 None。
    """
    filepath = CHECKPOINT_DIR / f"{checkpoint_name}.json"

    if not filepath.exists():
        print(f"[Checkpoint] 未找到 checkpoint 文件: {filepath}")
        return None

    with open(filepath, "r", encoding="utf-8") as f:
        checkpoint_data = json.load(f)

    state = checkpoint_data.get("state", {})
    saved_at = checkpoint_data.get("saved_at", "unknown")

    print(f"[Checkpoint] 从 {filepath} 加载状态（保存时间: {saved_at}）")
    return state


def clear_checkpoint(checkpoint_name: str = "latest") -> None:
    """删除 checkpoint 文件。

    Args:
        checkpoint_name: checkpoint 文件名（不含扩展名）。默认 "latest"。
    """
    filepath = CHECKPOINT_DIR / f"{checkpoint_name}.json"

    if filepath.exists():
        os.remove(filepath)
        print(f"[Checkpoint] 已删除: {filepath}")


def has_checkpoint(checkpoint_name: str = "latest") -> bool:
    """检查是否存在指定的 checkpoint 文件。

    Args:
        checkpoint_name: checkpoint 文件名（不含扩展名）。默认 "latest"。

    Returns:
        bool: 是否存在 checkpoint 文件。
    """
    filepath = CHECKPOINT_DIR / f"{checkpoint_name}.json"
    return filepath.exists()

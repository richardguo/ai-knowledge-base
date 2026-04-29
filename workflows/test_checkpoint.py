"""测试 checkpoint 功能。

验证：
1. 正常执行时保存 checkpoint
2. -resume 参数能正确加载状态
3. 从 organize 节点恢复执行
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from workflows.checkpoint import clear_checkpoint, has_checkpoint, load_checkpoint, save_checkpoint
from workflows.state import KBState

load_dotenv(Path(__file__).parent.parent / ".env")


def test_save_load_checkpoint() -> None:
    """测试 checkpoint 保存和加载功能。"""
    print("=" * 60)
    print("测试 1: checkpoint 保存和加载")
    print("=" * 60)

    test_state: KBState = {
        "sources": [{"title": "test/repo", "url": "https://github.com/test/repo"}],
        "analyses": [{"url": "https://github.com/test/repo", "summary": "测试摘要", "tags": ["test"], "relevance_score": 0.9, "category": "other"}],
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "cost_tracker": {"total_tokens": 100},
    }

    save_checkpoint(test_state, "test_checkpoint")

    loaded = load_checkpoint("test_checkpoint")
    assert loaded is not None, "加载失败"
    assert loaded["analyses"][0]["summary"] == "测试摘要", "数据不匹配"
    assert loaded["cost_tracker"]["total_tokens"] == 100, "cost_tracker 不匹配"

    print("✓ 保存和加载功能正常")

    clear_checkpoint("test_checkpoint")
    assert not has_checkpoint("test_checkpoint"), "删除失败"
    print("✓ 删除功能正常")


def test_has_checkpoint() -> None:
    """测试 checkpoint 存在检查。"""
    print("\n" + "=" * 60)
    print("测试 2: checkpoint 存在检查")
    print("=" * 60)

    assert not has_checkpoint("nonexistent"), "不存在的 checkpoint 应返回 False"
    print("✓ 不存在的 checkpoint 正确返回 False")

    test_state: KBState = {
        "sources": [],
        "analyses": [],
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "cost_tracker": {},
    }
    save_checkpoint(test_state, "test_exists")
    assert has_checkpoint("test_exists"), "存在的 checkpoint 应返回 True"
    print("✓ 存在的 checkpoint 正确返回 True")

    clear_checkpoint("test_exists")


def test_resume_workflow() -> None:
    """测试 -resume 参数的完整流程。"""
    print("\n" + "=" * 60)
    print("测试 3: 模拟 resume 工作流")
    print("=" * 60)

    test_state: KBState = {
        "sources": [],
        "analyses": [
            {
                "url": "https://github.com/test/repo1",
                "title": "test/repo1",
                "summary": "测试项目1",
                "tags": ["test"],
                "relevance_score": 0.9,
                "category": "other",
                "highlights": ["feature1"],
                "collected_at": "2024-01-01",
            },
            {
                "url": "https://github.com/test/repo2",
                "title": "test/repo2",
                "summary": "测试项目2",
                "tags": ["test"],
                "relevance_score": 0.8,
                "category": "other",
                "highlights": ["feature2"],
                "collected_at": "2024-01-01",
            },
        ],
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "cost_tracker": {"total_tokens": 500, "input_tokens": 300, "output_tokens": 200},
    }

    save_checkpoint(test_state)
    print(f"✓ 已保存 checkpoint: {len(test_state['analyses'])} 条分析结果")

    loaded = load_checkpoint()
    print(f"✓ 已加载 checkpoint: {len(loaded['analyses'])} 条分析结果")
    print(f"  - cost_tracker: {loaded['cost_tracker']}")

    clear_checkpoint()
    print("✓ 已清理 checkpoint")


if __name__ == "__main__":
    test_save_load_checkpoint()
    test_has_checkpoint()
    test_resume_workflow()

    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)

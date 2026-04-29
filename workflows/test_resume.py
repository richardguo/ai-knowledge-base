"""测试 checkpoint 恢复功能的完整流程。

模拟：
1. 创建 checkpoint 文件
2. 使用 -resume 参数恢复执行
3. 验证从 organize 节点开始执行
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

from workflows.checkpoint import clear_checkpoint, has_checkpoint, load_checkpoint, save_checkpoint
from workflows.graph import print_state_summary, route_review
from workflows.nodes import organize_node, review_node_test, save_node
from workflows.state import KBState

load_dotenv(Path(__file__).parent.parent / ".env")


def create_test_checkpoint() -> None:
    """创建测试用的 checkpoint 文件。"""
    test_state: KBState = {
        "sources": [],
        "analyses": [
            {
                "url": "https://github.com/test/resume-test",
                "title": "test/resume-test",
                "summary": "这是一个测试项目，用于验证 checkpoint 恢复功能",
                "tags": ["test", "checkpoint", "resume"],
                "relevance_score": 0.95,
                "category": "other",
                "highlights": ["checkpoint 测试", "resume 功能"],
                "collected_at": "2024-01-01T00:00:00Z",
            }
        ],
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "cost_tracker": {"total_tokens": 1000, "input_tokens": 600, "output_tokens": 400},
    }

    save_checkpoint(test_state)
    print(f"✓ 创建测试 checkpoint: {len(test_state['analyses'])} 条分析结果")


def test_resume_workflow() -> None:
    """测试从 checkpoint 恢复工作流。"""
    print("=" * 60)
    print("测试: 从 checkpoint 恢复工作流")
    print("=" * 60)

    if not has_checkpoint():
        print("错误: 未找到 checkpoint 文件")
        return

    saved_state = load_checkpoint()
    if not saved_state:
        print("错误: 加载 checkpoint 失败")
        return

    analyses = saved_state.get("analyses", [])
    print(f"✓ 从 checkpoint 恢复: {len(analyses)} 条分析结果")
    print("✓ 跳过 collect 和 analyze 节点，从 organize 开始执行")
    print()

    graph = StateGraph(KBState)
    graph.add_node("organize", organize_node)
    graph.add_node("review", review_node_test)
    graph.add_node("save", save_node)
    graph.set_entry_point("organize")
    graph.add_edge("organize", "review")
    graph.add_conditional_edges(
        "review",
        route_review,
        {"save": "save", "organize": "organize"},
    )
    graph.add_edge("save", END)
    app = graph.compile()

    print("开始执行工作流（从 organize 节点）...")
    print("=" * 60)

    iteration_count = 0
    review_count = 0

    for event in app.stream(saved_state):
        for node_name, node_output in event.items():
            print_state_summary(node_output, node_name)
            if node_name == "organize":
                iteration_count += 1
            if node_name == "review":
                review_count += 1

    print("\n" + "=" * 60)
    print("执行统计:")
    print(f"  - organize 执行次数: {iteration_count}")
    print(f"  - review 执行次数: {review_count}")
    print("=" * 60)


def test_no_checkpoint() -> None:
    """测试没有 checkpoint 时的行为。"""
    print("\n" + "=" * 60)
    print("测试: 没有 checkpoint 时")
    print("=" * 60)

    if has_checkpoint():
        clear_checkpoint()

    if has_checkpoint():
        print("✗ checkpoint 仍存在")
    else:
        print("✓ 没有 checkpoint 文件，符合预期")


if __name__ == "__main__":
    if has_checkpoint():
        print("发现已存在的 checkpoint 文件，先清理...")
        clear_checkpoint()

    print("\n步骤 1: 创建测试 checkpoint")
    create_test_checkpoint()

    print("\n步骤 2: 测试 resume 工作流")
    test_resume_workflow()

    print("\n步骤 3: 清理并验证")
    clear_checkpoint()
    test_no_checkpoint()

    print("\n所有测试完成！")

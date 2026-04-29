"""LangGraph 工作流组装模块。

定义节点间的连接关系，构建完整的知识库处理流水线。
支持 checkpoint 持久化，可从 analyze 之后恢复执行。
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

from workflows.checkpoint import clear_checkpoint, has_checkpoint, load_checkpoint, save_checkpoint
from workflows.nodes import analyze_node, collect_node, organize_node, review_node, review_node_test, save_node
from workflows.state import KBState


def checkpoint_node(state: KBState) -> dict[str, any]:
    """Checkpoint 节点：保存当前状态到 JSON 文件。

    Args:
        state: 当前工作流状态。

    Returns:
        dict: 返回空字典（不修改状态）。
    """
    save_checkpoint(state)
    return {}


def route_review(state: KBState) -> str:
    """审核节点的路由函数。

    根据 review_passed 决定下一步走向：
    - True → save（保存到知识库）
    - False → organize（返回修正）

    Args:
        state: 当前工作流状态。

    Returns:
        str: 下一个节点名称（"save" 或 "organize"）。
    """
    if state.get("review_passed", False):
        return "save"
    return "organize"


def build_graph(use_mock_review: bool = False, enable_checkpoint: bool = True) -> StateGraph:
    """构建并编译 LangGraph 工作流。

    流程结构：
        collect → analyze → [checkpoint] → organize → review
                                              ├─(passed)→ save → END
                                              └─(failed)→ organize (循环修正)

    Args:
        use_mock_review: 是否使用 Mock 审核节点（用于测试循环）。默认 False。
        enable_checkpoint: 是否启用 checkpoint 节点。默认 True。

    Returns:
        StateGraph: 编译后的可执行工作流图。
    """
    review_fn = review_node_test if use_mock_review else review_node

    graph = StateGraph(KBState)

    graph.add_node("collect", collect_node)
    graph.add_node("analyze", analyze_node)
    if enable_checkpoint:
        graph.add_node("checkpoint", checkpoint_node)
    graph.add_node("organize", organize_node)
    graph.add_node("review", review_fn)
    graph.add_node("save", save_node)

    graph.set_entry_point("collect")

    graph.add_edge("collect", "analyze")
    if enable_checkpoint:
        graph.add_edge("analyze", "checkpoint")
        graph.add_edge("checkpoint", "organize")
    else:
        graph.add_edge("analyze", "organize")
    graph.add_edge("organize", "review")

    graph.add_conditional_edges(
        "review",
        route_review,
        {"save": "save", "organize": "organize"},
    )

    graph.add_edge("save", END)

    return graph.compile()


def print_state_summary(state: KBState, node_name: str) -> None:
    """打印节点执行后的状态摘要。

    Args:
        state: 当前工作流状态。
        node_name: 刚执行完的节点名称。
    """
    print(f"\n{'=' * 60}")
    print(f"[{node_name}] 执行完成")

    if node_name == "collect":
        sources = state.get("sources", [])
        print(f"  采集条目数: {len(sources)}")
        if sources:
            print(f"  示例: {sources[0].get('title', 'N/A')}")

    elif node_name == "analyze":
        analyses = state.get("analyses", [])
        print(f"  分析条目数: {len(analyses)}")
        if analyses:
            print(f"  平均相关度: {sum(a.get('relevance_score', 0) for a in analyses) / len(analyses):.2f}")

    elif node_name == "checkpoint":
        print(f"  状态已持久化")

    elif node_name == "organize":
        articles = state.get("articles", [])
        print(f"  知识条目数: {len(articles)}")
        if articles:
            print(f"  示例标签: {articles[0].get('tags', [])}")

    elif node_name == "review":
        passed = state.get("review_passed", False)
        iteration = state.get("iteration", 0)
        feedback = state.get("review_feedback", "")
        print(f"  审核通过: {passed}")
        print(f"  迭代次数: {iteration}")
        if feedback:
            print(f"  反馈: {feedback[:100]}...")

    elif node_name == "save":
        articles = state.get("articles", [])
        cost = state.get("cost_tracker", {})
        print(f"  保存条目数: {len(articles)}")
        print(f"  Token 消耗: {cost.get('total_tokens', 0)}")

    print(f"{'=' * 60}\n")


def run_workflow(resume: bool = False, use_mock_review: bool = False) -> None:
    """执行工作流。

    Args:
        resume: 是否从 checkpoint 恢复执行。默认 False。
        use_mock_review: 是否使用 Mock 审核节点。默认 False。
    """
    initial_state: KBState = {
        "sources": [],
        "analyses": [],
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "cost_tracker": {},
    }

    app = None

    if resume:
        if not has_checkpoint():
            print("错误: 未找到 checkpoint 文件，无法恢复")
            print("提示: 请直接运行 python workflows/graph.py 开始新的工作流")
            exit(1)

        saved_state = load_checkpoint()
        if saved_state:
            initial_state = saved_state
            analyses = saved_state.get("analyses", [])
            print(f"从 checkpoint 恢复: {len(analyses)} 条分析结果")
            print("跳过 collect 和 analyze 节点，从 organize 开始执行")

            review_fn = review_node_test if use_mock_review else review_node

            graph = StateGraph(KBState)
            graph.add_node("organize", organize_node)
            graph.add_node("review", review_fn)
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
        else:
            print("警告: checkpoint 加载失败，从头开始执行")
            app = build_graph(use_mock_review=use_mock_review)
    else:
        if has_checkpoint():
            print("警告: 发现已存在的 checkpoint 文件")
            print("提示: 如需恢复上次执行，请使用 python workflows/graph.py -resume")
            print("      如需开始新执行，将自动覆盖旧 checkpoint")
        app = build_graph(use_mock_review=use_mock_review)

    for event in app.stream(initial_state):
        for node_name, node_output in event.items():
            print_state_summary(node_output, node_name)

    if not resume:
        clear_checkpoint()
        print("[Checkpoint] 已清理 checkpoint 文件")

    print("工作流执行完成！")


if __name__ == "__main__":
    load_dotenv(Path(__file__).parent.parent / ".env")

    parser = argparse.ArgumentParser(description="AI 知识库工作流")
    parser.add_argument(
        "-resume",
        action="store_true",
        help="从上次 checkpoint 恢复执行（从 organize 节点开始）",
    )
    args = parser.parse_args()

    missing = []
    if not os.getenv("GITHUB_TOKEN"):
        missing.append("GITHUB_TOKEN")
    if not os.getenv("LLM_API_KEY"):
        missing.append("LLM_API_KEY")
    if not os.getenv("LLM_API_BASE"):
        missing.append("LLM_API_BASE")
    if not os.getenv("LLM_MODEL_ID"):
        missing.append("LLM_MODEL_ID")

    if missing:
        print(f"错误: 请设置以下环境变量: {', '.join(missing)}")
        exit(1)

    if args.resume:
        print("启动知识库工作流（恢复模式）...")
    else:
        print("启动知识库工作流...")
    print("=" * 60)

    run_workflow(resume=args.resume, use_mock_review=False)

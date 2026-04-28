"""LangGraph 工作流组装模块。

定义节点间的连接关系，构建完整的知识库处理流水线。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.graph import END, StateGraph

from workflows.nodes import analyze_node, collect_node, organize_node, review_node, save_node
from workflows.state import KBState


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


def build_graph() -> StateGraph:
    """构建并编译 LangGraph 工作流。

    流程结构：
        collect → analyze → organize → review
                                      ├─(passed)→ save → END
                                      └─(failed)→ organize (循环修正)

    Returns:
        StateGraph: 编译后的可执行工作流图。
    """
    graph = StateGraph(KBState)

    graph.add_node("collect", collect_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("organize", organize_node)
    graph.add_node("review", review_node)
    graph.add_node("save", save_node)

    graph.set_entry_point("collect")

    graph.add_edge("collect", "analyze")
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


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).parent.parent / ".env")

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

    print("启动知识库工作流...")
    print("=" * 60)

    app = build_graph()

    initial_state: KBState = {
        "sources": [],
        "analyses": [],
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "cost_tracker": {},
    }

    for event in app.stream(initial_state):
        for node_name, node_output in event.items():
            print_state_summary(node_output, node_name)

    print("工作流执行完成！")

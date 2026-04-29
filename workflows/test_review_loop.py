"""端到端测试：审核修正循环。

验证：
- review 未通过时能回到 organize
- organize 会读取 review_feedback 做修正
- iteration 正确递增
- 最多 3 次迭代后一定结束
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

from workflows.graph import route_review
from workflows.nodes import organize_node, review_node_test, save_node
from workflows.state import KBState

load_dotenv(Path(__file__).parent.parent / ".env")


def build_test_graph() -> StateGraph:
    """构建测试用工作流图（跳过 collect/analyze，使用 Mock review）。

    流程结构：
        organize → review
                   ├─(passed)→ save → END
                   └─(failed)→ organize (循环修正)

    Returns:
        StateGraph: 编译后的可执行工作流图。
    """
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

    return graph.compile()


def create_mock_analyses() -> list[dict]:
    """创建模拟的分析结果数据。

    Returns:
        list[dict]: 3 条技术项目分析结果。
    """
    return [
        {
            "url": "https://github.com/langchain-ai/langchain",
            "title": "langchain-ai/langchain",
            "summary": "LangChain 是一个用于构建 LLM 应用的框架，支持链式调用、Agent 和记忆管理。",
            "tags": ["llm", "agent-framework", "python", "chain"],
            "relevance_score": 0.95,
            "category": "agent-framework",
            "highlights": ["链式调用", "Agent 支持", "记忆管理"],
            "collected_at": "2022-10-17T00:00:00Z",
        },
        {
            "url": "https://github.com/openai/openai-python",
            "title": "openai/openai-python",
            "summary": "OpenAI 官方 Python SDK，提供 GPT-4、DALL-E 等模型的 API 访问能力。",
            "tags": ["openai", "api", "gpt", "python-sdk"],
            "relevance_score": 0.88,
            "category": "llm-tool",
            "highlights": ["官方 SDK", "GPT-4 支持", "异步调用"],
            "collected_at": "2020-05-01T00:00:00Z",
        },
        {
            "url": "https://github.com/microsoft/autogen",
            "title": "microsoft/autogen",
            "summary": "AutoGen 是微软开源的多 Agent 对话框架，支持复杂的 Agent 协作场景。",
            "tags": ["agent", "multi-agent", "llm", "conversation"],
            "relevance_score": 0.92,
            "category": "agent-framework",
            "highlights": ["多 Agent 协作", "对话管理", "微软开源"],
            "collected_at": "2023-08-01T00:00:00Z",
        },
    ]


def print_node_output(state: KBState, node_name: str) -> None:
    """打印节点执行后的关键输出。

    Args:
        state: 当前工作流状态。
        node_name: 刚执行完的节点名称。
    """
    print(f"\n[{node_name}] 执行完成")

    if node_name == "organize":
        articles = state.get("articles", [])
        iteration = state.get("iteration", 0)
        print(f"  条目数: {len(articles)}")
        print(f"  当前迭代: {iteration}")
        if articles:
            print(f"  示例: {articles[0].get('title', 'N/A')}")

    elif node_name == "review":
        passed = state.get("review_passed", False)
        iteration = state.get("iteration", 0)
        feedback = state.get("review_feedback", "")
        print(f"  审核通过: {passed}")
        print(f"  迭代次数: {iteration}")
        if feedback:
            print(f"  反馈: {feedback[:80]}...")

    elif node_name == "save":
        articles = state.get("articles", [])
        cost = state.get("cost_tracker", {})
        print(f"  保存条目数: {len(articles)}")
        print(f"  总 Token: {cost.get('total_tokens', 0)}")


def print_final_stats(final_state: KBState) -> None:
    """打印最终统计信息。

    Args:
        final_state: 工作流最终状态。
    """
    print("\n" + "=" * 60)
    print("最终统计")
    print("=" * 60)

    iteration = final_state.get("iteration", 0)
    review_passed = final_state.get("review_passed", False)
    articles = final_state.get("articles", [])
    cost = final_state.get("cost_tracker", {})

    print(f"总迭代次数: {iteration}")
    print(f"最终审核通过: {review_passed}")
    print(f"保存文章数: {len(articles)}")
    print(f"总成本 (Token):")
    print(f"  - total_tokens: {cost.get('total_tokens', 0)}")
    print(f"  - input_tokens: {cost.get('input_tokens', 0)}")
    print(f"  - output_tokens: {cost.get('output_tokens', 0)}")
    print(f"  - call_count: {cost.get('call_count', 0)}")


if __name__ == "__main__":
    print("=" * 60)
    print("端到端测试：审核修正循环")
    print("=" * 60)

    app = build_test_graph()

    initial_state: KBState = {
        "sources": [],
        "analyses": create_mock_analyses(),
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "cost_tracker": {},
    }

    print(f"\n初始状态:")
    print(f"  analyses: {len(initial_state['analyses'])} 条模拟数据")
    for a in initial_state["analyses"]:
        print(f"    - {a['title']} (score: {a['relevance_score']})")

    print("\n开始执行工作流...\n")
    print("=" * 60)

    node_count = {"organize": 0, "review": 0, "save": 0}
    last_iteration = 0
    last_review_passed = False
    last_articles_count = 0
    total_cost: dict = {}

    for event in app.stream(initial_state):
        for node_name, node_output in event.items():
            node_count[node_name] = node_count.get(node_name, 0) + 1

            if "iteration" in node_output:
                last_iteration = node_output["iteration"]
            if "review_passed" in node_output:
                last_review_passed = node_output["review_passed"]
            if "articles" in node_output:
                last_articles_count = len(node_output.get("articles", []))
            if "cost_tracker" in node_output:
                total_cost = node_output.get("cost_tracker", {})

            print_node_output(node_output, node_name)

    print_final_stats(
        {
            "iteration": last_iteration,
            "review_passed": last_review_passed,
            "articles": [{"id": i} for i in range(last_articles_count)],
            "cost_tracker": total_cost,
        }
    )

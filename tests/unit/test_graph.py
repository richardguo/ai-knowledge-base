"""LangGraph 工作流组装单元测试。"""

import os

import pytest

from workflows.graph import build_graph, print_state_summary, route_review
from workflows.state import KBState


class TestRouteReview:
    """route_review 路由函数测试。"""

    def test_route_review_passed_true(self):
        """测试审核通过时路由到 save 节点。"""
        state: KBState = {
            "sources": [],
            "analyses": [],
            "articles": [],
            "review_feedback": "",
            "review_passed": True,
            "iteration": 1,
            "cost_tracker": {},
        }

        result = route_review(state)
        assert result == "save"

    def test_route_review_passed_false(self):
        """测试审核未通过时路由到 organize 节点。"""
        state: KBState = {
            "sources": [],
            "analyses": [],
            "articles": [],
            "review_feedback": "摘要质量不足",
            "review_passed": False,
            "iteration": 1,
            "cost_tracker": {},
        }

        result = route_review(state)
        assert result == "organize"

    def test_route_review_default_false(self):
        """测试缺少 review_passed 字段时默认返回 organize。"""
        state: KBState = {
            "sources": [],
            "analyses": [],
            "articles": [],
            "review_feedback": "",
            "iteration": 0,
            "cost_tracker": {},
        }

        result = route_review(state)
        assert result == "organize"


class TestBuildGraph:
    """build_graph 函数测试。"""

    def test_build_graph_returns_compiled_graph(self):
        """测试返回编译后的工作流图。"""
        app = build_graph()

        assert app is not None
        assert hasattr(app, "stream")
        assert hasattr(app, "invoke")

    def test_build_graph_has_all_nodes(self):
        """测试工作流包含所有节点。"""
        app = build_graph()

        nodes = app.get_graph().nodes

        assert "collect" in nodes
        assert "analyze" in nodes
        assert "organize" in nodes
        assert "review" in nodes
        assert "save" in nodes

    def test_build_graph_entry_point(self):
        """测试入口点设置正确。"""
        app = build_graph()

        graph = app.get_graph()
        edges = graph.edges

        start_to_collect = any(
            edge.source == "__start__" and edge.target == "collect"
            for edge in edges
        )
        assert start_to_collect, "入口点应从 __start__ 连接到 collect"


class TestPrintStateSummary:
    """print_state_summary 函数测试。"""

    def test_print_state_summary_collect(self, capsys):
        """测试 collect 节点摘要打印。"""
        state: KBState = {
            "sources": [{"title": "test-repo", "url": "https://github.com/test/repo"}],
            "analyses": [],
            "articles": [],
            "review_feedback": "",
            "review_passed": False,
            "iteration": 0,
            "cost_tracker": {},
        }

        print_state_summary(state, "collect")
        captured = capsys.readouterr()

        assert "采集条目数: 1" in captured.out
        assert "test-repo" in captured.out

    def test_print_state_summary_analyze(self, capsys):
        """测试 analyze 节点摘要打印。"""
        state: KBState = {
            "sources": [],
            "analyses": [
                {"relevance_score": 0.8},
                {"relevance_score": 0.6},
            ],
            "articles": [],
            "review_feedback": "",
            "review_passed": False,
            "iteration": 0,
            "cost_tracker": {},
        }

        print_state_summary(state, "analyze")
        captured = capsys.readouterr()

        assert "分析条目数: 2" in captured.out
        assert "平均相关度: 0.70" in captured.out

    def test_print_state_summary_review(self, capsys):
        """测试 review 节点摘要打印。"""
        state: KBState = {
            "sources": [],
            "analyses": [],
            "articles": [],
            "review_feedback": "摘要需要更详细",
            "review_passed": False,
            "iteration": 1,
            "cost_tracker": {},
        }

        print_state_summary(state, "review")
        captured = capsys.readouterr()

        assert "审核通过: False" in captured.out
        assert "迭代次数: 1" in captured.out
        assert "摘要需要更详细" in captured.out

    def test_print_state_summary_save(self, capsys):
        """测试 save 节点摘要打印。"""
        state: KBState = {
            "sources": [],
            "analyses": [],
            "articles": [{"id": "test"}],
            "review_feedback": "",
            "review_passed": True,
            "iteration": 1,
            "cost_tracker": {"total_tokens": 500},
        }

        print_state_summary(state, "save")
        captured = capsys.readouterr()

        assert "保存条目数: 1" in captured.out
        assert "Token 消耗: 500" in captured.out


class TestGraphExecution:
    """工作流端到端执行测试。"""

    @pytest.mark.skipif(
        not os.getenv("GITHUB_TOKEN") or not os.getenv("LLM_API_KEY"),
        reason="GITHUB_TOKEN 或 LLM_API_KEY 未配置"
    )
    def test_graph_full_execution(self):
        """测试完整工作流执行。"""
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

        events = list(app.stream(initial_state))

        assert len(events) >= 5

        node_names = [list(event.keys())[0] for event in events]
        assert "collect" in node_names
        assert "analyze" in node_names
        assert "organize" in node_names
        assert "review" in node_names
        assert "save" in node_names

    @pytest.mark.skipif(
        not os.getenv("GITHUB_TOKEN") or not os.getenv("LLM_API_KEY"),
        reason="GITHUB_TOKEN 或 LLM_API_KEY 未配置"
    )
    def test_graph_state_transitions(self):
        """测试状态在工作流中正确传递。"""
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

        final_state = None
        for event in app.stream(initial_state):
            for node_name, node_output in event.items():
                final_state = node_output

        assert final_state is not None
        assert len(final_state.get("sources", [])) > 0
        assert len(final_state.get("analyses", [])) > 0
        assert final_state.get("cost_tracker", {}).get("total_tokens", 0) > 0

    @pytest.mark.skipif(
        not os.getenv("GITHUB_TOKEN") or not os.getenv("LLM_API_KEY"),
        reason="GITHUB_TOKEN 或 LLM_API_KEY 未配置"
    )
    def test_graph_review_loop(self):
        """测试审核循环机制。"""
        from unittest.mock import patch

        app = build_graph()

        initial_state: KBState = {
            "sources": [
                {
                    "title": "test/repo",
                    "url": "https://github.com/test/repo",
                    "description": "Test",
                    "language": "Python",
                    "popularity": {"stars": 100},
                    "topics": [],
                }
            ],
            "analyses": [],
            "articles": [],
            "review_feedback": "",
            "review_passed": False,
            "iteration": 0,
            "cost_tracker": {},
        }

        call_count = {"review": 0}

        original_review = app.nodes.get("review")
        if original_review:

            def tracked_review(state):
                call_count["review"] += 1
                return original_review.func(state)

            app.nodes["review"] = type("Node", (), {"func": tracked_review})()

        list(app.stream(initial_state))

        assert call_count["review"] >= 1

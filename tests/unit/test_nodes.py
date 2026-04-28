"""工作流节点函数单元测试（真实调用 API）。"""

import json
import os

import pytest

from workflows.nodes import analyze_node, collect_node, organize_node, review_node, save_node
from workflows.state import KBState


class TestCollectNode:
    """collect_node 节点测试。"""

    @pytest.mark.skipif(
        not os.getenv("GITHUB_TOKEN"),
        reason="GITHUB_TOKEN 未配置"
    )
    def test_collect_node_basic(self):
        """测试基本采集功能。"""
        state: KBState = {
            "sources": [],
            "analyses": [],
            "articles": [],
            "review_feedback": "",
            "review_passed": False,
            "iteration": 0,
            "cost_tracker": {},
        }

        result = collect_node(state)

        assert "sources" in result
        assert isinstance(result["sources"], list)
        assert len(result["sources"]) > 0

        source = result["sources"][0]
        assert "title" in source
        assert "url" in source
        assert "description" in source
        assert "popularity" in source
        assert isinstance(source["popularity"], dict)
        assert "stars" in source["popularity"]

    @pytest.mark.skipif(
        not os.getenv("GITHUB_TOKEN"),
        reason="GITHUB_TOKEN 未配置"
    )
    def test_collect_node_returns_partial_state(self):
        """测试返回部分状态更新。"""
        state: KBState = {
            "sources": [],
            "analyses": [],
            "articles": [],
            "review_feedback": "",
            "review_passed": False,
            "iteration": 0,
            "cost_tracker": {},
        }

        result = collect_node(state)

        assert "analyses" not in result
        assert "articles" not in result
        assert "sources" in result

    def test_collect_node_missing_token(self, monkeypatch):
        """测试缺少 GITHUB_TOKEN 时抛出异常。"""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        state: KBState = {
            "sources": [],
            "analyses": [],
            "articles": [],
            "review_feedback": "",
            "review_passed": False,
            "iteration": 0,
            "cost_tracker": {},
        }

        with pytest.raises(RuntimeError, match="GITHUB_TOKEN 未配置"):
            collect_node(state)


class TestAnalyzeNode:
    """analyze_node 节点测试。"""

    @pytest.mark.skipif(
        not os.getenv("LLM_API_KEY"),
        reason="LLM_API_KEY 未配置"
    )
    def test_analyze_node_basic(self):
        """测试基本分析功能。"""
        state: KBState = {
            "sources": [
                {
                    "title": "test-repo/ai-project",
                    "url": "https://github.com/test-repo/ai-project",
                    "description": "An AI-powered automation tool",
                    "language": "Python",
                    "popularity": {"stars": 1000},
                    "topics": ["ai", "automation"],
                }
            ],
            "analyses": [],
            "articles": [],
            "review_feedback": "",
            "review_passed": False,
            "iteration": 0,
            "cost_tracker": {},
        }

        result = analyze_node(state)

        assert "analyses" in result
        assert isinstance(result["analyses"], list)
        assert len(result["analyses"]) == 1

        analysis = result["analyses"][0]
        assert "summary" in analysis
        assert "tags" in analysis
        assert "relevance_score" in analysis
        assert "category" in analysis
        assert isinstance(analysis["summary"], str)
        assert len(analysis["summary"]) > 10

    @pytest.mark.skipif(
        not os.getenv("LLM_API_KEY"),
        reason="LLM_API_KEY 未配置"
    )
    def test_analyze_node_accumulates_cost(self):
        """测试 token 用量累加。"""
        state: KBState = {
            "sources": [
                {
                    "title": "test/simple",
                    "url": "https://github.com/test/simple",
                    "description": "Test project",
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
            "cost_tracker": {"total_tokens": 0},
        }

        result = analyze_node(state)

        assert "cost_tracker" in result
        assert result["cost_tracker"]["total_tokens"] > 0


class TestOrganizeNode:
    """organize_node 节点测试。"""

    def test_organize_node_filters_low_score(self):
        """测试过滤低分条目。"""
        state: KBState = {
            "sources": [],
            "analyses": [
                {
                    "url": "https://github.com/test/high",
                    "summary": "高分项目",
                    "tags": ["ai"],
                    "relevance_score": 0.8,
                    "category": "llm-tool",
                    "highlights": ["亮点1"],
                },
                {
                    "url": "https://github.com/test/low",
                    "summary": "低分项目",
                    "tags": [],
                    "relevance_score": 0.3,
                    "category": "other",
                    "highlights": [],
                },
            ],
            "articles": [],
            "review_feedback": "",
            "review_passed": False,
            "iteration": 0,
            "cost_tracker": {},
        }

        result = organize_node(state)

        assert len(result["articles"]) == 1
        assert result["articles"][0]["url"] == "https://github.com/test/high"

    def test_organize_node_deduplication(self):
        """测试 URL 去重。"""
        state: KBState = {
            "sources": [],
            "analyses": [
                {
                    "url": "https://github.com/test/same",
                    "summary": "项目1",
                    "tags": ["ai"],
                    "relevance_score": 0.7,
                    "category": "llm-tool",
                    "highlights": [],
                },
                {
                    "url": "https://github.com/test/same",
                    "summary": "项目2",
                    "tags": ["llm"],
                    "relevance_score": 0.8,
                    "category": "agent-framework",
                    "highlights": [],
                },
            ],
            "articles": [],
            "review_feedback": "",
            "review_passed": False,
            "iteration": 0,
            "cost_tracker": {},
        }

        result = organize_node(state)

        assert len(result["articles"]) == 1

    @pytest.mark.skipif(
        not os.getenv("LLM_API_KEY"),
        reason="LLM_API_KEY 未配置"
    )
    def test_organize_node_with_feedback(self):
        """测试根据审核反馈修正。"""
        state: KBState = {
            "sources": [],
            "analyses": [
                {
                    "url": "https://github.com/test/project",
                    "summary": "测试项目",
                    "tags": ["test"],
                    "relevance_score": 0.7,
                    "category": "other",
                    "highlights": ["功能1"],
                }
            ],
            "articles": [],
            "review_feedback": "摘要过于简短，请补充更多细节",
            "review_passed": False,
            "iteration": 1,
            "cost_tracker": {},
        }

        result = organize_node(state)

        assert "articles" in result
        assert len(result["articles"]) >= 1


class TestReviewNode:
    """review_node 节点测试。"""

    def test_review_node_force_pass_on_max_iteration(self):
        """测试达到最大迭代次数时强制通过。"""
        state: KBState = {
            "sources": [],
            "analyses": [],
            "articles": [{"id": "test", "title": "测试"}],
            "review_feedback": "",
            "review_passed": False,
            "iteration": 2,
            "cost_tracker": {},
        }

        result = review_node(state)

        assert result["review_passed"] is True
        assert result["iteration"] == 3

    def test_review_node_no_articles(self):
        """测试无条目时的审核。"""
        state: KBState = {
            "sources": [],
            "analyses": [],
            "articles": [],
            "review_feedback": "",
            "review_passed": False,
            "iteration": 0,
            "cost_tracker": {},
        }

        result = review_node(state)

        assert result["review_passed"] is False
        assert "无有效条目" in result["review_feedback"]

    @pytest.mark.skipif(
        not os.getenv("LLM_API_KEY"),
        reason="LLM_API_KEY 未配置"
    )
    def test_review_node_llm_scoring(self):
        """测试 LLM 四维度评分。"""
        state: KBState = {
            "sources": [],
            "analyses": [],
            "articles": [
                {
                    "id": "test",
                    "title": "LangChain",
                    "url": "https://github.com/langchain-ai/langchain",
                    "summary": "LangChain 是一个用于构建 LLM 应用的框架，提供了链式调用、记忆管理、工具集成等核心功能。",
                    "tags": ["llm", "agent", "framework", "python"],
                    "category": "agent-framework",
                    "relevance_score": 0.95,
                    "highlights": ["链式调用", "工具集成", "记忆管理"],
                }
            ],
            "review_feedback": "",
            "review_passed": False,
            "iteration": 0,
            "cost_tracker": {},
        }

        result = review_node(state)

        assert "review_passed" in result
        assert isinstance(result["review_passed"], bool)
        assert "iteration" in result
        assert result["iteration"] == 1


class TestSaveNode:
    """save_node 节点测试。"""

    def test_save_node_creates_files(self, tmp_path):
        """测试保存文件功能。"""
        articles = [
            {
                "id": "test-project",
                "title": "Test Project",
                "url": "https://github.com/test/project",
                "summary": "测试项目摘要",
                "tags": ["test"],
                "category": "other",
            }
        ]

        state: KBState = {
            "sources": [],
            "analyses": [],
            "articles": articles,
            "review_feedback": "",
            "review_passed": True,
            "iteration": 1,
            "cost_tracker": {},
        }

        import workflows.nodes
        original_makedirs = os.makedirs

        def mock_makedirs(path, exist_ok=True):
            if "knowledge/articles" in path:
                return
            return original_makedirs(path, exist_ok)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(os, "makedirs", mock_makedirs)
        monkeypatch.chdir(tmp_path)

        try:
            result = save_node(state)

            assert "cost_tracker" in result

            articles_dir = tmp_path / "knowledge" / "articles"
            assert articles_dir.exists()

            json_files = list(articles_dir.glob("*.json"))
            assert any("test-project" in f.name for f in json_files)

            index_file = articles_dir / "index.json"
            assert index_file.exists()

            with open(index_file, encoding="utf-8") as f:
                index_data = json.load(f)
            assert "articles" in index_data
        finally:
            monkeypatch.undo()

    def test_save_node_empty_articles(self, tmp_path):
        """测试空条目列表。"""
        state: KBState = {
            "sources": [],
            "analyses": [],
            "articles": [],
            "review_feedback": "",
            "review_passed": True,
            "iteration": 1,
            "cost_tracker": {},
        }

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.chdir(tmp_path)

        try:
            result = save_node(state)
            assert "cost_tracker" in result
        finally:
            monkeypatch.undo()

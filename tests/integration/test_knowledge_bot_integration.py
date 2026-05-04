"""knowledge_bot 模块集成测试——真实 Rerank API 调用。"""

import json
import os
from pathlib import Path

import pytest

from bot.knowledge_bot import (
    KnowledgeBot,
    KnowledgeSearchEngine,
    Permission,
    PermissionManager,
    Reranker,
    SearchHistory,
    SubscriptionManager,
    SynonymExpander,
)


@pytest.mark.integration
class TestRerankerIntegration:
    """真实 Rerank API 测试。"""

    @pytest.mark.skipif(
        not os.getenv("BAISHAN_RERANK_API_BASE"),
        reason="BAISHAN_RERANK_API_BASE 未配置",
    )
    def test_rerank_real_api(self) -> None:
        reranker = Reranker()
        assert reranker.is_configured

        documents = [
            "Apple is a fruit that grows on trees",
            "Banana is a yellow fruit",
            "Apple Inc. is a technology company",
            "Car is a vehicle",
        ]
        indices = reranker.rerank("Apple company", documents, top_n=2)
        assert len(indices) <= 2
        assert all(0 <= i < len(documents) for i in indices)

    @pytest.mark.skipif(
        not os.getenv("BAISHAN_RERANK_API_BASE"),
        reason="BAISHAN_RERANK_API_BASE 未配置",
    )
    def test_rerank_with_article_docs(self) -> None:
        reranker = Reranker()

        documents = [
            "agent-framework A framework for building AI agents with LLM",
            "langflow Low-code platform for AI workflows",
            "ollama A tool for local LLM inference",
            "deep-learning-kit Deep learning utilities",
            "nlp-parser Natural language processing parser",
        ]
        indices = reranker.rerank("智能体框架", documents, top_n=3)
        assert len(indices) <= 3
        assert 0 in indices


@pytest.mark.integration
class TestSearchHistoryIntegration:
    """真实文件写入的搜索历史测试。"""

    def test_record_and_read(self, tmp_path: Path) -> None:
        path = str(tmp_path / "history.jsonl")
        history = SearchHistory(path=path)
        history.record("user1", "智能体", 5)
        history.record("user1", "agent", 3)

        lines = Path(path).read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            record = json.loads(line)
            assert "timestamp" in record
            assert record["user_id"] == "user1"


@pytest.mark.integration
class TestFullSearchPipelineIntegration:
    """完整搜索流水线集成测试（含同义词、历史、分页）。"""

    @pytest.fixture()
    def bot(self, tmp_path: Path) -> KnowledgeBot:
        articles_dir = tmp_path / "articles"
        articles_dir.mkdir()

        for name, score, tags, date in [
            ("agent-framework", 9, ["agent-framework"], "2026-04-21"),
            ("langflow", 8, ["low-code", "agent-framework"], "2026-04-22"),
            ("ollama", 7, ["llm"], "2026-04-23"),
            ("llm-engine", 6, ["llm", "inference"], "2026-04-24"),
            ("deep-learning-kit", 5, ["deep-learning"], "2026-04-25"),
            ("ml-tools", 4, ["machine-learning"], "2026-04-26"),
            ("nlp-parser", 3, ["nlp"], "2026-04-27"),
            ("rag-system", 2, ["rag"], "2026-04-28"),
            ("vector-db", 1, ["vector-database"], "2026-04-29"),
            ("codegen-assistant", 0, ["code-generation"], "2026-04-30"),
        ]:
            article = {
                "id": name,
                "title": name,
                "url": f"https://github.com/test/{name}",
                "source": "github-search",
                "collected_at": f"{date}T10:00:00+08:00",
                "summary": f"{name} is a project",
                "relevance_score": score,
                "tags": tags,
            }
            (articles_dir / f"{date}-{name}.json").write_text(
                json.dumps(article, ensure_ascii=False), encoding="utf-8"
            )

        syn_file = tmp_path / "synonyms.json"
        syn_file.write_text(
            json.dumps(
                [["智能体", "agent", "agents"], ["大模型", "llm"]],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        reranker = Reranker()

        bot = KnowledgeBot(
            knowledge_dir=str(articles_dir),
            synonyms_path=str(syn_file),
            history_path=str(tmp_path / "history.jsonl"),
        )
        bot._permission_mgr = PermissionManager(store_path=str(tmp_path / "perms.json"))
        bot._subscription_mgr = SubscriptionManager(
            store_path=str(tmp_path / "subs.json")
        )
        bot._reranker = reranker
        bot._permission_mgr.grant("reader", Permission.READ)
        bot._permission_mgr.grant("writer", Permission.WRITE)
        return bot

    @pytest.mark.skipif(
        not os.getenv("BAISHAN_RERANK_API_BASE"),
        reason="BAISHAN_RERANK_API_BASE 未配置",
    )
    def test_synonym_expansion_with_rerank(self, bot: KnowledgeBot) -> None:
        reply = bot.handle_message("reader", "/search 智能体")
        assert "agent-framework" in reply

    @pytest.mark.skipif(
        not os.getenv("BAISHAN_RERANK_API_BASE"),
        reason="BAISHAN_RERANK_API_BASE 未配置",
    )
    def test_search_history_with_rerank(
        self, bot: KnowledgeBot, tmp_path: Path
    ) -> None:
        bot.handle_message("reader", "/search agent")
        bot.handle_message("reader", "/search llm")
        history_file = tmp_path / "history.jsonl"
        lines = history_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

    @pytest.mark.skipif(
        not os.getenv("BAISHAN_RERANK_API_BASE"),
        reason="BAISHAN_RERANK_API_BASE 未配置",
    )
    def test_pagination_flow_with_rerank(self, bot: KnowledgeBot) -> None:
        reply1 = bot.handle_message("reader", "/search agent")
        assert "agent-framework" in reply1

        reply2 = bot.handle_message("reader", "/next")
        assert "搜索" in reply2 or "没有更多" in reply2 or "最后一页" in reply2

    @pytest.mark.skipif(
        not os.getenv("BAISHAN_RERANK_API_BASE"),
        reason="BAISHAN_RERANK_API_BASE 未配置",
    )
    def test_full_pipeline_search_with_rerank(self, bot: KnowledgeBot) -> None:
        reply = bot.handle_message("reader", "/search agent")
        assert "agent-framework" in reply

    def test_synonym_expander_with_real_file(self) -> None:
        expander = SynonymExpander()
        result = expander.expand("智能体")
        assert "agent" in result

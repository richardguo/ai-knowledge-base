"""knowledge_bot 模块单元测试。"""

import json
import os
import unittest.mock
from pathlib import Path
from typing import Any

import pytest

from bot.knowledge_bot import (
    Intent,
    KnowledgeBot,
    KnowledgeSearchEngine,
    Permission,
    PermissionManager,
    Reranker,
    SearchHistory,
    SubscriptionManager,
    SynonymExpander,
    format_search_results,
    recognize_intent,
)


class TestIntent:
    """Intent 枚举测试。"""

    def test_all_intents_exist(self) -> None:
        assert Intent.SEARCH
        assert Intent.TODAY
        assert Intent.TOP
        assert Intent.SUBSCRIBE
        assert Intent.HELP
        assert Intent.NEXT
        assert Intent.UNKNOWN


class TestPermission:
    """Permission 枚举比较测试。"""

    def test_read_lt_write(self) -> None:
        assert Permission.READ < Permission.WRITE

    def test_write_lt_delete(self) -> None:
        assert Permission.WRITE < Permission.DELETE

    def test_delete_ge_read(self) -> None:
        assert Permission.DELETE >= Permission.READ

    def test_read_not_ge_write(self) -> None:
        assert not (Permission.READ >= Permission.WRITE)

    def test_value(self) -> None:
        assert Permission.READ.value == "read"
        assert Permission.WRITE.value == "write"
        assert Permission.DELETE.value == "delete"


class TestRecognizeIntent:
    """recognize_intent 测试。"""

    def test_command_search(self) -> None:
        intent, param = recognize_intent("/search langflow")
        assert intent == Intent.SEARCH
        assert param == "langflow"

    def test_command_today(self) -> None:
        intent, param = recognize_intent("/today")
        assert intent == Intent.TODAY
        assert param == ""

    def test_command_top(self) -> None:
        intent, param = recognize_intent("/top")
        assert intent == Intent.TOP
        assert param == ""

    def test_command_subscribe(self) -> None:
        intent, param = recognize_intent("/subscribe daily")
        assert intent == Intent.SUBSCRIBE
        assert param == "daily"

    def test_command_help(self) -> None:
        intent, param = recognize_intent("/help")
        assert intent == Intent.HELP
        assert param == ""

    def test_command_next(self) -> None:
        intent, param = recognize_intent("/next")
        assert intent == Intent.NEXT
        assert param == ""

    def test_keyword_search(self) -> None:
        intent, param = recognize_intent("搜索 agent")
        assert intent == Intent.SEARCH

    def test_keyword_today(self) -> None:
        intent, _ = recognize_intent("今天有什么")
        assert intent == Intent.TODAY

    def test_keyword_top(self) -> None:
        intent, _ = recognize_intent("热门排行")
        assert intent == Intent.TOP

    def test_keyword_subscribe(self) -> None:
        intent, _ = recognize_intent("订阅")
        assert intent == Intent.SUBSCRIBE

    def test_keyword_help(self) -> None:
        intent, _ = recognize_intent("帮助")
        assert intent == Intent.HELP

    def test_keyword_next(self) -> None:
        intent, _ = recognize_intent("下一页")
        assert intent == Intent.NEXT

    def test_unknown(self) -> None:
        intent, param = recognize_intent("随机文本")
        assert intent == Intent.UNKNOWN
        assert param == "随机文本"

    def test_empty(self) -> None:
        intent, param = recognize_intent("")
        assert intent == Intent.UNKNOWN
        assert param == ""

    def test_command_priority_over_keyword(self) -> None:
        intent, param = recognize_intent("/search 今天")
        assert intent == Intent.SEARCH
        assert param == "今天"


class TestSynonymExpander:
    """SynonymExpander 单元测试。"""

    @pytest.fixture()
    def expander(self, tmp_path: Path) -> SynonymExpander:
        syn_file = tmp_path / "synonyms.json"
        syn_file.write_text(
            json.dumps(
                [
                    ["智能体", "agent", "agents"],
                    ["大模型", "llm", "large-language-model"],
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return SynonymExpander(synonyms_path=str(syn_file))

    def test_expand_returns_original(self, expander: SynonymExpander) -> None:
        result = expander.expand("智能体")
        assert "智能体" in result

    def test_expand_adds_synonyms(self, expander: SynonymExpander) -> None:
        result = expander.expand("智能体")
        assert "agent" in result
        assert "agents" in result

    def test_expand_reverse_direction(self, expander: SynonymExpander) -> None:
        result = expander.expand("agent")
        assert "智能体" in result
        assert "agents" in result

    def test_expand_no_match_returns_original(self, expander: SynonymExpander) -> None:
        result = expander.expand("python")
        assert result == ["python"]

    def test_expand_case_insensitive(self, expander: SynonymExpander) -> None:
        result = expander.expand("Agent")
        assert "智能体" in result

    def test_expand_dedup(self, expander: SynonymExpander) -> None:
        result = expander.expand("agent")
        agent_count = sum(1 for t in result if t.lower() == "agent")
        assert agent_count == 1

    def test_missing_file_returns_original(self, tmp_path: Path) -> None:
        expander = SynonymExpander(synonyms_path=str(tmp_path / "missing.json"))
        result = expander.expand("智能体")
        assert result == ["智能体"]

    def test_expand_substring_match(self, expander: SynonymExpander) -> None:
        result = expander.expand("智能体框架")
        assert "agent" in result

    def test_expand_multiple_groups(self, expander: SynonymExpander) -> None:
        result = expander.expand("智能体 大模型")
        assert "agent" in result
        assert "llm" in result


class TestReranker:
    """Reranker 单元测试。"""

    def test_rerank_returns_indices(self) -> None:
        mock_response = unittest.mock.MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "results": [
                    {"index": 2, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.8},
                    {"index": 1, "relevance_score": 0.7},
                ]
            }
        ).encode("utf-8")
        mock_response.__enter__ = unittest.mock.MagicMock(return_value=mock_response)
        mock_response.__exit__ = unittest.mock.MagicMock(return_value=False)

        with unittest.mock.patch(
            "bot.knowledge_bot.urllib.request.urlopen", return_value=mock_response
        ):
            reranker = Reranker(
                api_base="https://test.com/rerank",
                api_key="test-key",
                model="test-model",
            )
            indices = reranker.rerank("Apple", ["apple", "banana", "fruit"], top_n=2)
            assert indices == [2, 0]

    def test_rerank_empty_documents(self) -> None:
        reranker = Reranker(
            api_base="https://test.com/rerank",
            api_key="test-key",
            model="test-model",
        )
        indices = reranker.rerank("test", [], top_n=5)
        assert indices == []

    def test_rerank_api_error_fallback(self) -> None:
        with unittest.mock.patch(
            "bot.knowledge_bot.urllib.request.urlopen",
            side_effect=Exception("API error"),
        ):
            reranker = Reranker(
                api_base="https://test.com/rerank",
                api_key="test-key",
                model="test-model",
            )
            indices = reranker.rerank("test", ["a", "b", "c"], top_n=2)
            assert indices == [0, 1]

    def test_rerank_not_configured_fallback(self) -> None:
        reranker = Reranker(api_base="", api_key="")
        assert not reranker.is_configured
        indices = reranker.rerank("test", ["a", "b", "c"], top_n=5)
        assert indices == [0, 1, 2]

    def test_rerank_top_n_exceeds_docs(self) -> None:
        mock_response = unittest.mock.MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.5},
                ]
            }
        ).encode("utf-8")
        mock_response.__enter__ = unittest.mock.MagicMock(return_value=mock_response)
        mock_response.__exit__ = unittest.mock.MagicMock(return_value=False)

        with unittest.mock.patch(
            "bot.knowledge_bot.urllib.request.urlopen", return_value=mock_response
        ):
            reranker = Reranker(
                api_base="https://test.com/rerank",
                api_key="test-key",
                model="test-model",
            )
            indices = reranker.rerank("test", ["a", "b"], top_n=5)
            assert indices == [1, 0]

    def test_rerank_constructs_correct_request(self) -> None:
        mock_response = unittest.mock.MagicMock()
        mock_response.read.return_value = json.dumps(
            {"results": [{"index": 0, "relevance_score": 1.0}]}
        ).encode("utf-8")
        mock_response.__enter__ = unittest.mock.MagicMock(return_value=mock_response)
        mock_response.__exit__ = unittest.mock.MagicMock(return_value=False)

        with unittest.mock.patch(
            "bot.knowledge_bot.urllib.request.urlopen", return_value=mock_response
        ) as mock_urlopen:
            reranker = Reranker(
                api_base="https://test.com/rerank",
                api_key="test-key",
                model="test-model",
            )
            reranker.rerank("Apple", ["apple", "banana"], top_n=1)

            call_args = mock_urlopen.call_args
            req = call_args[0][0]
            assert req.full_url == "https://test.com/rerank"
            assert req.get_header("Authorization") == "Bearer test-key"
            body = json.loads(req.data.decode("utf-8"))
            assert body["model"] == "test-model"
            assert body["query"] == "Apple"
            assert body["documents"] == ["apple", "banana"]
            assert body["top_n"] == 1

    def test_rerank_uses_env_vars(self) -> None:
        env = {
            "BAISHAN_RERANK_API_BASE": "https://env.com/rerank",
            "BAISHAN_API_KEY": "env-key",
            "RERANK_MODEL_ID": "env-model",
        }
        with unittest.mock.patch.dict(os.environ, env, clear=False):
            reranker = Reranker()
            assert reranker._api_base == "https://env.com/rerank"
            assert reranker._api_key == "env-key"
            assert reranker._model == "env-model"

    def test_rerank_json_decode_error_fallback(self) -> None:
        mock_response = unittest.mock.MagicMock()
        mock_response.read.return_value = b"invalid json"
        mock_response.__enter__ = unittest.mock.MagicMock(return_value=mock_response)
        mock_response.__exit__ = unittest.mock.MagicMock(return_value=False)

        with unittest.mock.patch(
            "bot.knowledge_bot.urllib.request.urlopen", return_value=mock_response
        ):
            reranker = Reranker(
                api_base="https://test.com/rerank",
                api_key="test-key",
                model="test-model",
            )
            indices = reranker.rerank("test", ["a", "b"], top_n=2)
            assert indices == [0, 1]


class TestSearchHistory:
    """SearchHistory 单元测试。"""

    @pytest.fixture()
    def history(self, tmp_path: Path) -> SearchHistory:
        return SearchHistory(path=str(tmp_path / "history.jsonl"))

    def test_record_creates_file(self, history: SearchHistory, tmp_path: Path) -> None:
        history.record("user1", "智能体", 5)
        assert (tmp_path / "history.jsonl").exists()

    def test_record_contains_fields(
        self, history: SearchHistory, tmp_path: Path
    ) -> None:
        history.record("user1", "智能体", 5)
        line = (tmp_path / "history.jsonl").read_text(encoding="utf-8").strip()
        record = json.loads(line)
        assert "timestamp" in record
        assert record["user_id"] == "user1"
        assert record["query"] == "智能体"
        assert record["result_count"] == 5

    def test_record_appends(self, history: SearchHistory, tmp_path: Path) -> None:
        history.record("user1", "agent", 3)
        history.record("user2", "llm", 1)
        lines = (
            (tmp_path / "history.jsonl").read_text(encoding="utf-8").strip().split("\n")
        )
        assert len(lines) == 2
        assert json.loads(lines[0])["user_id"] == "user1"
        assert json.loads(lines[1])["user_id"] == "user2"

    def test_record_creates_parent_dirs(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "history.jsonl"
        history = SearchHistory(path=str(nested))
        history.record("user1", "test", 0)
        assert nested.exists()

    def test_default_path_is_home(self) -> None:
        history = SearchHistory()
        assert history._path == Path.home() / ".knowledge_bot_history.jsonl"


class TestKnowledgeSearchEngine:
    """KnowledgeSearchEngine 测试。"""

    @pytest.fixture()
    def engine(self, tmp_path: Path) -> KnowledgeSearchEngine:
        articles_dir = tmp_path / "articles"
        articles_dir.mkdir()
        for name, score, tags, date in [
            ("agent-framework", 9, ["agent-framework"], "2026-04-21"),
            ("langflow", 8, ["low-code", "agent-framework"], "2026-04-22"),
            ("ollama", 7, ["llm"], "2026-04-23"),
        ]:
            article = {
                "id": name,
                "title": name,
                "url": f"https://github.com/test/{name}",
                "source": "github-search",
                "collected_at": f"{date}T10:00:00+08:00",
                "summary": f"{name} is a project for agent and LLM"
                if "agent" in name
                else f"{name} is a tool for local LLM inference",
                "relevance_score": score,
                "tags": tags,
            }
            (articles_dir / f"{date}-{name}.json").write_text(
                json.dumps(article, ensure_ascii=False), encoding="utf-8"
            )
        return KnowledgeSearchEngine(knowledge_dir=str(articles_dir))

    def test_search_keyword(self, engine: KnowledgeSearchEngine) -> None:
        results = engine.search(keyword="agent")
        assert len(results) == 2
        assert results[0]["title"] == "agent-framework"

    def test_search_keyword_list(self, engine: KnowledgeSearchEngine) -> None:
        results = engine.search(keyword=["agent", "ollama"])
        assert len(results) == 3

    def test_search_keyword_list_or_logic(
        self, engine: KnowledgeSearchEngine
    ) -> None:
        results = engine.search(keyword=["agent", "nonexistent"])
        assert len(results) == 2

    def test_search_tags(self, engine: KnowledgeSearchEngine) -> None:
        results = engine.search(tags=["agent-framework"])
        assert len(results) == 2

    def test_search_date_range(self, engine: KnowledgeSearchEngine) -> None:
        results = engine.search(date_from="2026-04-22", date_to="2026-04-23")
        assert len(results) == 2

    def test_search_date_string(self, engine: KnowledgeSearchEngine) -> None:
        import datetime as dt

        results = engine.search(date_from=dt.date(2026, 4, 23))
        assert len(results) == 1

    def test_search_limit(self, engine: KnowledgeSearchEngine) -> None:
        results = engine.search(limit=2)
        assert len(results) == 2

    def test_search_no_results(self, engine: KnowledgeSearchEngine) -> None:
        results = engine.search(keyword="nonexistent")
        assert results == []

    def test_search_sorted_by_score(self, engine: KnowledgeSearchEngine) -> None:
        results = engine.search()
        scores = [r["relevance_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        engine = KnowledgeSearchEngine(knowledge_dir=str(tmp_path / "nope"))
        assert engine.search() == []


class TestSubscriptionManager:
    """SubscriptionManager 测试。"""

    @pytest.fixture()
    def mgr(self, tmp_path: Path) -> SubscriptionManager:
        return SubscriptionManager(store_path=str(tmp_path / "subs.json"))

    def test_add_and_get(self, mgr: SubscriptionManager) -> None:
        mgr.add("u1", tags=["agent-framework"], daily=True)
        sub = mgr.get("u1")
        assert sub is not None
        assert "agent-framework" in sub["tags"]
        assert sub["daily"] is True

    def test_add_merges_tags(self, mgr: SubscriptionManager) -> None:
        mgr.add("u1", tags=["a"])
        mgr.add("u1", tags=["b"])
        sub = mgr.get("u1")
        assert sub is not None
        assert set(sub["tags"]) == {"a", "b"}

    def test_remove(self, mgr: SubscriptionManager) -> None:
        mgr.add("u1", tags=["a"])
        assert mgr.remove("u1") is True
        assert mgr.get("u1") is None

    def test_remove_nonexistent(self, mgr: SubscriptionManager) -> None:
        assert mgr.remove("nope") is False

    def test_get_nonexistent(self, mgr: SubscriptionManager) -> None:
        assert mgr.get("nope") is None

    def test_list_subscribers(self, mgr: SubscriptionManager) -> None:
        mgr.add("u1", tags=["a"])
        mgr.add("u2", tags=["b"])
        assert set(mgr.list_subscribers()) == {"u1", "u2"}

    def test_list_subscribers_by_tag(self, mgr: SubscriptionManager) -> None:
        mgr.add("u1", tags=["agent"])
        mgr.add("u2", tags=["llm"])
        assert mgr.list_subscribers(tag="agent") == ["u1"]

    def test_persistence(self, tmp_path: Path) -> None:
        path = str(tmp_path / "subs.json")
        mgr1 = SubscriptionManager(store_path=path)
        mgr1.add("u1", tags=["x"])
        mgr2 = SubscriptionManager(store_path=path)
        assert mgr2.get("u1") is not None


class TestPermissionManager:
    """PermissionManager 测试。"""

    @pytest.fixture()
    def mgr(self, tmp_path: Path) -> PermissionManager:
        return PermissionManager(store_path=str(tmp_path / "perms.json"))

    def test_grant_and_check(self, mgr: PermissionManager) -> None:
        mgr.grant("u1", Permission.READ)
        assert mgr.check("u1", Permission.READ) is True
        assert mgr.check("u1", Permission.WRITE) is False

    def test_write_includes_read(self, mgr: PermissionManager) -> None:
        mgr.grant("u1", Permission.WRITE)
        assert mgr.check("u1", Permission.READ) is True
        assert mgr.check("u1", Permission.WRITE) is True

    def test_delete_includes_all(self, mgr: PermissionManager) -> None:
        mgr.grant("u1", Permission.DELETE)
        assert mgr.check("u1", Permission.READ) is True
        assert mgr.check("u1", Permission.WRITE) is True
        assert mgr.check("u1", Permission.DELETE) is True

    def test_revoke(self, mgr: PermissionManager) -> None:
        mgr.grant("u1", Permission.READ)
        assert mgr.revoke("u1") is True
        assert mgr.check("u1", Permission.READ) is False

    def test_revoke_nonexistent(self, mgr: PermissionManager) -> None:
        assert mgr.revoke("nope") is False

    def test_check_no_permission(self, mgr: PermissionManager) -> None:
        assert mgr.check("u1", Permission.READ) is False

    def test_persistence(self, tmp_path: Path) -> None:
        path = str(tmp_path / "perms.json")
        mgr1 = PermissionManager(store_path=path)
        mgr1.grant("u1", Permission.WRITE)
        mgr2 = PermissionManager(store_path=path)
        assert mgr2.check("u1", Permission.WRITE) is True


class TestFormatSearchResults:
    """format_search_results 测试。"""

    @pytest.fixture()
    def sample_results(self) -> list[dict[str, Any]]:
        return [
            {
                "title": "agent-framework",
                "url": "https://github.com/test/agent-framework",
                "relevance_score": 9,
                "summary": "A framework for building AI agents with LLM",
                "tags": ["agent-framework"],
            },
            {
                "title": "langflow",
                "url": "https://github.com/test/langflow",
                "relevance_score": 7,
                "summary": "Low-code platform for AI workflows",
                "tags": ["low-code"],
            },
        ]

    def test_with_query(self, sample_results: list[dict[str, Any]]) -> None:
        output = format_search_results(sample_results, custom_query_input="agent")
        assert "搜索「agent」" in output
        assert "agent-framework" in output
        assert "9/10" in output
        assert "7/10" in output

    def test_without_query(self, sample_results: list[dict[str, Any]]) -> None:
        output = format_search_results(sample_results)
        assert "搜索结果" in output
        assert "agent-framework" in output

    def test_empty_results_with_query(self) -> None:
        output = format_search_results([], custom_query_input="agent")
        assert "未找到" in output
        assert "agent" in output

    def test_empty_results_without_query(self) -> None:
        output = format_search_results([])
        assert "未找到" in output


class TestKnowledgeBot:
    """KnowledgeBot 测试。"""

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
                [["智能体", "agent", "agents"], ["大模型", "llm", "large-language-model"]],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        bot = KnowledgeBot(
            knowledge_dir=str(articles_dir),
            synonyms_path=str(syn_file),
            history_path=str(tmp_path / "history.jsonl"),
        )
        bot._permission_mgr = PermissionManager(store_path=str(tmp_path / "perms.json"))
        bot._subscription_mgr = SubscriptionManager(
            store_path=str(tmp_path / "subs.json")
        )
        bot._reranker = Reranker(api_base="", api_key="")
        bot._permission_mgr.grant("reader", Permission.READ)
        bot._permission_mgr.grant("writer", Permission.WRITE)
        return bot

    def test_search_with_permission(self, bot: KnowledgeBot) -> None:
        reply = bot.handle_message("reader", "/search agent")
        assert "agent-framework" in reply

    def test_search_no_permission(self, bot: KnowledgeBot) -> None:
        reply = bot.handle_message("stranger", "/search agent")
        assert "权限" in reply

    def test_search_no_keyword(self, bot: KnowledgeBot) -> None:
        reply = bot.handle_message("reader", "/search")
        assert "关键词" in reply

    def test_search_with_synonym_expansion(self, bot: KnowledgeBot) -> None:
        reply = bot.handle_message("reader", "/search 智能体")
        assert "agent-framework" in reply

    def test_search_records_history(
        self, bot: KnowledgeBot, tmp_path: Path
    ) -> None:
        bot.handle_message("reader", "/search agent")
        history_file = tmp_path / "history.jsonl"
        assert history_file.exists()
        line = history_file.read_text(encoding="utf-8").strip()
        record = json.loads(line)
        assert record["query"] == "agent"
        assert record["user_id"] == "reader"

    def test_search_stores_page_state(self, bot: KnowledgeBot) -> None:
        bot.handle_message("reader", "/search agent")
        assert "reader" in bot._user_page_state

    def test_search_shows_first_page(self, bot: KnowledgeBot) -> None:
        reply = bot.handle_message("reader", "/search agent")
        lines = [l for l in reply.split("\n") if l.strip().startswith(tuple("12345"))]
        assert len(lines) <= 5

    def test_next_returns_next_page(self, bot: KnowledgeBot) -> None:
        bot.handle_message("reader", "/search agent")
        reply = bot.handle_message("reader", "/next")
        assert "搜索" in reply or "没有更多" in reply

    def test_next_without_search(self, bot: KnowledgeBot) -> None:
        reply = bot.handle_message("reader", "/next")
        assert "搜索" in reply or "没有可翻页" in reply

    def test_next_at_end(self, bot: KnowledgeBot) -> None:
        bot.handle_message("reader", "/search agent")
        bot.handle_message("reader", "/next")
        reply = bot.handle_message("reader", "/next")
        assert "没有更多" in reply or "最后一页" in reply

    def test_per_user_page_isolation(self, bot: KnowledgeBot) -> None:
        bot.handle_message("reader", "/search agent")
        reply = bot.handle_message("writer", "/next")
        assert "搜索" in reply or "没有可翻页" in reply

    def test_subscribe_with_write(self, bot: KnowledgeBot) -> None:
        reply = bot.handle_message("writer", "/subscribe daily")
        assert "已订阅" in reply

    def test_subscribe_with_read_only(self, bot: KnowledgeBot) -> None:
        reply = bot.handle_message("reader", "/subscribe daily")
        assert "权限" in reply

    def test_subscribe_view(self, bot: KnowledgeBot) -> None:
        bot.handle_message("writer", "/subscribe daily")
        reply = bot.handle_message("writer", "/subscribe")
        assert "每日简报" in reply

    def test_subscribe_no_subscription(self, bot: KnowledgeBot) -> None:
        reply = bot.handle_message("writer", "/subscribe")
        assert "暂无订阅" in reply

    def test_top(self, bot: KnowledgeBot) -> None:
        reply = bot.handle_message("reader", "/top")
        assert "agent-framework" in reply

    def test_help(self, bot: KnowledgeBot) -> None:
        reply = bot.handle_message("reader", "/help")
        assert "/search" in reply
        assert "/next" in reply

    def test_unknown(self, bot: KnowledgeBot) -> None:
        reply = bot.handle_message("reader", "随便说说")
        assert "未识别" in reply

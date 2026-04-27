"""Router 路由模式的单元测试。"""

import json
from typing import Any
from unittest.mock import MagicMock, mock_open, patch

import pytest

from patterns.router import (
    Intent,
    IntentResult,
    classify_by_keyword,
    classify_by_llm,
    classify_intent,
    convert_llmresult_to_json,
    handle_github_search,
    handle_knowledge_query,
    handle_general_chat,
    route,
)
from pipeline.model_client import LLMResponse, Usage


class TestConvertLLMResultToJson:
    """LLM 结果转 JSON 测试。"""

    def test_valid_json(self) -> None:
        """测试标准 JSON 格式返回。"""
        response = LLMResponse(
            content='{"intent": "github_search", "confidence": 0.9}',
            usage=Usage(),
        )
        result = convert_llmresult_to_json(response)
        assert result["intent"] == "github_search"
        assert result["confidence"] == 0.9

    def test_json_with_whitespace(self) -> None:
        """测试带空白字符的 JSON。"""
        response = LLMResponse(
            content='  \n  {"intent": "general_chat", "confidence": 0.8}  \n  ',
            usage=Usage(),
        )
        result = convert_llmresult_to_json(response)
        assert result["intent"] == "general_chat"

    def test_json_embedded_in_text(self) -> None:
        """测试 JSON 嵌入在文本中。"""
        response = LLMResponse(
            content='根据分析，结果是 {"intent": "knowledge_query", "confidence": 0.85} 如上。',
            usage=Usage(),
        )
        result = convert_llmresult_to_json(response)
        assert result["intent"] == "knowledge_query"

    def test_invalid_json_raises_error(self) -> None:
        """测试无效 JSON 抛出 ValueError。"""
        response = LLMResponse(
            content="这不是 JSON 格式",
            usage=Usage(),
        )
        with pytest.raises(ValueError) as exc_info:
            convert_llmresult_to_json(response)
        assert "无法解析" in str(exc_info.value)

    def test_multiline_json(self) -> None:
        """测试多行 JSON。"""
        response = LLMResponse(
            content='{\n  "intent": "github_search",\n  "confidence": 0.95\n}',
            usage=Usage(),
        )
        result = convert_llmresult_to_json(response)
        assert result["intent"] == "github_search"


class TestClassifyByKeyword:
    """关键词匹配测试。"""

    def test_github_keyword_matched(self) -> None:
        """测试 github 关键词匹配。"""
        result = classify_by_keyword("帮我搜索 github 上的项目")
        assert result is not None
        assert result.intent == Intent.GITHUB_SEARCH
        assert result.source == "keyword"
        assert result.confidence == 0.9

    def test_repo_keyword_matched(self) -> None:
        """测试 repo 关键词匹配。"""
        result = classify_by_keyword("找一个开源 repo")
        assert result is not None
        assert result.intent == Intent.GITHUB_SEARCH

    def test_trending_keyword_matched(self) -> None:
        """测试 trending 关键词匹配。"""
        result = classify_by_keyword("今天的热门项目有哪些")
        assert result is not None
        assert result.intent == Intent.GITHUB_SEARCH

    def test_knowledge_query_keyword_matched(self) -> None:
        """测试知识库关键词匹配。"""
        result = classify_by_keyword("知识库里有什么")
        assert result is not None
        assert result.intent == Intent.KNOWLEDGE_QUERY

    def test_local_keyword_matched(self) -> None:
        """测试本地关键词匹配。"""
        result = classify_by_keyword("本地已收集的条目")
        assert result is not None
        assert result.intent == Intent.KNOWLEDGE_QUERY

    def test_no_keyword_matched(self) -> None:
        """测试无关键词匹配返回 None。"""
        result = classify_by_keyword("今天天气怎么样")
        assert result is None

    def test_case_insensitive(self) -> None:
        """测试大小写不敏感。"""
        result = classify_by_keyword("GITHUB GITHUB Repo REPO")
        assert result is not None
        assert result.intent == Intent.GITHUB_SEARCH

    def test_first_match_wins(self) -> None:
        """测试第一个匹配的意图被返回。"""
        result = classify_by_keyword("知识库 github")
        assert result is not None


class TestClassifyByLLM:
    """LLM 分类测试。"""

    @patch("patterns.router.quick_chat")
    def test_github_search_intent(self, mock_chat: MagicMock) -> None:
        """测试 LLM 返回 github_search 意图。"""
        mock_chat.return_value = LLMResponse(
            content='{"intent": "github_search", "confidence": 0.95, "reason": "用户想搜索开源项目"}',
            usage=Usage(),
        )
        result = classify_by_llm("帮我找一些 AI 项目")
        assert result.intent == Intent.GITHUB_SEARCH
        assert result.confidence == 0.95
        assert result.source == "llm"

    @patch("patterns.router.quick_chat")
    def test_knowledge_query_intent(self, mock_chat: MagicMock) -> None:
        """测试 LLM 返回 knowledge_query 意图。"""
        mock_chat.return_value = LLMResponse(
            content='{"intent": "knowledge_query", "confidence": 0.88, "reason": "用户查询本地数据"}',
            usage=Usage(),
        )
        result = classify_by_llm("之前收集的项目在哪")
        assert result.intent == Intent.KNOWLEDGE_QUERY
        assert result.confidence == 0.88

    @patch("patterns.router.quick_chat")
    def test_general_chat_intent(self, mock_chat: MagicMock) -> None:
        """测试 LLM 返回 general_chat 意图。"""
        mock_chat.return_value = LLMResponse(
            content='{"intent": "general_chat", "confidence": 0.92, "reason": "普通对话"}',
            usage=Usage(),
        )
        result = classify_by_llm("今天天气怎么样")
        assert result.intent == Intent.GENERAL_CHAT
        assert result.confidence == 0.92

    @patch("patterns.router.quick_chat")
    def test_invalid_intent_fallback(self, mock_chat: MagicMock) -> None:
        """测试 LLM 返回无效意图时回退到 general_chat。"""
        mock_chat.return_value = LLMResponse(
            content='{"intent": "invalid_intent", "confidence": 0.5}',
            usage=Usage(),
        )
        result = classify_by_llm("测试")
        assert result.intent == Intent.GENERAL_CHAT
        assert result.confidence == 0.3

    @patch("patterns.router.quick_chat")
    def test_llm_error_fallback(self, mock_chat: MagicMock) -> None:
        """测试 LLM 调用失败时回退。"""
        mock_chat.side_effect = Exception("API 错误")
        result = classify_by_llm("测试")
        assert result.intent == Intent.GENERAL_CHAT
        assert result.source == "llm_fallback"

    @patch("patterns.router.quick_chat")
    def test_response_format_parameter(self, mock_chat: MagicMock) -> None:
        """测试传入了 response_format 参数。"""
        mock_chat.return_value = LLMResponse(
            content='{"intent": "general_chat", "confidence": 0.8}',
            usage=Usage(),
        )
        classify_by_llm("测试")
        call_kwargs = mock_chat.call_args[1]
        assert "response_format" in call_kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}


class TestClassifyIntent:
    """两层意图分类测试。"""

    def test_keyword_match_no_llm_call(self) -> None:
        """测试关键词匹配时不调用 LLM。"""
        with patch("patterns.router.classify_by_llm") as mock_llm:
            result = classify_intent("github 上的项目")
            assert result.intent == Intent.GITHUB_SEARCH
            assert result.source == "keyword"
            mock_llm.assert_not_called()

    @patch("patterns.router.classify_by_llm")
    def test_no_keyword_calls_llm(self, mock_llm: MagicMock) -> None:
        """测试无关键词时调用 LLM。"""
        mock_llm.return_value = IntentResult(
            intent=Intent.GENERAL_CHAT,
            confidence=0.8,
            source="llm",
        )
        result = classify_intent("今天天气")
        mock_llm.assert_called_once_with("今天天气")
        assert result.source == "llm"


class TestHandleGithubSearch:
    """GitHub 搜索处理测试。"""

    @patch("patterns.router.urllib.request.urlopen")
    @patch.dict("os.environ", {"GITHUB_TOKEN": "test_token"})
    def test_successful_search(self, mock_urlopen: MagicMock) -> None:
        """测试成功的 GitHub 搜索。"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "total_count": 2,
            "items": [
                {
                    "full_name": "test/repo1",
                    "html_url": "https://github.com/test/repo1",
                    "stargazers_count": 100,
                    "description": "Test repo 1",
                    "language": "Python",
                },
                {
                    "full_name": "test/repo2",
                    "html_url": "https://github.com/test/repo2",
                    "stargazers_count": 50,
                    "description": "Test repo 2",
                    "language": "JavaScript",
                },
            ],
        }).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = handle_github_search("AI agent project")
        data = json.loads(result)
        assert data["total"] == 2
        assert len(data["results"]) == 2
        assert data["results"][0]["name"] == "test/repo1"

    @patch("patterns.router.urllib.request.urlopen")
    def test_search_with_token(self, mock_urlopen: MagicMock) -> None:
        """测试带 token 的搜索请求。"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "total_count": 0,
            "items": [],
        }).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        with patch.dict("os.environ", {"GITHUB_TOKEN": "my_token"}):
            handle_github_search("test query")

        request = mock_urlopen.call_args[0][0]
        assert "Authorization" in request.headers
        assert "token my_token" in request.headers["Authorization"]

    @patch("patterns.router.urllib.request.urlopen")
    def test_search_error_handling(self, mock_urlopen: MagicMock) -> None:
        """测试搜索错误处理。"""
        mock_urlopen.side_effect = Exception("Network error")
        result = handle_github_search("test query")
        data = json.loads(result)
        assert "error" in data


class TestHandleKnowledgeQuery:
    """知识库查询测试。"""

    @patch("builtins.open", new_callable=mock_open)
    def test_successful_query(self, mock_file: MagicMock) -> None:
        """测试成功的知识库查询。"""
        mock_file.return_value.read.return_value = json.dumps({
            "entries": [
                {
                    "id": "1",
                    "title": "langchain",
                    "url": "https://github.com/langchain-ai/langchain",
                    "tags": ["llm", "agent"],
                    "category": "framework",
                    "relevance_score": 8,
                },
                {
                    "id": "2",
                    "title": "autogpt",
                    "url": "https://github.com/Significant-Gravitas/AutoGPT",
                    "tags": ["agent", "automation"],
                    "category": "framework",
                    "relevance_score": 7,
                },
            ],
        })

        with patch("patterns.router.KNOWLEDGE_INDEX_PATH") as mock_path:
            mock_path.exists.return_value = True
            result = handle_knowledge_query("agent framework")
            data = json.loads(result)
            assert "results" in data

    @patch("patterns.router.KNOWLEDGE_INDEX_PATH")
    def test_index_not_exists(self, mock_path: MagicMock) -> None:
        """测试索引文件不存在。"""
        mock_path.exists.return_value = False
        result = handle_knowledge_query("test query")
        data = json.loads(result)
        assert "error" in data

    @patch("builtins.open", new_callable=mock_open)
    def test_empty_results(self, mock_file: MagicMock) -> None:
        """测试无匹配结果。"""
        mock_file.return_value.read.return_value = json.dumps({
            "entries": [
                {
                    "id": "1",
                    "title": "unrelated",
                    "url": "https://example.com",
                    "tags": ["other"],
                    "category": "other",
                    "relevance_score": 5,
                },
            ],
        })

        with patch("patterns.router.KNOWLEDGE_INDEX_PATH") as mock_path:
            mock_path.exists.return_value = True
            result = handle_knowledge_query("xyzabc123")
            data = json.loads(result)
            assert data["total_matched"] == 0


class TestHandleGeneralChat:
    """普通对话处理测试。"""

    @patch("patterns.router.quick_chat")
    def test_successful_chat(self, mock_chat: MagicMock) -> None:
        """测试成功的对话响应。"""
        mock_chat.return_value = LLMResponse(
            content="这是回复内容",
            usage=Usage(),
        )
        result = handle_general_chat("你好")
        assert result == "这是回复内容"

    @patch("patterns.router.quick_chat")
    def test_chat_error(self, mock_chat: MagicMock) -> None:
        """测试对话错误处理。"""
        mock_chat.side_effect = Exception("API 错误")
        result = handle_general_chat("你好")
        assert "抱歉" in result


class TestRoute:
    """统一路由入口测试。"""

    @patch("patterns.router.handle_github_search")
    def test_route_to_github_search(self, mock_handler: MagicMock) -> None:
        """测试路由到 GitHub 搜索。"""
        import patterns.router
        
        mock_handler.return_value = '{"results": []}'
        patterns.router.INTENT_HANDLERS[Intent.GITHUB_SEARCH] = mock_handler
        
        result = route("github 上的 AI 项目")
        mock_handler.assert_called_once()
        assert "results" in result

    @patch("patterns.router.handle_knowledge_query")
    def test_route_to_knowledge_query(self, mock_handler: MagicMock) -> None:
        """测试路由到知识库查询。"""
        import patterns.router
        
        mock_handler.return_value = '{"results": []}'
        patterns.router.INTENT_HANDLERS[Intent.KNOWLEDGE_QUERY] = mock_handler
        
        result = route("知识库里的内容")
        mock_handler.assert_called_once()
        assert "results" in result

    @patch("patterns.router.handle_general_chat")
    def test_route_to_general_chat(self, mock_handler: MagicMock) -> None:
        """测试路由到普通对话。"""
        import patterns.router
        
        mock_handler.return_value = "回复内容"
        patterns.router.INTENT_HANDLERS[Intent.GENERAL_CHAT] = mock_handler
        
        result = route("今天天气怎么样呢")
        mock_handler.assert_called_once()

    def test_route_empty_query(self) -> None:
        """测试空查询。"""
        result = route("")
        assert "请输入" in result

    def test_route_whitespace_query(self) -> None:
        """测试空白查询。"""
        result = route("   ")
        assert "请输入" in result


class TestIntentEnum:
    """Intent 枚举测试。"""

    def test_intent_values(self) -> None:
        """测试意图枚举值。"""
        assert Intent.GITHUB_SEARCH.value == "github_search"
        assert Intent.KNOWLEDGE_QUERY.value == "knowledge_query"
        assert Intent.GENERAL_CHAT.value == "general_chat"

    def test_intent_from_string(self) -> None:
        """测试从字符串创建意图。"""
        assert Intent("github_search") == Intent.GITHUB_SEARCH
        assert Intent("knowledge_query") == Intent.KNOWLEDGE_QUERY
        assert Intent("general_chat") == Intent.GENERAL_CHAT


class TestIntentResult:
    """IntentResult 数据类测试。"""

    def test_intent_result_creation(self) -> None:
        """测试创建意图结果。"""
        result = IntentResult(
            intent=Intent.GITHUB_SEARCH,
            confidence=0.9,
            source="keyword",
        )
        assert result.intent == Intent.GITHUB_SEARCH
        assert result.confidence == 0.9
        assert result.source == "keyword"

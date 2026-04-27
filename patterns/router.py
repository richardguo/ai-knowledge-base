"""Router 路由模式实现。

两层意图分类策略：
1. 第一层：关键词快速匹配（零成本）
2. 第二层：LLM 分类兜底（处理模糊意图）

三种意图：
- github_search: 调用 GitHub Search API
- knowledge_query: 从本地知识库检索
- general_chat: 调用 LLM 直接回答
"""

import json
import logging
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from pipeline.model_client import LLMResponse, quick_chat

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KNOWLEDGE_INDEX_PATH = Path(__file__).parent.parent / "knowledge" / "articles" / "index.json"


class Intent(str, Enum):
    """意图类型枚举。"""

    GITHUB_SEARCH = "github_search"
    KNOWLEDGE_QUERY = "knowledge_query"
    GENERAL_CHAT = "general_chat"


@dataclass
class IntentResult:
    """意图分类结果。

    Attributes:
        intent: 识别出的意图类型。
        confidence: 置信度（0-1）。
        source: 分类来源（keyword/llm）。
    """

    intent: Intent
    confidence: float
    source: str


KEYWORD_PATTERNS: dict[Intent, list[str]] = {
    Intent.GITHUB_SEARCH: [
        "github",
        "仓库",
        "repo",
        "开源项目",
        "star",
        "fork",
        "trending",
        "热门项目",
        "最新项目",
    ],
    Intent.KNOWLEDGE_QUERY: [
        "知识库",
        "本地",
        "已收集",
        "已采集",
        "articles",
        "entry",
        "条目",
    ],
}

LLM_CLASSIFICATION_PROMPT = """你是一个意图分类器。分析用户的查询，返回最匹配的意图类型。

可用的意图类型：
- github_search: 用户想搜索 GitHub 上的开源项目、仓库、热门项目等
- knowledge_query: 用户想查询本地知识库中已收集的条目
- general_chat: 普通对话、问答、或其他无法归类的请求

返回格式（必须严格遵循JSON格式）：
{{"intent": "意图类型", "confidence": 置信度0-1, "reason": "简短原因"}}

用户查询：{query}
"""


def convert_llmresult_to_json(response: LLMResponse) -> dict[str, Any]:
    """将 LLM 返回的结果转换为 JSON。

    Args:
        response: LLM 响应对象。

    Returns:
        解析后的 JSON 字典。

    Raises:
        ValueError: 当无法解析 JSON 时抛出。
    """
    content = response.content.strip()

    json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
    else:
        json_str = content

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"无法解析 LLM 返回的 JSON: {e}\n原始内容: {content}") from e


def classify_by_keyword(query: str) -> IntentResult | None:
    """通过关键词匹配快速分类意图。

    Args:
        query: 用户查询文本。

    Returns:
        分类结果，无匹配时返回 None。
    """
    query_lower = query.lower()

    for intent, keywords in KEYWORD_PATTERNS.items():
        for keyword in keywords:
            if keyword.lower() in query_lower:
                return IntentResult(intent=intent, confidence=0.9, source="keyword")

    return None


def classify_by_llm(query: str) -> IntentResult:
    """通过 LLM 分类模糊意图。

    Args:
        query: 用户查询文本。

    Returns:
        分类结果。
    """
    prompt = LLM_CLASSIFICATION_PROMPT.format(query=query)

    try:
        response = quick_chat(
            prompt,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        result = convert_llmresult_to_json(response)

        intent_str = result.get("intent", "general_chat")
        confidence = float(result.get("confidence", 0.5))

        try:
            intent = Intent(intent_str)
        except ValueError:
            intent = Intent.GENERAL_CHAT
            confidence = 0.3

        return IntentResult(intent=intent, confidence=confidence, source="llm")

    except Exception as e:
        logger.warning(f"LLM 分类失败: {e}，使用默认意图")
        return IntentResult(intent=Intent.GENERAL_CHAT, confidence=0.5, source="llm_fallback")


def classify_intent(query: str) -> IntentResult:
    """分类用户意图（两层策略）。

    先尝试关键词匹配，失败则调用 LLM。

    Args:
        query: 用户查询文本。

    Returns:
        分类结果。
    """
    keyword_result = classify_by_keyword(query)
    if keyword_result:
        logger.info(f"关键词匹配成功: {keyword_result.intent.value}")
        return keyword_result

    logger.info("关键词未匹配，调用 LLM 分类...")
    return classify_by_llm(query)


def handle_github_search(query: str) -> str:
    """处理 GitHub 搜索意图。

    Args:
        query: 用户查询文本。

    Returns:
        搜索结果（JSON 格式）。
    """
    token = os.getenv("GITHUB_TOKEN", "")
    search_terms = re.findall(r"[a-zA-Z][\w\-]*", query)
    stopwords = {"github", "the", "for", "help", "search", "about", "some", "hot", "popular", "me", "is", "are", "in", "on", "to", "of"}
    search_terms = [t for t in search_terms if len(t) > 1 and t.lower() not in stopwords]
    search_query = " ".join(search_terms[:5]) or "AI agent"
    logger.info(f"GitHub 搜索关键词: {search_query}")

    encoded_query = quote(search_query)
    url = f"https://api.github.com/search/repositories?q={encoded_query}&sort=stars&order=desc&per_page=5"

    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

        items = data.get("items", [])
        results = []
        for item in items[:5]:
            results.append(
                {
                    "name": item.get("full_name", ""),
                    "url": item.get("html_url", ""),
                    "stars": item.get("stargazers_count", 0),
                    "description": item.get("description", "")[:100] if item.get("description") else "",
                    "language": item.get("language", ""),
                }
            )

        return json.dumps(
            {"query": search_query, "total": data.get("total_count", 0), "results": results},
            ensure_ascii=False,
            indent=2,
        )

    except URLError as e:
        logger.error(f"GitHub API 请求失败: {e}")
        return json.dumps(
            {"error": f"GitHub API 请求失败: {e}", "hint": "请配置 GITHUB_TOKEN 环境变量"},
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"GitHub 搜索异常: {e}")
        return json.dumps({"error": f"搜索异常: {e}"}, ensure_ascii=False)


def handle_knowledge_query(query: str) -> str:
    """处理知识库查询意图。

    Args:
        query: 用户查询文本。

    Returns:
        查询结果（JSON 格式）。
    """
    if not KNOWLEDGE_INDEX_PATH.exists():
        return json.dumps({"error": "知识库索引文件不存在"}, ensure_ascii=False)

    try:
        with open(KNOWLEDGE_INDEX_PATH, encoding="utf-8") as f:
            index_data = json.load(f)

        entries = index_data.get("entries", [])
        query_lower = query.lower()
        query_keywords = set(re.findall(r"[\w\-]+", query_lower))
        query_keywords = {kw for kw in query_keywords if len(kw) > 2}

        scored_entries = []
        for entry in entries:
            score = 0
            title = entry.get("title", "").lower()
            tags = [t.lower() for t in entry.get("tags", [])]

            for kw in query_keywords:
                if kw in title:
                    score += 3
                for tag in tags:
                    if kw in tag:
                        score += 1

            if score > 0:
                scored_entries.append((score, entry))

        scored_entries.sort(key=lambda x: x[0], reverse=True)
        top_entries = [entry for _, entry in scored_entries[:5]]

        results = []
        for entry in top_entries:
            results.append(
                {
                    "id": entry.get("id", ""),
                    "title": entry.get("title", ""),
                    "url": entry.get("url", ""),
                    "category": entry.get("category", ""),
                    "tags": entry.get("tags", []),
                    "relevance_score": entry.get("relevance_score", 0),
                }
            )

        return json.dumps(
            {
                "query": query,
                "total_matched": len(scored_entries),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )

    except Exception as e:
        logger.error(f"知识库查询异常: {e}")
        return json.dumps({"error": f"查询异常: {e}"}, ensure_ascii=False)


def handle_general_chat(query: str) -> str:
    """处理普通对话意图。

    Args:
        query: 用户查询文本。

    Returns:
        LLM 回答。
    """
    try:
        response = quick_chat(query, temperature=0.7)
        return response.content
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        return f"抱歉，无法处理您的请求: {e}"


INTENT_HANDLERS: dict[Intent, callable] = {
    Intent.GITHUB_SEARCH: handle_github_search,
    Intent.KNOWLEDGE_QUERY: handle_knowledge_query,
    Intent.GENERAL_CHAT: handle_general_chat,
}


def route(query: str) -> str:
    """统一入口函数，路由用户查询到对应处理器。

    Args:
        query: 用户查询文本。

    Returns:
        处理结果。
    """
    if not query or not query.strip():
        return "请输入有效的查询内容。"

    logger.info(f"处理查询: {query[:50]}...")

    intent_result = classify_intent(query)
    logger.info(f"意图识别: {intent_result.intent.value} (置信度: {intent_result.confidence}, 来源: {intent_result.source})")

    handler = INTENT_HANDLERS.get(intent_result.intent)
    if not handler:
        logger.warning(f"未找到意图处理器: {intent_result.intent}")
        handler = handle_general_chat

    return handler(query)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_query = " ".join(sys.argv[1:])
        print(f"查询: {user_query}")
        print("-" * 60)
        result = route(user_query)
        print(result)
    else:
        test_queries = [
            "帮我搜索 GitHub 上关于 AI agent 的热门项目",
            "知识库里有什么关于 workflow 的条目？",
            "今天天气怎么样？",
            "推荐一些好用的 Python 库",
        ]

        print("=" * 60)
        print("Router 路由模式测试")
        print("=" * 60)

        for i, test_query in enumerate(test_queries, 1):
            print(f"\n测试 {i}: {test_query}")
            print("-" * 40)
            result = route(test_query)
            if len(result) > 500:
                print(result[:500] + "...")
            else:
                print(result)

        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)

"""
MCP Knowledge Server - 为 AI 工具提供本地知识库搜索能力

提供三个工具：
- search_articles: 按关键词/来源/标签/评分搜索文章
- get_article: 按 ID 获取文章详情
- knowledge_stats: 获取知识库统计信息
"""

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route, Mount
import uvicorn

ARTICLES_DIR = Path(__file__).parent.parent / "knowledge" / "articles"
app = Server("knowledge-server")


def load_all_articles() -> list[dict[str, Any]]:
    """加载所有知识条目"""
    articles = []
    if not ARTICLES_DIR.exists():
        return articles

    for json_file in ARTICLES_DIR.glob("*.json"):
        if json_file.name == "index.json":
            continue
        try:
            with open(json_file, encoding="utf-8") as f:
                article = json.load(f)
                articles.append(article)
        except (json.JSONDecodeError, IOError):
            continue

    return articles


@app.list_tools()
async def list_tools() -> list[Tool]:
    """返回可用工具列表"""
    return [
        Tool(
            name="search_articles",
            description="搜索知识库文章，支持按关键词、来源、标签、最低评分过滤，各参数可组合使用，至少提供一个过滤条件",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，匹配标题、摘要、标签"
                    },
                    "source": {
                        "type": "string",
                        "description": "按来源过滤，可选值: github-search, github-trending, rss"
                    },
                    "tag": {
                        "type": "string",
                        "description": "按标签过滤，精确匹配标签名，如 agent-framework, python, llm"
                    },
                    "min_score": {
                        "type": "integer",
                        "description": "最低相关度评分过滤，只返回 relevance_score >= min_score 的文章，取值 1-10"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量限制，默认10",
                        "default": 10
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_article",
            description="根据文章 ID 获取完整内容",
            inputSchema={
                "type": "object",
                "properties": {
                    "article_id": {
                        "type": "string",
                        "description": "文章唯一标识符"
                    }
                },
                "required": ["article_id"]
            }
        ),
        Tool(
            name="knowledge_stats",
            description="获取知识库统计信息，包括文章总数、来源分布、热门标签",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """执行工具调用"""
    articles = load_all_articles()

    if name == "search_articles":
        return _search_articles(articles, arguments)
    elif name == "get_article":
        return _get_article(articles, arguments)
    elif name == "knowledge_stats":
        return _knowledge_stats(articles)
    else:
        return [TextContent(type="text", text=f"未知工具: {name}")]


def _search_articles(articles: list[dict], arguments: dict) -> list[TextContent]:
    """搜索文章"""
    keyword = arguments.get("keyword", "")
    source_filter = arguments.get("source", "")
    tag_filter = arguments.get("tag", "")
    min_score = arguments.get("min_score")
    limit = arguments.get("limit", 10)

    has_filter = keyword or source_filter or tag_filter or min_score is not None
    if not has_filter:
        return [TextContent(type="text", text="请至少提供一个过滤条件: keyword, source, tag, min_score")]

    pattern = re.compile(re.escape(keyword), re.IGNORECASE) if keyword else None
    results = []

    for article in articles:
        if source_filter:
            if article.get("source", "").lower() != source_filter.lower():
                continue

        if tag_filter:
            article_tags = [t.lower() for t in article.get("tags", [])]
            if tag_filter.lower() not in article_tags:
                continue

        if min_score is not None:
            score = article.get("relevance_score")
            if score is None or score < min_score:
                continue

        if pattern:
            title = article.get("title", "")
            summary = article.get("summary", "")
            tags = article.get("tags", [])

            if not (pattern.search(title) or
                    pattern.search(summary) or
                    any(pattern.search(tag) for tag in tags)):
                continue

        summary_text = article.get("summary", "") or ""
        results.append({
            "id": article.get("id"),
            "title": article.get("title", ""),
            "source": article.get("source"),
            "relevance_score": article.get("relevance_score"),
            "tags": article.get("tags", []),
            "summary": summary_text[:200] + "..." if len(summary_text) > 200 else summary_text
        })

    results = results[:limit]

    if not results:
        parts = []
        if keyword:
            parts.append(f"关键词='{keyword}'")
        if source_filter:
            parts.append(f"来源='{source_filter}'")
        if tag_filter:
            parts.append(f"标签='{tag_filter}'")
        if min_score is not None:
            parts.append(f"最低评分={min_score}")
        return [TextContent(type="text", text=f"未找到匹配 [{', '.join(parts)}] 的文章")]

    return [TextContent(
        type="text",
        text=json.dumps(results, ensure_ascii=False, indent=2)
    )]


def _get_article(articles: list[dict], arguments: dict) -> list[TextContent]:
    """获取单篇文章"""
    article_id = arguments.get("article_id")

    if not article_id:
        return [TextContent(type="text", text="请提供文章 ID")]

    for article in articles:
        if article.get("id") == article_id:
            return [TextContent(
                type="text",
                text=json.dumps(article, ensure_ascii=False, indent=2)
            )]

    return [TextContent(type="text", text=f"未找到 ID 为 '{article_id}' 的文章")]


def _knowledge_stats(articles: list[dict]) -> list[TextContent]:
    """获取统计信息"""
    total = len(articles)

    sources: dict[str, int] = {}
    tag_counts: dict[str, int] = {}

    for article in articles:
        source = article.get("source", "unknown")
        sources[source] = sources.get(source, 0) + 1

        for tag in article.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    stats = {
        "total_articles": total,
        "sources": sources,
        "top_tags": [{"tag": tag, "count": count} for tag, count in top_tags]
    }

    return [TextContent(
        type="text",
        text=json.dumps(stats, ensure_ascii=False, indent=2)
    )]


sse = SseServerTransport("/messages/")


async def handle_sse(request):
    """处理 SSE 连接 (GET)"""
    async with sse.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await app.run(
            streams[0], streams[1], app.create_initialization_options()
        )
    return Response()


starlette_app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ]
)


def main():
    """启动服务器"""
    parser = argparse.ArgumentParser(description="MCP Knowledge Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="sse",
        help="传输模式: stdio (本地) 或 sse (远程)"
    )
    args = parser.parse_args()

    print(f"知识库目录: {ARTICLES_DIR}", file=__import__("sys").stderr)
    print(f"已加载文章数: {len(load_all_articles())}", file=__import__("sys").stderr)

    if args.transport == "stdio":
        print("MCP Server 启动中 (stdio 模式)...", file=__import__("sys").stderr)
        asyncio.run(run_stdio())
    else:
        print("MCP Server 启动中 (SSE 模式)...", file=__import__("sys").stderr)
        print("SSE 端点: http://localhost:8000/sse", file=__import__("sys").stderr)
        uvicorn.run(starlette_app, host="0.0.0.0", port=8000)


async def run_stdio():
    """stdio 模式运行"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    main()

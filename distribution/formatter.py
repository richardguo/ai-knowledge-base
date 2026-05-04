"""知识条目格式化模块，将文章 JSON 转换为 Markdown / 飞书卡片 / Telegram 等输出格式。"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any


def _score_indicator(score: int) -> str:
    """根据相关性评分返回 emoji 指示符。

    Args:
        score: 相关性评分（0-10）。

    Returns:
        对应的 emoji 指示符：🟢 >= 8 / 🟡 >= 6 / 🔴 < 6。
    """
    if score >= 8:
        return "🟢"
    if score >= 6:
        return "🟡"
    return "🔴"


def _score_color(score: int) -> str:
    """根据相关性评分返回飞书卡片 header 模板颜色。

    Args:
        score: 相关性评分（0-10）。

    Returns:
        飞书 header template 值：green / yellow / red。
    """
    if score >= 8:
        return "green"
    if score >= 6:
        return "yellow"
    return "red"


def json_to_markdown(article: dict[str, Any]) -> str:
    """将单篇知识条目转换为 Markdown 格式。

    Args:
        article: 知识条目字典，需包含 title / url / source /
            collected_at / relevance_score / tags / summary 字段。

    Returns:
        Markdown 格式字符串。
    """
    title = article["title"]
    source = article["source"]
    collected_date = article["collected_at"][:10]
    score = article["relevance_score"]
    tags = article.get("tags", [])
    summary = article["summary"]
    url = article["url"]

    lines = [
        f"## {title}",
        f"**来源**: {source} | **日期**: {collected_date} | **相关性**: {score}/10 {_score_indicator(score)}",
    ]
    if tags:
        lines.append(f"**标签**: {', '.join(tags)}")
    lines.extend(["", summary, "", f"[原文链接]({url})"])

    return "\n".join(lines)


def _build_feishu_elements(article: dict[str, Any]) -> list[dict[str, Any]]:
    """构建单篇文章的飞书卡片元素列表。

    Args:
        article: 知识条目字典。

    Returns:
        飞书卡片 elements 列表。
    """
    source = article["source"]
    collected_date = article["collected_at"][:10]
    score = article["relevance_score"]
    tags = article.get("tags", [])
    summary = article["summary"]
    url = article["url"]
    highlights = article.get("highlights", [])
    category = article.get("category", "")
    maturity = article.get("maturity", "")

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**来源**: {source} | **日期**: {collected_date} "
                    f"| **相关性**: {score}/10 {_score_indicator(score)}"
                ),
            },
        }
    ]

    meta_parts: list[str] = []
    if category:
        meta_parts.append(f"**分类**: {category}")
    if maturity:
        meta_parts.append(f"**成熟度**: {maturity}")
    if tags:
        meta_parts.append(f"**标签**: {', '.join(tags)}")
    if meta_parts:
        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": " | ".join(meta_parts)},
            }
        )

    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": summary}})

    if highlights:
        highlight_text = "\n".join(f"▸ {h}" for h in highlights)
        elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": highlight_text}}
        )

    elements.append(
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看原文"},
                    "url": url,
                    "type": "primary",
                }
            ],
        }
    )

    return elements


def json_to_feishu(article: dict[str, Any]) -> dict[str, Any]:
    """将单篇知识条目转换为飞书 interactive 卡片格式。

    Args:
        article: 知识条目字典。

    Returns:
        飞书消息体字典（msg_type=interactive），header.template 按
        relevance_score 染色：green(>=8) / yellow(>=6) / red(<6)。
    """
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "template": _score_color(article["relevance_score"]),
                "title": {"tag": "plain_text", "content": article["title"]},
            },
            "elements": _build_feishu_elements(article),
        },
    }


def _article_to_telegram(article: dict[str, Any]) -> str:
    """将单篇知识条目转换为 Telegram HTML 格式。

    Args:
        article: 知识条目字典。

    Returns:
        Telegram HTML 格式字符串。
    """
    title = article["title"]
    source = article["source"]
    collected_date = article["collected_at"][:10]
    score = article["relevance_score"]
    tags = article.get("tags", [])
    summary = article["summary"]
    url = article["url"]

    lines = [
        f"📌 <b>{title}</b>",
        f"📡 {source} | 📅 {collected_date} | ⭐ {score}/10 {_score_indicator(score)}",
    ]
    if tags:
        lines.append(f"🏷 {' '.join(f'#{t}' for t in tags)}")
    lines.extend(["", summary, "", f'🔗 <a href="{url}">原文链接</a>'])

    return "\n".join(lines)


def generate_daily_digest(
    knowledge_dir: str = "knowledge/articles",
    date: dt.date | str | None = None,
    top_n: int = 5,
) -> dict[str, Any] | str:
    """生成每日知识简报，包含 Markdown / Telegram / 飞书三种格式。

    按 relevance_score 降序取 Top N 篇，组合为三种输出格式的简报。

    Args:
        knowledge_dir: 知识条目目录路径。
        date: 目标日期，支持 ``datetime.date`` 或 ``"YYYY-MM-DD"`` 字符串，
            默认为今天。
        top_n: 取相关性评分最高的 N 篇。

    Returns:
        包含 markdown / telegram / feishu 键的字典；
        当日无文章时返回提示字符串。
    """
    if date is None:
        target_date = dt.date.today()
    elif isinstance(date, str):
        target_date = dt.date.fromisoformat(date)
    else:
        target_date = date
    articles_dir = Path(knowledge_dir)

    articles: list[dict[str, Any]] = []
    for path in articles_dir.glob(f"{target_date.isoformat()}-*.json"):
        with path.open(encoding="utf-8") as f:
            articles.append(json.load(f))

    if not articles:
        return f"📭 {target_date.isoformat()} 暂无新增知识条目"

    articles.sort(key=lambda a: a["relevance_score"], reverse=True)
    articles = articles[:top_n]

    date_str = target_date.isoformat()
    md_sections = [json_to_markdown(a) for a in articles]
    tg_sections = [_article_to_telegram(a) for a in articles]

    feishu_elements: list[dict[str, Any]] = []
    for i, article in enumerate(articles):
        if i > 0:
            feishu_elements.append({"tag": "hr"})
        feishu_elements.extend(_build_feishu_elements(article))

    return {
        "markdown": f"# AI 知识日报 · {date_str}\n\n" + "\n\n---\n\n".join(md_sections),
        "telegram": f"📰 <b>AI 知识日报</b> · {date_str}\n\n"
        + "\n\n".join(tg_sections),
        "feishu": {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "template": "blue",
                    "title": {
                        "tag": "plain_text",
                        "content": f"AI 知识日报 · {date_str}",
                    },
                },
                "elements": feishu_elements,
            },
        },
    }

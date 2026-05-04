"""知识简报推送模块，通过各渠道 Webhook 发布每日知识日报。"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import aiohttp
from dotenv import load_dotenv

from distribution.formatter import generate_daily_digest

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    """单次发布结果记录。

    Attributes:
        channel: 发布渠道名称（如 ``feishu``）。
        success: 是否发布成功。
        message_id: 消息唯一标识（成功时由平台返回）。
        error: 失败原因（成功时为空字符串）。
    """

    channel: str
    success: bool
    message_id: str = ""
    error: str = ""


class BasePublisher(ABC):
    """发布者抽象基类，定义统一的消息发送接口。"""

    @abstractmethod
    async def send_message(self, payload: dict[str, Any]) -> PublishResult:
        """发送单条消息到对应渠道。

        Args:
            payload: 渠道所需的完整消息体。

        Returns:
            发布结果。
        """

    @abstractmethod
    async def send_digest(self, digest: dict[str, Any]) -> PublishResult:
        """从简报字典中提取对应渠道内容并发送。

        Args:
            digest: ``generate_daily_digest()`` 返回的简报字典，
                包含 ``markdown`` / ``telegram`` / ``feishu`` 键。

        Returns:
            发布结果。
        """


class FeishuPublisher(BasePublisher):
    """飞书 Webhook 发布者，通过自定义机器人 Webhook 发送 interactive 卡片。

    Args:
        webhook_url: 飞书自定义机器人 Webhook 地址。
            默认从环境变量 ``FEISHU_WEBHOOK_URL`` 读取。
    """

    def __init__(self, webhook_url: str | None = None) -> None:
        self._webhook_url = webhook_url or os.environ.get("FEISHU_WEBHOOK_URL", "")

    async def send_message(self, payload: dict[str, Any]) -> PublishResult:
        """发送飞书消息体到 Webhook。

        Args:
            payload: 飞书消息体，需包含 ``msg_type`` 和对应内容字段。

        Returns:
            发布结果，成功时 ``message_id`` 为飞书返回的消息 ID。
        """
        if not self._webhook_url:
            return PublishResult(
                channel="feishu",
                success=False,
                error="FEISHU_WEBHOOK_URL 未配置",
            )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self._webhook_url, json=payload) as resp:
                    body = await resp.json()
        except Exception as exc:
            logger.exception("飞书 Webhook 请求失败")
            return PublishResult(channel="feishu", success=False, error=str(exc))

        if body.get("code") == 0:
            return PublishResult(
                channel="feishu",
                success=True,
                message_id=str(body.get("data", {}).get("message_id", "")),
            )

        return PublishResult(
            channel="feishu",
            success=False,
            error=body.get("msg", "未知错误"),
        )

    async def send_digest(self, digest: dict[str, Any]) -> PublishResult:
        """发送飞书格式的每日简报卡片。

        Args:
            digest: ``generate_daily_digest()`` 返回的简报字典。

        Returns:
            发布结果。
        """
        return await self.send_message(digest["feishu"])


_CHANNEL_REGISTRY: dict[str, type[BasePublisher]] = {
    "feishu": FeishuPublisher,
}


def _escape_lark_md(text: str) -> str:
    """转义飞书 lark_md 中的特殊字符，避免被误解析为 Markdown。

    飞书 lark_md 中 ``*`` / ``_`` / ``~`` / ``>`` 等字符成对出现时
    会被渲染为加粗/斜体/删除线/引用。对纯文本内容进行转义可保证原样显示。

    Args:
        text: 原始文本。

    Returns:
        转义后的文本。
    """
    return re.sub(r"([*_~>`#])", r"\\\1", text)


def _format_feishu_custom(message: str | dict[str, Any]) -> dict[str, Any]:
    """将自定义消息格式化为飞书 interactive 卡片消息体。

    - 字符串消息：转义 lark_md 特殊字符后以纯文本渲染。
    - 字典消息：pretty-print 后放入代码块，保持结构可读。

    Args:
        message: 字符串或字典形式的自定义消息。

    Returns:
        飞书消息体字典。
    """
    if isinstance(message, dict):
        content = json.dumps(message, ensure_ascii=False, indent=2)
        body = f"```\n{content}\n```"
    else:
        body = _escape_lark_md(str(message))

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": "AI 知识库通知"},
            },
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": body}}],
        },
    }


_CUSTOM_FORMATTERS: dict[str, Callable[[str | dict[str, Any]], dict[str, Any]]] = {
    "feishu": _format_feishu_custom,
}


def _build_publishers(channels: list[str] | None = None) -> list[BasePublisher]:
    """根据渠道名称列表构建发布者实例。

    Args:
        channels: 渠道名称列表，默认为 ``["feishu"]``。

    Returns:
        发布者实例列表。
    """
    names = channels if channels is not None else ["feishu"]
    publishers: list[BasePublisher] = []
    for name in names:
        cls = _CHANNEL_REGISTRY.get(name)
        if cls is None:
            logger.warning("未知渠道: %s，已跳过", name)
            continue
        publishers.append(cls())
    return publishers


async def publish_daily_digest(
    knowledge_dir: str = "knowledge/articles",
    date: dt.date | str | None = None,
    top_n: int = 5,
    channel: list[str] | None = None,
    publishers: list[BasePublisher] | None = None,
) -> list[PublishResult]:
    """统一异步入口：生成简报并并发推送到所有渠道。

    Args:
        knowledge_dir: 知识条目目录路径。
        date: 目标日期，支持 ``datetime.date`` 或 ``"YYYY-MM-DD"`` 字符串，
            默认为今天。
        top_n: 取相关性评分最高的 N 篇。
        channel: 渠道名称列表，默认为 ``["feishu"]``。
        publishers: 发布者实例列表，传入时忽略 ``channel`` 参数。

    Returns:
        各渠道的发布结果列表。
    """
    digest = generate_daily_digest(knowledge_dir=knowledge_dir, date=date, top_n=top_n)

    if isinstance(digest, str):
        logger.info(digest)
        return []

    active_publishers = (
        publishers if publishers is not None else _build_publishers(channel)
    )
    if not active_publishers:
        logger.warning("未配置任何推送渠道，跳过发布")
        return []

    tasks = [p.send_digest(digest) for p in active_publishers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    publish_results: list[PublishResult] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            channel = type(active_publishers[i]).__name__
            publish_results.append(
                PublishResult(channel=channel, success=False, error=str(result))
            )
        else:
            publish_results.append(result)

    return publish_results


async def publish_custom_info(
    message: str | dict[str, Any],
    channel: list[str] | None = None,
    publishers: list[tuple[str, BasePublisher, Callable]] | None = None,
) -> list[PublishResult]:
    """发布自定义消息到指定渠道。

    将用户输入的字符串或 JSON 直接推送到目标渠道。字符串消息会转义
    Markdown 特殊字符以确保原样显示；字典消息会 pretty-print 到代码块中
    以保持结构可读。

    Args:
        message: 字符串或字典形式的自定义消息。
        channel: 渠道名称列表，默认为 ``["feishu"]``。
        publishers: ``(channel_name, publisher, formatter)`` 三元组列表，
            传入时忽略 ``channel`` 参数，用于测试注入。

    Returns:
        各渠道的发布结果列表。
    """
    if publishers is not None:
        pairs = publishers
    else:
        channels = channel or ["feishu"]
        pairs = []
        for name in channels:
            cls = _CHANNEL_REGISTRY.get(name)
            if cls is None:
                logger.warning("未知渠道: %s，已跳过", name)
                continue
            formatter = _CUSTOM_FORMATTERS.get(name)
            if formatter is None:
                logger.warning("渠道 %s 暂不支持自定义消息，已跳过", name)
                continue
            pairs.append((name, cls(), formatter))

    if not pairs:
        logger.warning("无可用的推送渠道，跳过发布")
        return []

    tasks = [pub.send_message(formatter(message)) for _, pub, formatter in pairs]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    publish_results: list[PublishResult] = []
    for i, result in enumerate(results):
        ch_name = pairs[i][0]
        if isinstance(result, Exception):
            publish_results.append(
                PublishResult(channel=ch_name, success=False, error=str(result))
            )
        else:
            publish_results.append(result)

    return publish_results

"""publisher 模块集成测试——真实推送飞书消息。"""

import asyncio
import os

import pytest

from distribution.formatter import json_to_feishu
from distribution.publisher import (
    FeishuPublisher,
    PublishResult,
    publish_custom_info,
    publish_daily_digest,
)

SAMPLE_ARTICLE = {
    "id": "integration-test-001",
    "title": "Integration Test Project",
    "url": "https://github.com/test/integration-test",
    "source": "github-search",
    "collected_at": "2026-05-03T08:05:50+08:00",
    "processed_at": "2026-05-03T08:09:01+08:00",
    "summary": "这是一条集成测试消息，验证飞书 Webhook 推送是否正常。",
    "highlights": ["集成测试验证"],
    "relevance_score": 8,
    "tags": ["test"],
    "category": "测试",
    "maturity": "测试",
}


@pytest.mark.integration
class TestFeishuPublisherIntegration:
    """真实飞书 Webhook 推送测试。"""

    @pytest.mark.skipif(
        not os.getenv("FEISHU_WEBHOOK_URL"),
        reason="FEISHU_WEBHOOK_URL 未配置",
    )
    @pytest.mark.asyncio
    async def test_send_single_card(self) -> None:
        """发送单篇飞书卡片消息。"""
        publisher = FeishuPublisher()
        payload = json_to_feishu(SAMPLE_ARTICLE)
        result = await publisher.send_message(payload)

        assert result.channel == "feishu"
        assert result.success is True, f"推送失败: {result.error}"

    @pytest.mark.skipif(
        not os.getenv("FEISHU_WEBHOOK_URL"),
        reason="FEISHU_WEBHOOK_URL 未配置",
    )
    @pytest.mark.asyncio
    async def test_publish_daily_digest_real(self) -> None:
        """通过 publish_daily_digest 真实推送每日简报。"""
        results = await publish_daily_digest(
            date="2026-04-23",
            top_n=3,
            channel=["feishu"],
        )

        assert len(results) >= 1
        assert results[0].channel == "feishu"
        assert results[0].success is True, f"推送失败: {results[0].error}"

    @pytest.mark.skipif(
        not os.getenv("FEISHU_WEBHOOK_URL"),
        reason="FEISHU_WEBHOOK_URL 未配置",
    )
    @pytest.mark.asyncio
    async def test_publish_custom_info_string(self) -> None:
        """真实推送字符串自定义消息。"""
        results = await publish_custom_info(
            "这是一条自定义通知消息，验证 publish_custom_info 字符串推送。",
            channel=["feishu"],
        )

        assert len(results) == 1
        assert results[0].channel == "feishu"
        assert results[0].success is True, f"推送失败: {results[0].error}"

    @pytest.mark.skipif(
        not os.getenv("FEISHU_WEBHOOK_URL"),
        reason="FEISHU_WEBHOOK_URL 未配置",
    )
    @pytest.mark.asyncio
    async def test_publish_custom_info_dict(self) -> None:
        """真实推送字典自定义消息。"""
        results = await publish_custom_info(
            {"event": "pipeline_complete", "status": "success", "count": 42},
            channel=["feishu"],
        )

        assert len(results) == 1
        assert results[0].channel == "feishu"
        assert results[0].success is True, f"推送失败: {results[0].error}"

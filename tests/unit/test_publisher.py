"""publisher 模块单元测试。"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from distribution.publisher import (
    BasePublisher,
    FeishuPublisher,
    PublishResult,
    _build_publishers,
    _escape_lark_md,
    _format_feishu_custom,
    publish_custom_info,
    publish_daily_digest,
)

SAMPLE_ARTICLE: dict[str, Any] = {
    "id": "test-001",
    "title": "test-project",
    "url": "https://github.com/test/test-project",
    "source": "github-search",
    "collected_at": "2026-05-03T08:05:50+08:00",
    "processed_at": "2026-05-03T08:09:01+08:00",
    "summary": "测试摘要",
    "highlights": ["亮点一", "亮点二"],
    "relevance_score": 8,
    "tags": ["agent-framework"],
    "category": "工具",
    "maturity": "生产",
}

SAMPLE_ARTICLE_LOW: dict[str, Any] = {
    **SAMPLE_ARTICLE,
    "id": "test-002",
    "title": "low-score-project",
    "relevance_score": 4,
}


class TestPublishResult:
    """PublishResult 数据类测试。"""

    def test_success_result(self) -> None:
        result = PublishResult(channel="feishu", success=True, message_id="msg_123")
        assert result.channel == "feishu"
        assert result.success is True
        assert result.message_id == "msg_123"
        assert result.error == ""

    def test_failure_result(self) -> None:
        result = PublishResult(channel="feishu", success=False, error="timeout")
        assert result.success is False
        assert result.error == "timeout"
        assert result.message_id == ""


class TestFeishuPublisher:
    """FeishuPublisher 测试。"""

    def test_init_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://example.com/webhook")
        pub = FeishuPublisher()
        assert pub._webhook_url == "https://example.com/webhook"

    def test_init_from_param(self) -> None:
        pub = FeishuPublisher(webhook_url="https://custom.url/hook")
        assert pub._webhook_url == "https://custom.url/hook"

    def test_init_no_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FEISHU_WEBHOOK_URL", raising=False)
        pub = FeishuPublisher()
        assert pub._webhook_url == ""

    @pytest.mark.asyncio
    async def test_send_message_no_webhook(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FEISHU_WEBHOOK_URL", raising=False)
        pub = FeishuPublisher()
        result = await pub.send_message({"msg_type": "text", "content": {"text": "hi"}})
        assert result.channel == "feishu"
        assert result.success is False
        assert "FEISHU_WEBHOOK_URL" in result.error

    @pytest.mark.asyncio
    async def test_send_message_success(self) -> None:
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(
            return_value={"code": 0, "data": {"message_id": "msg_abc"}}
        )
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "distribution.publisher.aiohttp.ClientSession", return_value=mock_session
        ):
            pub = FeishuPublisher(webhook_url="https://example.com/hook")
            result = await pub.send_message({"msg_type": "interactive", "card": {}})

        assert result.success is True
        assert result.message_id == "msg_abc"

    @pytest.mark.asyncio
    async def test_send_message_api_error(self) -> None:
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(
            return_value={"code": 19001, "msg": "invalid webhook"}
        )
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "distribution.publisher.aiohttp.ClientSession", return_value=mock_session
        ):
            pub = FeishuPublisher(webhook_url="https://example.com/hook")
            result = await pub.send_message(
                {"msg_type": "text", "content": {"text": "hi"}}
            )

        assert result.success is False
        assert "invalid webhook" in result.error

    @pytest.mark.asyncio
    async def test_send_message_network_error(self) -> None:
        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=ConnectionError("network down"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "distribution.publisher.aiohttp.ClientSession", return_value=mock_session
        ):
            pub = FeishuPublisher(webhook_url="https://example.com/hook")
            result = await pub.send_message(
                {"msg_type": "text", "content": {"text": "hi"}}
            )

        assert result.success is False
        assert "network down" in result.error

    @pytest.mark.asyncio
    async def test_send_digest(self) -> None:
        pub = FeishuPublisher(webhook_url="")
        pub.send_message = AsyncMock(
            return_value=PublishResult(channel="feishu", success=True, message_id="m1")
        )

        digest = {"feishu": {"msg_type": "interactive", "card": {}}}
        result = await pub.send_digest(digest)

        pub.send_message.assert_awaited_once_with(digest["feishu"])
        assert result.success is True


class TestBuildPublishers:
    """_build_publishers 测试。"""

    def test_default_returns_feishu(self) -> None:
        pubs = _build_publishers()
        assert len(pubs) == 1
        assert isinstance(pubs[0], FeishuPublisher)

    def test_explicit_feishu(self) -> None:
        pubs = _build_publishers(["feishu"])
        assert len(pubs) == 1
        assert isinstance(pubs[0], FeishuPublisher)

    def test_unknown_channel_skipped(self) -> None:
        pubs = _build_publishers(["telegram", "feishu"])
        assert len(pubs) == 1
        assert isinstance(pubs[0], FeishuPublisher)

    def test_empty_channels(self) -> None:
        pubs = _build_publishers([])
        assert pubs == []


class TestPublishDailyDigest:
    """publish_daily_digest 集成测试。"""

    @pytest.mark.asyncio
    async def test_empty_date(self) -> None:
        results = await publish_daily_digest(date="2099-01-01")
        assert results == []

    @pytest.mark.asyncio
    async def test_with_real_data_mocked_publisher(self, tmp_path: Path) -> None:
        article_dir = tmp_path / "articles"
        article_dir.mkdir()
        article_file = article_dir / "2026-05-03-test-project.json"
        article_file.write_text(
            json.dumps(SAMPLE_ARTICLE, ensure_ascii=False), encoding="utf-8"
        )

        mock_pub = AsyncMock(spec=BasePublisher)
        mock_pub.send_digest = AsyncMock(
            return_value=PublishResult(channel="feishu", success=True, message_id="m1")
        )

        results = await publish_daily_digest(
            knowledge_dir=str(article_dir),
            date="2026-05-03",
            publishers=[mock_pub],
        )

        assert len(results) == 1
        assert results[0].success is True
        mock_pub.send_digest.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multiple_publishers(self, tmp_path: Path) -> None:
        article_dir = tmp_path / "articles"
        article_dir.mkdir()
        article_file = article_dir / "2026-05-03-test-project.json"
        article_file.write_text(
            json.dumps(SAMPLE_ARTICLE, ensure_ascii=False), encoding="utf-8"
        )

        mock_a = AsyncMock(spec=BasePublisher)
        mock_a.send_digest = AsyncMock(
            return_value=PublishResult(channel="a", success=True)
        )
        mock_b = AsyncMock(spec=BasePublisher)
        mock_b.send_digest = AsyncMock(
            return_value=PublishResult(channel="b", success=False, error="fail")
        )

        results = await publish_daily_digest(
            knowledge_dir=str(article_dir),
            date="2026-05-03",
            publishers=[mock_a, mock_b],
        )

        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is False

    @pytest.mark.asyncio
    async def test_publisher_exception_handled(self, tmp_path: Path) -> None:
        article_dir = tmp_path / "articles"
        article_dir.mkdir()
        article_file = article_dir / "2026-05-03-test-project.json"
        article_file.write_text(
            json.dumps(SAMPLE_ARTICLE, ensure_ascii=False), encoding="utf-8"
        )

        mock_pub = AsyncMock(spec=BasePublisher)
        mock_pub.send_digest = AsyncMock(side_effect=RuntimeError("boom"))

        results = await publish_daily_digest(
            knowledge_dir=str(article_dir),
            date="2026-05-03",
            publishers=[mock_pub],
        )

        assert len(results) == 1
        assert results[0].success is False
        assert "boom" in results[0].error

    @pytest.mark.asyncio
    async def test_no_publishers(self, tmp_path: Path) -> None:
        article_dir = tmp_path / "articles"
        article_dir.mkdir()
        article_file = article_dir / "2026-05-03-test-project.json"
        article_file.write_text(
            json.dumps(SAMPLE_ARTICLE, ensure_ascii=False), encoding="utf-8"
        )

        results = await publish_daily_digest(
            knowledge_dir=str(article_dir),
            date="2026-05-03",
            publishers=[],
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_channel_param(self, tmp_path: Path) -> None:
        article_dir = tmp_path / "articles"
        article_dir.mkdir()
        article_file = article_dir / "2026-05-03-test-project.json"
        article_file.write_text(
            json.dumps(SAMPLE_ARTICLE, ensure_ascii=False), encoding="utf-8"
        )

        with patch("distribution.publisher._build_publishers") as mock_build:
            mock_build.return_value = [
                FeishuPublisher(webhook_url="https://example.com/hook")
            ]
            with patch.object(FeishuPublisher, "send_message") as mock_send:
                mock_send.return_value = PublishResult(
                    channel="feishu", success=True, message_id="m1"
                )
                results = await publish_daily_digest(
                    knowledge_dir=str(article_dir),
                    date="2026-05-03",
                    channel=["feishu"],
                )

        mock_build.assert_called_once_with(["feishu"])
        assert len(results) == 1


class TestEscapeLarkMd:
    """_escape_lark_md 测试。"""

    def test_escape_asterisk(self) -> None:
        assert _escape_lark_md("*bold*") == r"\*bold\*"

    def test_escape_underscore(self) -> None:
        assert _escape_lark_md("_italic_") == r"\_italic\_"

    def test_escape_tilde(self) -> None:
        assert _escape_lark_md("~strike~") == r"\~strike\~"

    def test_escape_gt(self) -> None:
        assert _escape_lark_md(">quote") == r"\>quote"

    def test_no_escape_plain_text(self) -> None:
        assert _escape_lark_md("hello world") == "hello world"


class TestFormatFeishuCustom:
    """_format_feishu_custom 测试。"""

    def test_string_message(self) -> None:
        payload = _format_feishu_custom("hello world")
        assert payload["msg_type"] == "interactive"
        card = payload["card"]
        assert card["header"]["template"] == "blue"
        content = card["elements"][0]["text"]["content"]
        assert "hello world" in content

    def test_string_with_special_chars_escaped(self) -> None:
        payload = _format_feishu_custom("price *100* > 50")
        content = payload["card"]["elements"][0]["text"]["content"]
        assert r"\*" in content
        assert r"\>" in content

    def test_dict_message_in_code_block(self) -> None:
        payload = _format_feishu_custom({"key": "value", "n": 1})
        content = payload["card"]["elements"][0]["text"]["content"]
        assert "```" in content
        assert '"key": "value"' in content

    def test_dict_message_pretty_printed(self) -> None:
        payload = _format_feishu_custom({"a": 1})
        content = payload["card"]["elements"][0]["text"]["content"]
        assert "\n" in content


class TestPublishCustomInfo:
    """publish_custom_info 测试。"""

    @pytest.mark.asyncio
    async def test_default_channel(self) -> None:
        mock_pub = AsyncMock(spec=BasePublisher)
        mock_pub.send_message = AsyncMock(
            return_value=PublishResult(channel="feishu", success=True)
        )

        results = await publish_custom_info(
            "test message",
            publishers=[("feishu", mock_pub, _format_feishu_custom)],
        )

        assert len(results) == 1
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_dict_message(self) -> None:
        mock_pub = AsyncMock(spec=BasePublisher)
        mock_pub.send_message = AsyncMock(
            return_value=PublishResult(channel="feishu", success=True)
        )

        results = await publish_custom_info(
            {"status": "ok"},
            publishers=[("feishu", mock_pub, _format_feishu_custom)],
        )

        assert len(results) == 1
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_unknown_channel_skipped(self) -> None:
        results = await publish_custom_info("test", channel=["telegram"])
        assert results == []

    @pytest.mark.asyncio
    async def test_exception_handled(self) -> None:
        mock_pub = AsyncMock(spec=BasePublisher)
        mock_pub.send_message = AsyncMock(side_effect=RuntimeError("fail"))

        results = await publish_custom_info(
            "test",
            publishers=[("feishu", mock_pub, _format_feishu_custom)],
        )

        assert len(results) == 1
        assert results[0].success is False
        assert "fail" in results[0].error

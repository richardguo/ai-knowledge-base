"""llm_retry 装饰器的集成测试。

测试真实 LLM API 调用场景。
需要配置环境变量：LLM_API_BASE, LLM_API_KEY, LLM_MODEL_ID 或
ZHIPU_API_BASE_URL, ZHIPU_API_KEY, ZHIPU_MODEL_ID
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

from utils import LLMError, llm_retry

logger = logging.getLogger(__name__)


def get_test_config() -> dict[str, str | None]:
    """获取测试配置。

    优先使用 ZHIPU 配置（更容易触发 RateLimit），
    其次使用通用 LLM 配置。

    Returns:
        包含 api_base, api_key, model 的字典。
    """
    config = {
        "api_base": os.getenv("ZHIPU_API_BASE_URL")
        or os.getenv("LLM_API_BASE"),
        "api_key": os.getenv("ZHIPU_API_KEY") or os.getenv("LLM_API_KEY"),
        "model": os.getenv("ZHIPU_MODEL_ID") or os.getenv("LLM_MODEL_ID"),
    }
    return config


def has_api_config() -> bool:
    """检查是否有 API 配置。

    Returns:
        是否配置了必要的 API 参数。
    """
    config = get_test_config()
    return all(config.values())


pytestmark = pytest.mark.skipif(
    not has_api_config(),
    reason="未配置 API 环境变量 (ZHIPU_API_BASE_URL/ZHIPU_API_KEY/ZHIPU_MODEL_ID 或 LLM_API_BASE/LLM_API_KEY/LLM_MODEL_ID)",
)


@pytest.fixture
def test_provider() -> Any:
    """创建测试用的 LLM 提供商。

    Returns:
        OpenAICompatibleProvider 实例。
    """
    from pipeline.model_client import OpenAICompatibleProvider

    config = get_test_config()
    return OpenAICompatibleProvider(
        api_base=config["api_base"],
        api_key=config["api_key"],
        default_model=config["model"],
    )


class TestRealAPICall:
    """真实 API 调用测试。"""

    def test_successful_api_call(self, test_provider: Any) -> None:
        """测试真实调用 LLM API 成功。"""
        from pipeline.model_client import chat_with_retry

        messages = [{"role": "user", "content": "请回复：测试成功"}]

        response = chat_with_retry(
            provider=test_provider,
            messages=messages,
            max_retries=2,
        )

        assert response.content
        assert len(response.content) > 0
        logger.info(f"API 响应: {response.content[:100]}")

    def test_api_call_with_retry_decorator(self, test_provider: Any) -> None:
        """测试直接使用 @llm_retry 装饰器调用 API。"""
        call_count = 0

        @llm_retry(max_retries=2, base_delay=0.5)
        def call_api() -> str:
            nonlocal call_count
            call_count += 1
            response = test_provider.chat(
                messages=[{"role": "user", "content": "1+1=?"}],
            )
            return response.content

        result = call_api()
        assert result
        assert call_count == 1


class TestRateLimitTrigger:
    """RateLimit 触发测试。

    通过并发请求触发 RateLimit，验证重试机制。
    注意：此测试依赖外部 API 行为，可能因服务状态不同而产生不稳定结果。
    """

    @pytest.mark.xfail(
        reason="RateLimit 触发依赖外部 API 状态，可能因服务端配置而失败",
        strict=False,
    )
    def test_concurrent_requests_trigger_rate_limit(
        self, test_provider: Any, caplog: Any
    ) -> None:
        """测试并发请求触发 RateLimit。

        5 个并发，2-3 轮，验证重试机制。
        允许部分请求因 RateLimit 失败，重点验证重试日志。
        如果 API 未触发 RateLimit，测试将标记为 xfail 而非失败。
        """
        from pipeline.model_client import chat_with_retry

        concurrency = 5
        rounds = 2

        def make_request(round_num: int) -> tuple[str, bool]:
            messages = [
                {
                    "role": "user",
                    "content": f"第 {round_num} 轮测试：请回复一个随机数字",
                }
            ]
            try:
                response = chat_with_retry(
                    provider=test_provider,
                    messages=messages,
                    max_retries=2,
                    max_retries_on_rate_limit=5,
                )
                return response.content, True
            except LLMError:
                return "", False

        success_count = 0
        failure_count = 0

        for round_num in range(1, rounds + 1):
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [
                    executor.submit(make_request, round_num)
                    for _ in range(concurrency)
                ]
                for f in futures:
                    _, success = f.result()
                    if success:
                        success_count += 1
                    else:
                        failure_count += 1

        rate_limit_retry_count = sum(
            1
            for r in caplog.records
            if r.levelname == "WARNING" and "429" in r.message
        )

        total_requests = concurrency * rounds
        logger.info(f"总请求数: {total_requests}")
        logger.info(f"成功: {success_count}, 失败: {failure_count}")
        logger.info(f"RateLimit 重试次数: {rate_limit_retry_count}")

        assert success_count >= 1, "至少应有 1 个请求成功"

        if rate_limit_retry_count < 1:
            pytest.xfail("未触发 RateLimit，可能 API 服务端未限流")

        assert rate_limit_retry_count >= 1


class TestLogOutput:
    """日志输出验证测试。"""

    def test_retry_log_output(self, test_provider: Any, caplog: Any) -> None:
        """验证重试日志输出。"""
        from pipeline.model_client import chat_with_retry

        with caplog.at_level(logging.WARNING):
            messages = [{"role": "user", "content": "测试日志输出"}]

            try:
                chat_with_retry(
                    provider=test_provider,
                    messages=messages,
                    max_retries=3,
                )
            except LLMError:
                pass

        all_logs = [r.message for r in caplog.records]
        logger.info(f"捕获的日志: {all_logs[:5]}")

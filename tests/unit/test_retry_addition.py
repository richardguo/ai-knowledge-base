"""llm_retry 装饰器的补充单元测试。

覆盖边界条件、异常判断逻辑、混合场景、日志格式、异步完整性等。
"""

import asyncio
import logging
from typing import Any
from unittest.mock import patch

import pytest

from utils import LLMError, llm_retry, llm_retry_async


class TestParameterValidation:
    """参数边界值测试。"""

    def test_max_retries_zero_no_retry(self) -> None:
        """max_retries=0 → 不重试，直接抛出异常。"""
        call_count = 0

        @llm_retry(max_retries=0, base_delay=0.01)
        def fail_func() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMError("错误", status_code=500)

        with pytest.raises(LLMError):
            fail_func()

        assert call_count == 1

    def test_max_retries_on_rate_limit_zero_no_retry(self) -> None:
        """max_retries_on_rate_limit=0 时 RateLimit 不重试。"""
        call_count = 0

        @llm_retry(max_retries=3, max_retries_on_rate_limit=0, base_delay=0.01)
        def rate_limit_func() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMError("限流", status_code=429)

        with pytest.raises(LLMError):
            rate_limit_func()

        assert call_count == 1

    def test_base_delay_zero_immediate_retry(self, mocker: Any) -> None:
        """base_delay=0 → 立即重试，无等待。"""
        sleep_times: list[float] = []

        def mock_sleep(duration: float) -> None:
            sleep_times.append(duration)

        mocker.patch("time.sleep", side_effect=mock_sleep)

        @llm_retry(max_retries=2, base_delay=0.0, jitter=False)
        def fail_func() -> str:
            raise LLMError("错误", status_code=500)

        with pytest.raises(LLMError):
            fail_func()

        assert all(d == 0.0 for d in sleep_times)

    def test_max_delay_smaller_than_base_delay(self, mocker: Any) -> None:
        """max_delay < base_delay 时，延迟被 cap 在 max_delay。"""
        sleep_times: list[float] = []

        def mock_sleep(duration: float) -> None:
            sleep_times.append(duration)

        mocker.patch("time.sleep", side_effect=mock_sleep)

        @llm_retry(max_retries=2, base_delay=5.0, max_delay=2.0, jitter=False)
        def fail_func() -> str:
            raise LLMError("错误", status_code=500)

        with pytest.raises(LLMError):
            fail_func()

        assert all(d == 2.0 for d in sleep_times)

    def test_exponential_base_one_fixed_delay(self, mocker: Any) -> None:
        """exponential_base=1 → 退避不增长，固定延迟。"""
        sleep_times: list[float] = []

        def mock_sleep(duration: float) -> None:
            sleep_times.append(duration)

        mocker.patch("time.sleep", side_effect=mock_sleep)

        @llm_retry(max_retries=3, base_delay=2.0, exponential_base=1, jitter=False)
        def fail_func() -> str:
            raise LLMError("错误", status_code=500)

        with pytest.raises(LLMError):
            fail_func()

        assert all(d == 2.0 for d in sleep_times)

    def test_empty_retryable_exceptions_no_retry(self) -> None:
        """空 retryable_exceptions 元组 → 任何异常都不重试。"""
        call_count = 0

        @llm_retry(max_retries=3, base_delay=0.01, retryable_exceptions=())
        def fail_func() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMError("错误", status_code=500)

        with pytest.raises(LLMError):
            fail_func()

        assert call_count == 1


class TestCustomRetryableExceptions:
    """自定义异常类型测试。"""

    def test_custom_exception_type_retryable(self) -> None:
        """自定义 retryable_exceptions（非 LLMError）。"""
        call_count = 0

        @llm_retry(
            max_retries=2,
            base_delay=0.01,
            retryable_exceptions=(ValueError,),
        )
        def fail_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("自定义错误")
            return "success"

        result = fail_func()
        assert result == "success"
        assert call_count == 2

    def test_multiple_exception_types(self) -> None:
        """多个异常类型的 retryable_exceptions。"""
        call_count = 0

        @llm_retry(
            max_retries=3,
            base_delay=0.01,
            retryable_exceptions=(LLMError, ConnectionError),
        )
        def fail_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("连接失败")
            if call_count == 2:
                raise LLMError("LLM 错误", status_code=500)
            return "success"

        result = fail_func()
        assert result == "success"
        assert call_count == 3

    def test_llmerror_subclass_retryable(self) -> None:
        """LLMError 子类异常应被正确识别。"""

        class CustomLLMError(LLMError):
            pass

        call_count = 0

        @llm_retry(max_retries=2, base_delay=0.01)
        def fail_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise CustomLLMError("子类错误", status_code=500)
            return "success"

        result = fail_func()
        assert result == "success"
        assert call_count == 2


class TestMixedErrorCounter:
    """混合场景计数逻辑完整测试。"""

    def test_rate_limit_then_server_error(self) -> None:
        """先 RateLimit 后普通错误，验证计数器正确切换。"""
        call_count = 0
        error_sequence = [429, 500]

        @llm_retry(
            max_retries=1,
            max_retries_on_rate_limit=5,
            base_delay=0.01,
        )
        def mixed_func() -> str:
            nonlocal call_count
            error_code = error_sequence[call_count]
            call_count += 1
            raise LLMError(f"错误 {error_code}", status_code=error_code)

        with pytest.raises(LLMError):
            mixed_func()

        # 第1次 429 (attempt=0) -> max_retries_on_rate_limit=5, 未达到, 重试
        # 第2次 500 (attempt=1) -> max_retries=1, 已达到, 抛出
        assert call_count == 2

    def test_rate_limit_count_not_reached_but_server_error_limit_reached(self) -> None:
        """RateLimit 次数未达到上限，但普通错误达到上限。"""
        call_count = 0

        @llm_retry(
            max_retries=1,
            max_retries_on_rate_limit=10,
            base_delay=0.01,
        )
        def server_error_func() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMError("服务器错误", status_code=503)

        with pytest.raises(LLMError):
            server_error_func()

        # 普通错误 max_retries=1, 所以最多调用 2 次 (初始 + 1 次重试)
        assert call_count == 2

    def test_first_429_then_all_500(self) -> None:
        """第一次是 429，后续全是 500，验证混合计数。"""
        call_count = 0
        error_sequence = [429, 500, 500]

        @llm_retry(
            max_retries=2,
            max_retries_on_rate_limit=5,
            base_delay=0.01,
        )
        def mixed_func() -> str:
            nonlocal call_count
            error_code = error_sequence[call_count] if call_count < len(error_sequence) else 500
            call_count += 1
            raise LLMError(f"错误 {error_code}", status_code=error_code)

        with pytest.raises(LLMError):
            mixed_func()

        # attempt=0: 429 -> max_retries_on_rate_limit=5, 未达到, 重试
        # attempt=1: 500 -> max_retries=2, 未达到, 重试
        # attempt=2: 500 -> max_retries=2, 已达到, 抛出
        assert call_count == 3

    def test_all_rate_limit_then_success(self) -> None:
        """全部 RateLimit 错误后成功。"""
        call_count = 0

        @llm_retry(
            max_retries=1,
            max_retries_on_rate_limit=3,
            base_delay=0.01,
        )
        def rate_limit_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise LLMError("限流", status_code=429)
            return "success"

        result = rate_limit_func()
        assert result == "success"
        assert call_count == 4


class TestLogFormat:
    """日志格式验证测试。"""

    def test_retry_log_contains_delay_and_exception_message(self, caplog: Any) -> None:
        """重试日志包含延迟时间和异常消息。"""
        with caplog.at_level(logging.WARNING):

            @llm_retry(max_retries=1, base_delay=1.0, jitter=False)
            def fail_func() -> str:
                raise LLMError("测试错误消息", status_code=500)

            with pytest.raises(LLMError):
                fail_func()

        warning_logs = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warning_logs) >= 1

        log_message = warning_logs[0].message
        assert "1.0秒后重试" in log_message
        assert "测试错误消息" in log_message

    def test_retry_log_shows_correct_max_retries_for_rate_limit(self, caplog: Any) -> None:
        """RateLimit 日志显示正确的 max_retries_on_rate_limit。"""
        with caplog.at_level(logging.WARNING):

            @llm_retry(
                max_retries=1,
                max_retries_on_rate_limit=2,
                base_delay=0.01,
            )
            def rate_limit_func() -> str:
                raise LLMError("限流", status_code=429)

            with pytest.raises(LLMError):
                rate_limit_func()

        warning_logs = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warning_logs) >= 1

        log_message = warning_logs[0].message
        assert "/2" in log_message

    def test_final_failure_log_is_error_level(self, caplog: Any) -> None:
        """最终失败日志是 ERROR 级别。"""
        with caplog.at_level(logging.ERROR):

            @llm_retry(max_retries=1, base_delay=0.01)
            def fail_func() -> str:
                raise LLMError("错误", status_code=500)

            with pytest.raises(LLMError):
                fail_func()

        error_logs = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(error_logs) >= 1
        assert "最大重试次数" in error_logs[0].message


class TestAsyncRetryComplete:
    """异步装饰器完整测试。"""

    @pytest.mark.asyncio
    async def test_async_status_code_filtering(self) -> None:
        """异步版状态码过滤。"""
        call_count = 0

        @llm_retry_async(max_retries=2, base_delay=0.01)
        async def raise_401() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMError("认证失败", status_code=401)

        with pytest.raises(LLMError):
            await raise_401()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_network_error_retried(self) -> None:
        """异步版网络错误（无 status_code）重试。"""
        call_count = 0

        @llm_retry_async(max_retries=2, base_delay=0.01)
        async def network_error() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise LLMError("网络超时", status_code=None)
            return "success"

        result = await network_error()
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_custom_status_codes(self) -> None:
        """异步版自定义 retryable_status_codes。"""
        call_count = 0

        @llm_retry_async(
            max_retries=3,
            base_delay=0.01,
            retryable_status_codes={503},
        )
        async def raise_429() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMError("限流", status_code=429)

        with pytest.raises(LLMError):
            await raise_429()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_on_retry_callback(self) -> None:
        """异步版 on_retry 回调。"""
        callback_calls: list[tuple[Exception, int]] = []

        def on_retry_callback(exc: Exception, attempt: int) -> None:
            callback_calls.append((exc, attempt))

        @llm_retry_async(max_retries=2, base_delay=0.01, on_retry=on_retry_callback)
        async def fail_twice() -> str:
            if len(callback_calls) < 2:
                raise LLMError("错误", status_code=500)
            return "success"

        await fail_twice()

        assert len(callback_calls) == 2
        assert callback_calls[0][1] == 1
        assert callback_calls[1][1] == 2

    @pytest.mark.asyncio
    async def test_async_exponential_backoff(self, mocker: Any) -> None:
        """异步版指数退避使用 asyncio.sleep。"""
        sleep_times: list[float] = []

        async def mock_async_sleep(duration: float) -> None:
            sleep_times.append(duration)

        mocker.patch("asyncio.sleep", side_effect=mock_async_sleep)

        @llm_retry_async(max_retries=3, base_delay=1.0, jitter=False, max_delay=100.0)
        async def fail_func() -> str:
            raise LLMError("错误", status_code=500)

        with pytest.raises(LLMError):
            await fail_func()

        assert len(sleep_times) == 3
        assert sleep_times[0] == 1.0
        assert sleep_times[1] == 2.0
        assert sleep_times[2] == 4.0

    @pytest.mark.asyncio
    async def test_async_mixed_errors(self) -> None:
        """异步版混合错误计数。"""
        call_count = 0
        error_sequence = [429, 500]

        @llm_retry_async(
            max_retries=1,
            max_retries_on_rate_limit=5,
            base_delay=0.01,
        )
        async def mixed_func() -> str:
            nonlocal call_count
            error_code = error_sequence[call_count]
            call_count += 1
            raise LLMError(f"错误 {error_code}", status_code=error_code)

        with pytest.raises(LLMError):
            await mixed_func()

        assert call_count == 2


class TestFinalException:
    """最终异常验证测试。"""

    def test_last_exception_preserved(self) -> None:
        """验证抛出的是最后一次异常。"""
        call_count = 0
        error_messages = ["第一次错误", "第二次错误", "第三次错误"]

        @llm_retry(max_retries=2, base_delay=0.01)
        def fail_func() -> str:
            nonlocal call_count
            msg = error_messages[call_count]
            call_count += 1
            raise LLMError(msg, status_code=500)

        with pytest.raises(LLMError) as exc_info:
            fail_func()

        assert "第三次错误" in str(exc_info.value)
        assert call_count == 3

    def test_exception_status_code_preserved(self) -> None:
        """验证异常 status_code 完整保留。"""
        call_count = 0

        @llm_retry(max_retries=2, base_delay=0.01)
        def fail_func() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMError("错误", status_code=503)

        with pytest.raises(LLMError) as exc_info:
            fail_func()

        assert exc_info.value.status_code == 503

    def test_exception_without_status_code_preserved(self) -> None:
        """验证无 status_code 的异常信息保留。"""
        call_count = 0

        @llm_retry(max_retries=1, base_delay=0.01)
        def fail_func() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMError("网络错误", status_code=None)

        with pytest.raises(LLMError) as exc_info:
            fail_func()

        assert exc_info.value.status_code is None
        assert "网络错误" in str(exc_info.value)


class TestMetadataPreservation:
    """函数元数据保留测试。"""

    def test_docstring_preserved(self) -> None:
        """测试 __doc__ 被保留。"""

        @llm_retry()
        def documented_func() -> str:
            """这是一个有文档的函数。"""
            return "success"

        assert documented_func.__doc__ == "这是一个有文档的函数。"

    def test_module_preserved(self) -> None:
        """测试 __module__ 被保留。"""

        @llm_retry()
        def func_with_module() -> str:
            return "success"

        assert func_with_module.__module__ == __name__

    def test_async_docstring_preserved(self) -> None:
        """测试异步函数 __doc__ 被保留。"""

        @llm_retry_async()
        async def async_documented_func() -> str:
            """这是一个异步函数的文档。"""
            return "success"

        assert async_documented_func.__doc__ == "这是一个异步函数的文档。"

    def test_async_name_preserved(self) -> None:
        """测试异步函数 __name__ 被保留。"""

        @llm_retry_async()
        async def my_async_func() -> str:
            return "success"

        assert my_async_func.__name__ == "my_async_func"


class TestStatusCodesComplete:
    """状态码完整测试。"""

    def test_all_default_retryable_status_codes(self) -> None:
        """测试所有默认可重试状态码。"""
        for status_code in [429, 500, 502, 503, 504]:
            call_count = 0

            @llm_retry(max_retries=1, base_delay=0.01)
            def fail_func() -> str:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise LLMError(f"错误 {status_code}", status_code=status_code)
                return "success"

            result = fail_func()
            assert result == "success", f"状态码 {status_code} 应该重试"
            assert call_count == 2

    def test_non_retryable_status_codes(self) -> None:
        """测试不可重试的状态码。"""
        for status_code in [400, 401, 403, 404]:
            call_count = 0

            @llm_retry(max_retries=3, base_delay=0.01)
            def fail_func() -> str:
                nonlocal call_count
                call_count += 1
                raise LLMError(f"错误 {status_code}", status_code=status_code)

            with pytest.raises(LLMError):
                fail_func()

            assert call_count == 1, f"状态码 {status_code} 不应该重试"

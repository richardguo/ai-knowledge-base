"""llm_retry 装饰器的单元测试。"""

import asyncio
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils import LLMError, llm_retry, llm_retry_async


class TestBasicRetry:
    """基础重试场景测试。"""

    def test_successful_call_no_retry(self) -> None:
        """测试正常调用（无异常）→ 直接返回结果。"""

        @llm_retry()
        def successful_func() -> str:
            return "success"

        assert successful_func() == "success"

    def test_retry_then_success(self, mocker: Any) -> None:
        """测试第 1 次失败后成功 → 验证重试次数和返回值。"""
        call_count = 0

        @llm_retry(max_retries=3, base_delay=0.01)
        def flaky_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise LLMError("临时错误", status_code=429)
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 2

    def test_exhaust_all_retries(self, mocker: Any) -> None:
        """测试达到 max_retries 后仍失败 → 抛出异常。"""

        @llm_retry(max_retries=2, base_delay=0.01)
        def always_fail() -> str:
            raise LLMError("服务不可用", status_code=503)

        with pytest.raises(LLMError) as exc_info:
            always_fail()

        assert exc_info.value.status_code == 503

    def test_non_retryable_exception_raised_immediately(self) -> None:
        """测试非 retryable_exceptions 异常 → 不重试，直接抛出。"""
        call_count = 0

        @llm_retry(max_retries=3, base_delay=0.01)
        def raise_value_error() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("不是 LLMError")

        with pytest.raises(ValueError):
            raise_value_error()

        assert call_count == 1


class TestStatusCodeFiltering:
    """状态码过滤测试。"""

    def test_status_code_in_retryable_set(self, mocker: Any) -> None:
        """测试状态码在 retryable_status_codes 中 → 重试。"""
        call_count = 0

        @llm_retry(max_retries=2, base_delay=0.01)
        def raise_500() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise LLMError("服务器错误", status_code=500)
            return "success"

        result = raise_500()
        assert result == "success"
        assert call_count == 2

    def test_status_code_not_in_retryable_set(self) -> None:
        """测试状态码不在 retryable_status_codes 中（如 401）→ 不重试。"""
        call_count = 0

        @llm_retry(max_retries=3, base_delay=0.01)
        def raise_401() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMError("认证失败", status_code=401)

        with pytest.raises(LLMError) as exc_info:
            raise_401()

        assert exc_info.value.status_code == 401
        assert call_count == 1

    def test_custom_retryable_status_codes(self) -> None:
        """测试自定义 retryable_status_codes。"""
        call_count = 0

        @llm_retry(
            max_retries=3,
            base_delay=0.01,
            retryable_status_codes={503},
        )
        def raise_429() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMError("限流", status_code=429)

        with pytest.raises(LLMError) as exc_info:
            raise_429()

        assert exc_info.value.status_code == 429
        assert call_count == 1


class TestNetworkError:
    """网络错误测试。"""

    def test_llmerror_without_status_code_retried(self, mocker: Any) -> None:
        """测试无 status_code 的异常（网络错误）→ 重试。"""
        call_count = 0

        @llm_retry(max_retries=2, base_delay=0.01)
        def network_error() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise LLMError("网络超时", status_code=None)
            return "success"

        result = network_error()
        assert result == "success"
        assert call_count == 2


class TestRateLimit:
    """RateLimit 单独处理测试。"""

    def test_rate_limit_uses_higher_limit(self, mocker: Any) -> None:
        """测试 RateLimit 使用 max_retries_on_rate_limit。"""
        call_count = 0

        @llm_retry(
            max_retries=1,
            max_retries_on_rate_limit=3,
            base_delay=0.01,
        )
        def rate_limit_error() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMError("限流", status_code=429)

        with pytest.raises(LLMError):
            rate_limit_error()

        assert call_count == 4

    def test_mixed_errors_unified_counter(self, mocker: Any) -> None:
        """测试混合场景：RateLimit + ServerError，验证计数逻辑。"""
        call_count = 0
        error_sequence = [429, 429, 500]

        @llm_retry(
            max_retries=2,
            max_retries_on_rate_limit=5,
            base_delay=0.01,
        )
        def mixed_errors() -> str:
            nonlocal call_count
            error_code = error_sequence[call_count] if call_count < len(error_sequence) else 500
            call_count += 1
            raise LLMError(f"错误 {error_code}", status_code=error_code)

        with pytest.raises(LLMError):
            mixed_errors()

        assert call_count == 3

    def test_regular_error_exhausts_normal_limit(self, mocker: Any) -> None:
        """测试普通错误使用普通限制，即使 RateLimit 限制更高。"""
        call_count = 0

        @llm_retry(
            max_retries=2,
            max_retries_on_rate_limit=10,
            base_delay=0.01,
        )
        def server_error() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMError("服务器错误", status_code=503)

        with pytest.raises(LLMError):
            server_error()

        assert call_count == 3


class TestExponentialBackoff:
    """指数退避测试。"""

    def test_delay_calculation(self, mocker: Any) -> None:
        """测试指数退避计算正确。"""
        sleep_times: list[float] = []

        def mock_sleep(duration: float) -> None:
            sleep_times.append(duration)

        mocker.patch("time.sleep", side_effect=mock_sleep)

        @llm_retry(max_retries=3, base_delay=1.0, jitter=False, max_delay=100.0)
        def always_fail() -> str:
            raise LLMError("错误", status_code=500)

        with pytest.raises(LLMError):
            always_fail()

        assert len(sleep_times) == 3
        assert sleep_times[0] == 1.0
        assert sleep_times[1] == 2.0
        assert sleep_times[2] == 4.0

    def test_max_delay_cap(self, mocker: Any) -> None:
        """测试 max_delay 上限生效。"""
        sleep_times: list[float] = []

        def mock_sleep(duration: float) -> None:
            sleep_times.append(duration)

        mocker.patch("time.sleep", side_effect=mock_sleep)

        @llm_retry(max_retries=5, base_delay=1.0, jitter=False, max_delay=4.0)
        def always_fail() -> str:
            raise LLMError("错误", status_code=500)

        with pytest.raises(LLMError):
            always_fail()

        for delay in sleep_times:
            assert delay <= 4.0

    def test_jitter_range(self, mocker: Any) -> None:
        """测试 jitter 范围（50%~100%）。"""
        sleep_times: list[float] = []

        def mock_sleep(duration: float) -> None:
            sleep_times.append(duration)

        mocker.patch("time.sleep", side_effect=mock_sleep)

        @llm_retry(max_retries=3, base_delay=1.0, jitter=True, max_delay=100.0)
        def always_fail() -> str:
            raise LLMError("错误", status_code=500)

        with pytest.raises(LLMError):
            always_fail()

        for delay in sleep_times:
            base_delay_attempt = 1.0 * (2 ** sleep_times.index(delay))
            assert delay >= base_delay_attempt * 0.5
            assert delay <= base_delay_attempt


class TestOnRetryCallback:
    """on_retry 回调测试。"""

    def test_on_retry_called(self, mocker: Any) -> None:
        """测试 on_retry 回调被正确调用。"""
        callback_calls: list[tuple[Exception, int]] = []

        def on_retry_callback(exc: Exception, attempt: int) -> None:
            callback_calls.append((exc, attempt))

        @llm_retry(max_retries=2, base_delay=0.01, on_retry=on_retry_callback)
        def fail_twice() -> str:
            if len(callback_calls) < 2:
                raise LLMError("错误", status_code=500)
            return "success"

        fail_twice()

        assert len(callback_calls) == 2
        assert callback_calls[0][1] == 1
        assert callback_calls[1][1] == 2
        assert isinstance(callback_calls[0][0], LLMError)

    def test_on_retry_params_correct(self, mocker: Any) -> None:
        """测试 on_retry 参数正确（exception, attempt）。"""
        received_params: dict[str, Any] = {}

        def on_retry_callback(exc: Exception, attempt: int) -> None:
            received_params["exception"] = exc
            received_params["attempt"] = attempt

        @llm_retry(
            max_retries=1,
            max_retries_on_rate_limit=1,
            base_delay=0.01,
            on_retry=on_retry_callback,
        )
        def fail_once() -> str:
            raise LLMError("测试错误", status_code=429)

        with pytest.raises(LLMError):
            fail_once()

        assert isinstance(received_params["exception"], LLMError)
        assert received_params["attempt"] == 1

    def test_no_callback_when_none(self, mocker: Any) -> None:
        """测试 on_retry=None 时不调用回调。"""
        call_count = 0

        @llm_retry(max_retries=1, base_delay=0.01, on_retry=None)
        def always_fail() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMError("错误", status_code=500)

        with pytest.raises(LLMError):
            always_fail()

        assert call_count == 2


class TestEdgeCases:
    """边界情况测试。"""

    def test_max_retries_zero(self) -> None:
        """测试 max_retries=0 → 不重试。"""
        call_count = 0

        @llm_retry(max_retries=0, base_delay=0.01)
        def fail_once() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMError("错误", status_code=500)

        with pytest.raises(LLMError):
            fail_once()

        assert call_count == 1

    def test_base_delay_zero(self, mocker: Any) -> None:
        """测试 base_delay=0 → 立即重试（无等待）。"""
        sleep_times: list[float] = []

        def mock_sleep(duration: float) -> None:
            sleep_times.append(duration)

        mocker.patch("time.sleep", side_effect=mock_sleep)

        @llm_retry(max_retries=2, base_delay=0.0, jitter=False)
        def fail_twice() -> str:
            raise LLMError("错误", status_code=500)

        with pytest.raises(LLMError):
            fail_twice()

        for delay in sleep_times:
            assert delay == 0.0


class TestAsyncRetry:
    """异步装饰器测试。"""

    @pytest.mark.asyncio
    async def test_async_successful_call_no_retry(self) -> None:
        """测试异步正常调用（无异常）→ 直接返回结果。"""

        @llm_retry_async()
        async def successful_func() -> str:
            return "success"

        result = await successful_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_async_retry_then_success(self, mocker: Any) -> None:
        """测试异步第 1 次失败后成功 → 验证重试次数和返回值。"""
        call_count = 0

        @llm_retry_async(max_retries=3, base_delay=0.01)
        async def flaky_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise LLMError("临时错误", status_code=429)
            return "success"

        result = await flaky_func()
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_exhaust_all_retries(self) -> None:
        """测试异步达到 max_retries 后仍失败 → 抛出异常。"""

        @llm_retry_async(max_retries=2, base_delay=0.01)
        async def always_fail() -> str:
            raise LLMError("服务不可用", status_code=503)

        with pytest.raises(LLMError) as exc_info:
            await always_fail()

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_async_rate_limit_uses_higher_limit(self, mocker: Any) -> None:
        """测试异步 RateLimit 使用 max_retries_on_rate_limit。"""
        call_count = 0

        @llm_retry_async(
            max_retries=1,
            max_retries_on_rate_limit=3,
            base_delay=0.01,
        )
        async def rate_limit_error() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMError("限流", status_code=429)

        with pytest.raises(LLMError):
            await rate_limit_error()

        assert call_count == 4

    @pytest.mark.asyncio
    async def test_async_non_retryable_exception_raised_immediately(self) -> None:
        """测试异步非 retryable_exceptions 异常 → 不重试，直接抛出。"""
        call_count = 0

        @llm_retry_async(max_retries=3, base_delay=0.01)
        async def raise_value_error() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("不是 LLMError")

        with pytest.raises(ValueError):
            await raise_value_error()

        assert call_count == 1


class TestLogging:
    """日志测试。"""

    def test_warning_log_on_retry(self, caplog: Any) -> None:
        """测试重试时记录 warning 日志。"""

        @llm_retry(max_retries=2, base_delay=0.01)
        def fail_twice() -> str:
            if len([r for r in caplog.records if r.levelname == "WARNING"]) < 2:
                raise LLMError("错误", status_code=500)
            return "success"

        with caplog.at_level(logging.WARNING):
            result = fail_twice()

        assert result == "success"
        warning_logs = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warning_logs) >= 1

    def test_error_log_on_final_failure(self, caplog: Any) -> None:
        """测试最终失败时记录 error 日志。"""

        @llm_retry(max_retries=1, base_delay=0.01)
        def always_fail() -> str:
            raise LLMError("错误", status_code=500)

        with caplog.at_level(logging.ERROR):
            with pytest.raises(LLMError):
                always_fail()

        error_logs = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(error_logs) >= 1


class TestTypePreservation:
    """类型签名保持测试。"""

    def test_type_hints_preserved(self) -> None:
        """测试类型提示被保留。"""

        @llm_retry()
        def typed_func(x: int, y: str) -> str:
            return f"{x}: {y}"

        assert typed_func.__name__ == "typed_func"
        assert typed_func(1, "test") == "1: test"

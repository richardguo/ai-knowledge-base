"""LLM 调用重试装饰器模块。

提供同步和异步版本的 LLM 调用重试装饰器，支持：
- 指数退避 + jitter + max_delay 上限
- 智能异常判断（异常类型 + 状态码）
- RateLimit 单独处理（更高的重试次数）
- 可选的 on_retry 回调
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from functools import wraps
from typing import Any, Callable, ParamSpec, TypeVar

from utils.exceptions import LLMError

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")

DEFAULT_RETRYABLE_STATUS_CODES: set[int] = {429, 500, 502, 503, 504}


def _calculate_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    exponential_base: int,
    jitter: bool,
) -> float:
    """计算重试延迟时间。

    Args:
        attempt: 当前重试次数（从 0 开始）。
        base_delay: 基础延迟时间（秒）。
        max_delay: 最大延迟时间（秒）。
        exponential_base: 指数基数。
        jitter: 是否添加随机抖动。

    Returns:
        延迟时间（秒）。
    """
    delay = min(base_delay * (exponential_base**attempt), max_delay)
    if jitter:
        delay *= 0.5 + random.random() * 0.5
    return delay


def _should_retry(
    exception: Exception,
    retryable_exceptions: tuple[type[Exception], ...],
    retryable_status_codes: set[int],
) -> bool:
    """判断异常是否应该重试。

    Args:
        exception: 捕获的异常。
        retryable_exceptions: 可重试的异常类型元组。
        retryable_status_codes: 可重试的 HTTP 状态码集合。

    Returns:
        是否应该重试。
    """
    if not isinstance(exception, retryable_exceptions):
        return False

    if isinstance(exception, LLMError):
        if exception.status_code is None:
            return True
        return exception.status_code in retryable_status_codes

    return True


def _is_rate_limit_error(exception: Exception) -> bool:
    """判断异常是否为 RateLimit 错误。

    Args:
        exception: 捕获的异常。

    Returns:
        是否为 RateLimit 错误（status_code == 429）。
    """
    return isinstance(exception, LLMError) and exception.status_code == 429


def _get_max_retries_for_error(
    exception: Exception,
    max_retries: int,
    max_retries_on_rate_limit: int,
) -> int:
    """根据错误类型获取最大重试次数。

    Args:
        exception: 捕获的异常。
        max_retries: 普通错误最大重试次数。
        max_retries_on_rate_limit: RateLimit 错误最大重试次数。

    Returns:
        适用的最大重试次数。
    """
    if _is_rate_limit_error(exception):
        return max_retries_on_rate_limit
    return max_retries


def llm_retry(
    *,
    max_retries: int = 3,
    max_retries_on_rate_limit: int = 20,
    base_delay: float = 1.0,
    max_delay: float = 180.0,
    exponential_base: int = 2,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (LLMError,),
    retryable_status_codes: set[int] | None = None,
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """LLM 调用重试装饰器（同步版本）。

    为同步函数提供可配置的指数退避重试能力。

    Args:
        max_retries: 普通错误最大重试次数，默认 3。
        max_retries_on_rate_limit: RateLimit 错误最大重试次数，默认 20。
        base_delay: 基础延迟时间（秒），默认 1.0。
        max_delay: 最大延迟时间（秒），默认 180.0。
        exponential_base: 指数基数，默认 2。
        jitter: 是否添加随机抖动，默认 True。
        retryable_exceptions: 可重试的异常类型元组，默认 (LLMError,)。
        retryable_status_codes: 可重试的 HTTP 状态码集合，
            默认 {429, 500, 502, 503, 504}。
        on_retry: 重试回调函数，签名为 (exception, attempt) -> None。

    Returns:
        装饰器函数。

    Example:
        @llm_retry(max_retries=3, base_delay=1.0)
        def call_llm(prompt: str) -> str:
            return provider.chat(prompt)
    """
    status_codes = retryable_status_codes or DEFAULT_RETRYABLE_STATUS_CODES

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_error: Exception | None = None
            attempt = 0

            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if not _should_retry(e, retryable_exceptions, status_codes):
                        raise

                    last_error = e
                    applicable_max_retries = _get_max_retries_for_error(
                        e, max_retries, max_retries_on_rate_limit
                    )

                    if attempt >= applicable_max_retries:
                        logger.error(
                            f"LLM 调用失败，已达最大重试次数: {e}"
                        )
                        raise last_error

                    delay = _calculate_delay(
                        attempt, base_delay, max_delay, exponential_base, jitter
                    )

                    logger.warning(
                        f"LLM 调用失败 (尝试 {attempt + 1}/{applicable_max_retries}), "
                        f"{delay:.1f}秒后重试: {e}"
                    )

                    if on_retry is not None:
                        on_retry(e, attempt + 1)

                    time.sleep(delay)
                    attempt += 1

        return wrapper

    return decorator


def llm_retry_async(
    *,
    max_retries: int = 3,
    max_retries_on_rate_limit: int = 20,
    base_delay: float = 1.0,
    max_delay: float = 180.0,
    exponential_base: int = 2,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (LLMError,),
    retryable_status_codes: set[int] | None = None,
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """LLM 调用重试装饰器（异步版本）。

    为异步函数提供可配置的指数退避重试能力。
    参数和行为与 llm_retry 一致，但使用 asyncio.sleep() 实现非阻塞延迟。

    Args:
        max_retries: 普通错误最大重试次数，默认 3。
        max_retries_on_rate_limit: RateLimit 错误最大重试次数，默认 20。
        base_delay: 基础延迟时间（秒），默认 1.0。
        max_delay: 最大延迟时间（秒），默认 180.0。
        exponential_base: 指数基数，默认 2。
        jitter: 是否添加随机抖动，默认 True。
        retryable_exceptions: 可重试的异常类型元组，默认 (LLMError,)。
        retryable_status_codes: 可重试的 HTTP 状态码集合，
            默认 {429, 500, 502, 503, 504}。
        on_retry: 重试回调函数，签名为 (exception, attempt) -> None。

    Returns:
        装饰器函数。

    Example:
        @llm_retry_async(max_retries=3, base_delay=1.0)
        async def call_llm_async(prompt: str) -> str:
            return await provider.chat_async(prompt)
    """
    status_codes = retryable_status_codes or DEFAULT_RETRYABLE_STATUS_CODES

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_error: Exception | None = None
            attempt = 0

            while True:
                try:
                    result = func(*args, **kwargs)
                    if asyncio.iscoroutine(result):
                        return await result
                    return result
                except Exception as e:
                    if not _should_retry(e, retryable_exceptions, status_codes):
                        raise

                    last_error = e
                    applicable_max_retries = _get_max_retries_for_error(
                        e, max_retries, max_retries_on_rate_limit
                    )

                    if attempt >= applicable_max_retries:
                        logger.error(
                            f"LLM 调用失败，已达最大重试次数: {e}"
                        )
                        raise last_error

                    delay = _calculate_delay(
                        attempt, base_delay, max_delay, exponential_base, jitter
                    )

                    logger.warning(
                        f"LLM 调用失败 (尝试 {attempt + 1}/{applicable_max_retries}), "
                        f"{delay:.1f}秒后重试: {e}"
                    )

                    if on_retry is not None:
                        on_retry(e, attempt + 1)

                    await asyncio.sleep(delay)
                    attempt += 1

        return wrapper

    return decorator

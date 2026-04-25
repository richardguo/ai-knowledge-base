"""问题1进阶: 统一的装饰器能否同时支持同步和异步?

结论: 可以,但需要运行时检测函数类型,代码会变复杂.
策略:
1. 检测被装饰的函数是否是协程函数
2. 返回不同的包装器
"""

import asyncio
import inspect
import time
from functools import wraps
from typing import Callable, ParamSpec, TypeVar, Awaitable, Union

P = ParamSpec("P")
T = TypeVar("T")


def unified_retry(max_retries: int = 3, base_delay: float = 1.0):
    """同时支持同步和异步的统一重试装饰器.
    
    实现要点:
    1. 使用 inspect.iscoroutinefunction() 检测是否是异步函数
    2. 返回不同的包装器
    3. 类型签名变得复杂: 返回 Union[T, Awaitable[T]]
    """
    def decorator(func: Callable[P, T]) -> Callable[P, Union[T, Awaitable[T]]]:
        if inspect.iscoroutinefunction(func):
            # 异步函数 - 返回 async 包装器
            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                for attempt in range(max_retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        if attempt < max_retries:
                            delay = base_delay * (2 ** attempt)
                            print(f"  [统一-异步] 第{attempt + 1}次失败, {delay:.1f}s后重试: {e}")
                            await asyncio.sleep(delay)
                        else:
                            raise
                raise RuntimeError("Unreachable")
            return async_wrapper
        else:
            # 同步函数 - 返回 sync 包装器
            @wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                for attempt in range(max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        if attempt < max_retries:
                            delay = base_delay * (2 ** attempt)
                            print(f"  [统一-同步] 第{attempt + 1}次失败, {delay:.1f}s后重试: {e}")
                            time.sleep(delay)
                        else:
                            raise
                raise RuntimeError("Unreachable")
            return sync_wrapper
    return decorator


# ========== 测试 ==========
class FakeError(Exception):
    pass


@unified_retry(max_retries=2, base_delay=0.1)
def sync_func() -> str:
    """同步函数."""
    sync_func.attempts = getattr(sync_func, 'attempts', 0) + 1
    if sync_func.attempts < 3:
        raise FakeError(f"失败 #{sync_func.attempts}")
    return "同步成功!"


@unified_retry(max_retries=2, base_delay=0.1)
async def async_func() -> str:
    """异步函数."""
    async_func.attempts = getattr(async_func, 'attempts', 0) + 1
    if async_func.attempts < 3:
        raise FakeError(f"失败 #{async_func.attempts}")
    return "异步成功!"


def test_sync():
    """测试同步函数."""
    print("\n=== 统一装饰器 - 同步函数 ===")
    result = sync_func()
    print(f"结果: {result}")


async def test_async():
    """测试异步函数."""
    print("\n=== 统一装饰器 - 异步函数 ===")
    result = await async_func()
    print(f"结果: {result}")


if __name__ == "__main__":
    test_sync()
    asyncio.run(test_async())
    
    print("\n=== 结论 ===")
    print("统一装饰器可以工作,但存在类型提示的问题:")
    print("- 返回类型是 Union[T, Awaitable[T]], IDE无法准确推断")
    print("- 代码复杂度增加")
    print("- 通常更好的做法是提供两个独立的装饰器: @llm_retry 和 @llm_retry_async")

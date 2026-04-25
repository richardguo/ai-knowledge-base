"""问题1: 同步 vs 异步装饰器的差异

1.a 同步和异步实现的不同之处:
- 同步: 使用 time.sleep() 阻塞等待
- 异步: 使用 asyncio.sleep() 非阻塞等待
- 函数签名: 同步 def func() vs 异步 async def func()
- 返回值: 同步直接返回 T, 异步返回 Awaitable[T]
- 调用方式: 同步直接调用, 异步需要 await
"""

import asyncio
import time
from functools import wraps
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


# ========== 同步装饰器 ==========
def sync_retry(max_retries: int = 3, base_delay: float = 1.0):
    """仅支持同步函数的简单重试装饰器."""
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        print(f"  [同步] 第{attempt + 1}次失败, {delay:.1f}s后重试: {e}")
                        time.sleep(delay)  # 阻塞等待
                    else:
                        raise
            raise RuntimeError("Unreachable")
        return wrapper
    return decorator


# ========== 异步装饰器 ==========
def async_retry(max_retries: int = 3, base_delay: float = 1.0):
    """仅支持异步函数的重试装饰器."""
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)  # 注意这里的 await
                except Exception as e:
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        print(f"  [异步] 第{attempt + 1}次失败, {delay:.1f}s后重试: {e}")
                        await asyncio.sleep(delay)  # 非阻塞等待
                    else:
                        raise
            raise RuntimeError("Unreachable")
        return wrapper
    return decorator


# ========== 测试 ==========
class FakeError(Exception):
    pass


# 1. 同步函数用同步装饰器
@sync_retry(max_retries=2, base_delay=0.1)
def sync_call() -> str:
    """模拟会失败2次的同步调用."""
    sync_call.attempts = getattr(sync_call, 'attempts', 0) + 1
    if sync_call.attempts < 3:
        raise FakeError(f"同步调用失败 #{sync_call.attempts}")
    return "同步成功!"


# 2. 异步函数用异步装饰器
@async_retry(max_retries=2, base_delay=0.1)
async def async_call() -> str:
    """模拟会失败2次的异步调用."""
    async_call.attempts = getattr(async_call, 'attempts', 0) + 1
    if async_call.attempts < 3:
        raise FakeError(f"异步调用失败 #{async_call.attempts}")
    return "异步成功!"


# 3. 异步函数用同步装饰器会怎样？
@sync_retry(max_retries=1, base_delay=0.1)
async def wrong_usage() -> str:
    """异步函数被同步装饰器装饰 - 这是错误的!"""
    return "永远不会被 await"


def test_sync():
    """测试同步装饰器."""
    print("\n=== 测试同步装饰器 ===")
    result = sync_call()
    print(f"结果: {result}")


async def test_async():
    """测试异步装饰器."""
    print("\n=== 测试异步装饰器 ===")
    result = await async_call()
    print(f"结果: {result}")


async def test_wrong_usage():
    """测试错误用法: 异步函数 + 同步装饰器."""
    print("\n=== 测试错误用法 (异步函数 + 同步装饰器) ===")
    result = wrong_usage()
    print(f"返回类型: {type(result)}")
    print(f"是协程吗: {asyncio.iscoroutine(result)}")
    # 注意: result 是一个协程对象，但从未被 await!
    # 这会导致协程未被调度，或者产生警告
    try:
        # 尝试 await 结果
        actual = await result
        print(f"结果: {actual}")
    except TypeError as e:
        print(f"错误: {e}")


if __name__ == "__main__":
    # 测试同步
    test_sync()
    
    # 测试异步
    asyncio.run(test_async())
    
    # 测试错误用法
    asyncio.run(test_wrong_usage())

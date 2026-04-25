"""问题5: on_retry 回调与幂等性

展示如何在重试时执行清理操作, 以及为什么这不是装饰器的责任.
"""

from dataclasses import dataclass, field
from functools import wraps
from typing import Callable, ParamSpec, TypeVar, Any
import time

P = ParamSpec("P")
T = TypeVar("T")


# ========== 模拟有副作用的场景 ==========
@dataclass
class CostTracker:
    """成本追踪器 - 有副作用 (记录成本)."""
    records: list[dict] = field(default_factory=list)
    
    def record(self, call_id: str, cost: float):
        """记录一次调用成本 - 这是副作用!"""
        self.records.append({"call_id": call_id, "cost": cost})
        print(f"  [CostTracker] 记录成本: call_id={call_id}, cost={cost}")
    
    def clear(self, call_id: str):
        """清除特定调用的记录 - 用于重试时回滚."""
        original_count = len(self.records)
        self.records = [r for r in self.records if r["call_id"] != call_id]
        removed = original_count - len(self.records)
        if removed:
            print(f"  [CostTracker] 清除记录: call_id={call_id}, 移除{removed}条")


cost_tracker = CostTracker()


# ========== 带 on_retry 回调的装饰器 ==========
def llm_retry_with_callback(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 180.0,
    on_retry: Callable[[Exception, int, dict], None] | None = None,
):
    """支持 on_retry 回调的重试装饰器.
    
    Args:
        on_retry: 回调函数 (exception, attempt_number, context)
            - exception: 触发的异常
            - attempt_number: 当前尝试次数 (从1开始)
            - context: 调用上下文, 可用于传递 call_id 等信息
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # 生成唯一的调用 ID
            import uuid
            call_id = str(uuid.uuid4())[:8]
            context = {"call_id": call_id, "args": args, "kwargs": kwargs}
            
            last_error: Exception | None = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs, call_id=call_id)
                except Exception as e:
                    last_error = e
                    
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        print(f"  [Retry] 第{attempt + 1}次失败, {delay:.1f}s后重试")
                        
                        # 调用回调 (如果提供了)
                        if on_retry:
                            on_retry(e, attempt + 1, context)
                        
                        time.sleep(delay)
                    else:
                        raise
            
            raise last_error or RuntimeError("Unknown error")
        
        return wrapper
    return decorator


# ========== 使用示例 ==========
call_count = 0


# 示例1: 没有 on_retry 回调 (副作用会被重复记录)
@llm_retry_with_callback(max_retries=2, base_delay=0.1)
def call_without_cleanup(*, call_id: str = "unknown") -> str:
    """没有清理的调用 - 成本会被重复记录."""
    global call_count
    call_count += 1
    
    # 模拟: 先记录成本, 然后失败
    cost_tracker.record(call_id, cost=0.01 * call_count)
    
    if call_count < 3:
        raise Exception(f"网络错误 #{call_count}")
    
    return f"成功! (call_id={call_id})"


# 示例2: 有 on_retry 回调 (可以清理副作用)
def cleanup_on_retry(exception: Exception, attempt: int, context: dict):
    """重试时清理成本记录."""
    call_id = context.get("call_id")
    print(f"  [on_retry] 第{attempt}次失败, 准备清理 call_id={call_id}")
    cost_tracker.clear(call_id)


@llm_retry_with_callback(max_retries=2, base_delay=0.1, on_retry=cleanup_on_retry)
def call_with_cleanup(*, call_id: str = "unknown") -> str:
    """有清理的调用 - 成本不会被重复记录."""
    global call_count
    call_count += 1
    
    # 模拟: 先记录成本, 然后失败
    cost_tracker.record(call_id, cost=0.01)
    
    if call_count < 6:  # 注意: 这里是 6 因为 call_count 在示例1中已经增加了
        raise Exception(f"网络错误 #{call_count}")
    
    return f"成功! (call_id={call_id})"


# ========== 测试 ==========
print("=== 示例1: 没有 on_retry 回调 ===")
print("预期: 成本会被记录多次 (副作用重复)")
call_count = 0
cost_tracker.records.clear()

try:
    result = call_without_cleanup()
    print(f"结果: {result}")
except Exception as e:
    print(f"最终失败: {e}")

print(f"\n成本记录条数: {len(cost_tracker.records)}")
print(f"记录内容: {cost_tracker.records}")
print("注意: 3次尝试产生了3条记录, 同一次逻辑调用被计了3次成本!")

print("\n" + "=" * 50)
print("=== 示例2: 有 on_retry 回调 ===")
print("预期: 成本只记录一次 (副作用被清理)")
call_count = 3  # 重置到示例1结束后的值
cost_tracker.records.clear()

try:
    result = call_with_cleanup()
    print(f"结果: {result}")
except Exception as e:
    print(f"最终失败: {e}")

print(f"\n成本记录条数: {len(cost_tracker.records)}")
print(f"记录内容: {cost_tracker.records}")
print("注意: 虽然尝试了多次, 但只有最后一次的成本被保留")

print("\n" + "=" * 50)
print("""
=== 重要结论 ===

1. on_retry 回调确实可以帮助清理副作用, 但它不是万能的:
   - 需要业务层配合 (记录 call_id)
   - 需要用户主动提供清理逻辑
   - 如果副作用发生在装饰器控制范围之外, 无法清理

2. 更好的实践:
   - 延迟副作用: 在确认成功后再执行副作用
   - 幂等设计: 确保多次执行不会产生额外影响
   - 事务性操作: 使用数据库事务等机制保证原子性

3. 装饰器的责任边界:
   - 装饰器只负责"重试"这个行为
   - 幂等性应该由被装饰的函数自己保证
   - on_retry 是辅助手段, 不是解决方案

设计决策:
- 提供 on_retry 回调 (可选)
- 在文档中明确警告副作用问题
- 推荐用户采用幂等设计
""")

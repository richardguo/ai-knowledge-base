"""问题2: 可重试异常的边界

分析 LLMError 的不同场景, 设计 retryable_exceptions 参数.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, ParamSpec, TypeVar


class ErrorCategory(Enum):
    """LLM错误分类."""
    RETRYABLE = auto()      # 应该重试
    NOT_RETRYABLE = auto()  # 不应该重试
    UNKNOWN = auto()        # 需要判断


@dataclass
class LLMError(Exception):
    """增强版 LLMError, 包含状态码."""
    message: str
    status_code: int | None = None
    
    def category(self) -> ErrorCategory:
        """根据状态码判断错误类型."""
        if self.status_code is None:
            # 网络层错误 (超时, 连接失败等)
            return ErrorCategory.RETRYABLE
        
        if self.status_code in (429, 500, 502, 503, 504):
            # 429: 限流
            # 500/502/503/504: 服务端错误
            return ErrorCategory.RETRYABLE
        
        if self.status_code in (400, 401, 403, 404):
            # 400: 参数错误
            # 401: 认证失败
            # 403: 权限不足
            # 404: 资源不存在
            return ErrorCategory.NOT_RETRYABLE
        
        return ErrorCategory.UNKNOWN


# ========== 方案对比 ==========
print("""
=== 可重试异常边界设计方案对比 ===

方案A: 只接受异常类型列表
------------------------
@llm_retry(retryable_exceptions=(LLMError, TimeoutError))
def call_llm():
    ...

优点:
- 简单直接
- 用户完全控制

缺点:
- 需要用户了解哪些异常应该重试
- 无法细粒度控制 (如 401 不应该重试但 429 应该)
- 如果有多种错误类型, 列表会很长


方案B: 接受 should_retry 回调
-----------------------------
def should_retry(e: Exception) -> bool:
    if isinstance(e, LLMError):
        return e.status_code in (429, 500, 503)
    return isinstance(e, TimeoutError)

@llm_retry(should_retry=should_retry)
def call_llm():
    ...

优点:
- 最灵活, 可以完全自定义逻辑
- 可以检查异常属性 (如 status_code)

缺点:
- 需要用户编写回调函数
- 增加了使用复杂度


方案C: 内置智能判断 + 可覆盖
-----------------------------
@llm_retry()  # 使用内置判断
@llm_retry(retryable_status_codes={429, 503})  # 覆盖状态码
@llm_retry(should_retry=custom_logic)  # 完全自定义

def call_llm():
    ...

内置判断逻辑:
- 网络错误 (无 status_code): 重试
- 429 限流: 重试
- 500/502/503/504: 重试
- 400/401/403/404: 不重试

优点:
- 开箱即用, 大多数场景无需配置
- 可以通过参数微调
- 可以传入自定义函数覆盖

缺点:
- 装饰器内部需要处理 HTTP 细节
- 逻辑稍微复杂


=== 推荐方案 ===
采用方案C: 内置智能判断 + 可覆盖

默认行为:
1. 检查异常是否是 LLMError
2. 根据 status_code 判断:
   - 无 status_code (网络错误): 重试
   - 429, 500-504: 重试
   - 400-404: 不重试
3. 其他异常: 不重试

可配置项:
- retryable_exceptions: Tuple[Type[Exception], ...] = (LLMError,)
- retryable_status_codes: Set[int] = {429, 500, 502, 503, 504}
- should_retry: Optional[Callable[[Exception], bool]] = None

优先级: should_retry > status_codes > 默认逻辑
""")


# ========== 示例实现 ==========
P = ParamSpec("P")
T = TypeVar("T")


def llm_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 180.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    retryable_status_codes: set[int] | None = None,
    should_retry: Callable[[Exception], bool] | None = None,
):
    """LLM 调用重试装饰器.
    
    Args:
        max_retries: 最大重试次数
        base_delay: 初始延迟 (秒)
        max_delay: 最大延迟 (秒)
        retryable_exceptions: 应该重试的异常类型
        retryable_status_codes: 应该重试的 HTTP 状态码 (仅对 LLMError 有效)
        should_retry: 自定义重试判断函数, 优先级最高
    """
    default_status_codes = {429, 500, 502, 503, 504}
    status_codes = retryable_status_codes or default_status_codes
    
    def _default_should_retry(e: Exception) -> bool:
        """默认重试判断逻辑."""
        # 检查异常类型
        if not isinstance(e, retryable_exceptions):
            return False
        
        # 检查状态码
        if isinstance(e, LLMError) and e.status_code is not None:
            return e.status_code in status_codes
        
        # 网络错误 (无 status_code) 默认重试
        return True
    
    retry_checker = should_retry or _default_should_retry
    
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        from functools import wraps
        import time
        
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_error: Exception | None = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    
                    if attempt < max_retries and retry_checker(e):
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        print(f"  可重试错误, {delay:.1f}s后重试: {e}")
                        time.sleep(delay)
                    else:
                        raise
            
            raise last_error or RuntimeError("Unknown error")
        
        return wrapper
    return decorator


# ========== 使用示例 ==========
print("\n=== 使用示例 ===\n")


# 示例1: 使用默认行为
@llm_retry(max_retries=2, base_delay=0.1)
def call_with_default():
    """使用内置智能判断."""
    raise LLMError("限流", status_code=429)


# 示例2: 自定义状态码
@llm_retry(
    max_retries=2,
    base_delay=0.1,
    retryable_status_codes={503, 504},  # 只重试这两个
)
def call_custom_status():
    """只重试特定的状态码."""
    raise LLMError("限流", status_code=429)  # 这个不会重试!


# 示例3: 完全自定义判断
def my_retry_logic(e: Exception) -> bool:
    """自定义逻辑: 只有特定消息才重试."""
    return isinstance(e, LLMError) and "暂时" in str(e.message)


@llm_retry(max_retries=2, base_delay=0.1, should_retry=my_retry_logic)
def call_custom_logic():
    """使用自定义判断."""
    raise LLMError("暂时不可用", status_code=500)


# 测试
try:
    call_with_default()
except LLMError as e:
    print(f"示例1 (默认) 重试3次后失败: {e}")

try:
    call_custom_status()
except LLMError as e:
    print(f"示例2 (自定义状态码) 直接失败不重试: {e}")

try:
    call_custom_logic()
except LLMError as e:
    print(f"示例3 (自定义逻辑) 重试3次后失败: {e}")

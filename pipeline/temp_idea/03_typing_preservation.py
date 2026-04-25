"""问题4: 如何完整保持类型签名?

Python 3.10+ 中保持装饰器类型签名的最佳实践:
1. ParamSpec - 保留参数类型
2. TypeVar - 保留返回值类型
3. 对比: 不使用 vs 使用类型保持
"""

from functools import wraps
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


# ========== 不使用类型保持 (BAD) ==========
def retry_bad(max_retries: int = 3):
    """不保持类型的装饰器 - IDE 会丢失类型信息."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ========== 使用 ParamSpec + TypeVar (GOOD) ==========
def retry_good(max_retries: int = 3):
    """完整保持类型的装饰器.
    
    类型参数:
        P: ParamSpec - 捕获所有位置参数和关键字参数的类型
        T: TypeVar - 捕获返回值的类型
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ========== 测试类型保持效果 ==========
class LLMProvider:
    pass


class LLMResponse:
    content: str


class LLMError(Exception):
    pass


# 使用 BAD 装饰器
@retry_bad(max_retries=3)
def call_llm_bad(
    provider: LLMProvider,
    messages: list[dict[str, str]],
    max_tokens: int = 1000,
    temperature: float = 0.7,
) -> LLMResponse:
    """调用LLM - 类型已丢失.
    
    在IDE中:
    - call_llm_bad() 的参数没有类型提示
    - 返回值显示为 Any
    """
    return LLMResponse()


# 使用 GOOD 装饰器
@retry_good(max_retries=3)
def call_llm_good(
    provider: LLMProvider,
    messages: list[dict[str, str]],
    max_tokens: int = 1000,
    temperature: float = 0.7,
) -> LLMResponse:
    """调用LLM - 类型完整保留.
    
    在IDE中:
    - call_llm_good() 的参数有完整类型提示
    - 返回值正确显示为 LLMResponse
    - 跳转到定义可以正常工作
    """
    return LLMResponse()


# ========== 验证 ==========
def test_typing():
    """测试类型保持效果."""
    provider = LLMProvider()
    messages = [{"role": "user", "content": "hello"}]
    
    # BAD 版本: IDE无法推断参数类型
    # 把鼠标悬停在 call_llm_bad 上看不到参数提示
    response_bad = call_llm_bad(provider, messages)
    # response_bad 被推断为 Any, 没有 content 属性提示
    
    # GOOD 版本: IDE有完整类型提示
    # 把鼠标悬停在 call_llm_good 上能看到所有参数类型
    response_good = call_llm_good(provider, messages, max_tokens=2000)
    # response_good 被正确推断为 LLMResponse, 有 content 属性提示
    
    print("类型保持测试完成")
    print(f"response_bad 类型: {type(response_bad)}")
    print(f"response_good 类型: {type(response_good)}")


# ========== 其他选项对比 ==========
print("""
=== Python 类型保持方案对比 ===

1. ParamSpec + TypeVar (推荐)
   优点: 完整保留参数和返回类型, Python 3.10+ 原生支持
   缺点: 需要导入 typing 模块

2. Callable[..., T] (不推荐)
   缺点: 丢失所有参数类型信息, 返回值需要显式指定
   
3. 泛型装饰器类 (复杂场景)
   class RetryDecorator(Generic[P, T]): ...
   优点: 可以携带状态, 支持更复杂的类型操作
   缺点: 代码冗长

4. Protocol (结构性类型)
   用于定义结构类型, 不适合装饰器

结论: 对于 @llm_retry, ParamSpec + TypeVar 是最佳选择.
""")


if __name__ == "__main__":
    test_typing()

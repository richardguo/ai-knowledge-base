## Context

当前 `pipeline/model_client.py` 中的 `chat_with_retry` 函数（第 326-373 行）实现了 LLM 调用的重试逻辑：
- 指数退避：`delay = base_delay * (2 ** attempt)`
- 异常捕获：仅捕获 `LLMError`
- 无 max_delay 上限、无 jitter
- 函数式 API，非装饰器

`pipeline.py` 的 `Step2Analyzer._analyze_batch` 通过直接调用 `chat_with_retry` 使用此能力。未来新增的 LLM 调用点如果也需要重试，必须手动复制逻辑或依赖 `chat_with_retry` 的函数签名——两者都不理想。

约束：
- 项目使用 Python 3.12
- 当前所有 LLM 调用均为同步（`time.sleep`），暂无异步调用点
- `LLMError` 携带 `status_code` 属性，可用于区分可重试/不可重试错误
- Python 环境路径：`D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat`
- 环境变量从项目根目录 `.env` 文件读取

## Goals / Non-Goals

**Goals:**
- 将重试逻辑抽象为 `@llm_retry` 装饰器，任何 LLM 调用函数加一行即可获得重试能力
- 提供异步版本 `@llm_retry_async`，为未来异步 LLM 调用做好准备
- 内置智能异常判断（基于 `retryable_exceptions` + `retryable_status_codes`），默认值覆盖常见场景
- RateLimit 场景单独设置最大重试次数（`max_retries_on_rate_limit`）
- 指数退避 + jitter + max_delay 上限，避免过长等待和惊群效应
- 可选的 `on_retry` 回调，支持重试时清理副作用
- 重构 `chat_with_retry` 使其内部委托给 `@llm_retry`，消除重复逻辑
- 完整的类型签名保持（ParamSpec + TypeVar）
- 解决 `LLMError` 循环导入问题

**Non-Goals:**
- 不做 provider 级 fallback（如 GLM 挂了切换 DeepSeek）
- 不做 `should_retry` 自定义回调函数（`retryable_exceptions` + `retryable_status_codes` 已足够）
- 不做统一的同步/异步装饰器（类型提示问题，详见 proposal 探索参考）
- 不做装饰器层面的幂等性保证（由业务层负责）

## Decisions

### D1: 两个独立装饰器，而非统一装饰器

**选择**：`@llm_retry`（同步）+ `@llm_retry_async`（异步），分两个函数

**替代方案**：运行时用 `inspect.iscoroutinefunction()` 检测，返回不同包装器

**理由**：
1. 统一装饰器的返回类型必须声明为 `Union[T, Awaitable[T]]`，IDE 无法准确推断
2. 两个装饰器各自类型签名清晰：`Callable[P, T] -> Callable[P, T]`
3. Python 生态惯例（`tenacity` 等）也是分开设

### D2: 异常判断策略 = retryable_exceptions + retryable_status_codes

**选择**：组合式参数

```python
@llm_retry(
    retryable_exceptions=(LLMError,),
    retryable_status_codes={429, 500, 502, 503, 504},
)
```

判断逻辑：
1. 异常不在 `retryable_exceptions` → 不重试
2. 异常是 `LLMError` 且有 `status_code` → `status_code in retryable_status_codes` 才重试
3. 异常是 `LLMError` 但无 `status_code`（网络错误）→ 重试
4. 其他 → 不重试

**RateLimit 单独处理**：
- 检测方式：`status_code == 429`
- 混合场景计数：统一计数器，每次失败时根据当前错误类型选择检查哪个阈值
  - 当前错误是 429 → 检查 `max_retries_on_rate_limit`
  - 当前错误是其他可重试错误 → 检查 `max_retries`

**替代方案**：
- 只接受异常类型列表（无法区分 401 vs 429）
- `should_retry` 回调（过度灵活，增加使用复杂度）

**理由**：组合方案在简洁性和灵活性之间取得平衡——默认值覆盖 90% 场景，极端情况可调参数。

### D3: 指数退避 + jitter + max_delay

**退避公式**：
```python
delay = min(base_delay * (exponential_base ** attempt), max_delay)
if jitter:
    delay *= (0.5 + random.random() * 0.5)  # 50%~100% 抖动
```

**参数默认值**：
| 参数 | 默认值 | 含义 |
|------|--------|------|
| `max_retries` | 3 | 普通错误最大重试次数 |
| `max_retries_on_rate_limit` | 20 | RateLimit 场景最大重试次数 |
| `base_delay` | 1.0 | 初始等待秒数 |
| `max_delay` | 180.0 | 最大等待秒数（3 分钟） |
| `exponential_base` | 2 | 指数基数 |
| `jitter` | True | 是否添加随机抖动 |

**理由**：jitter 避免多并发请求同时重试（惊群效应）；max_delay 防止指数增长导致等太久。

### D4: on_retry 可选回调

**签名**：`on_retry: Callable[[Exception, int], None] | None = None`

- `exception`：触发重试的异常
- `attempt`：当前是第几次重试（从 1 开始）

**不提供 on_retry 时**：副作用可能重复执行（可接受）

**替代方案**：
- 不提供回调（过于限制）
- 装饰器自动清理副作用（不可能做到通用）

### D5: 类型签名保持使用 ParamSpec + TypeVar

```python
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")

def llm_retry(...) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            ...
        return wrapper
    return decorator
```

**理由**：完整保留参数类型和返回值类型，IDE 提示正常工作。Python 3.12 原生支持。

### D6: chat_with_retry 重构策略

**选择**：`chat_with_retry` 内部使用 `@llm_retry` 装饰一个内部函数

```python
def chat_with_retry(provider, messages, ..., max_retries=3, max_retries_on_rate_limit=20, base_delay=1.0, ...):
    @llm_retry(max_retries=max_retries, max_retries_on_rate_limit=max_retries_on_rate_limit, base_delay=base_delay, ...)
    def _call():
        return provider.chat(messages=messages, model=model, timeout=timeout, **kwargs)
    return _call()
```

**理由**：
- `chat_with_retry` 的公开签名和行为不变（向后兼容）
- 重试逻辑只维护一份（在 `@llm_retry` 中）
- 不破坏现有调用方

### D7: 模块位置

**选择**：装饰器放 `utils/retry.py`，`LLMError` 迁移到 `utils/exceptions.py`

**文件结构**：
```
utils/
├── __init__.py          # 导出 LLMError, llm_retry, llm_retry_async
├── exceptions.py        # LLMError 异常类
└── retry.py             # @llm_retry, @llm_retry_async 装饰器
```

**理由**：
- 解决 `pipeline/model_client.py` 和 `utils/retry.py` 之间的循环导入问题
- `utils/` 目录结构清晰，职责分离
- `__init__.py` 导出符号，使用方便：`from utils import llm_retry, LLMError`

**受影响的导入**：
- `pipeline/model_client.py` → 从 `utils.exceptions` 导入 `LLMError`
- `pipeline/pipeline.py` → 从 `utils.exceptions` 导入 `LLMError`

### D8: 日志策略

**选择**：装饰器内部记录日志

| 场景 | 日志级别 | 格式 |
|------|----------|------|
| 重试时 | `logger.warning` | `LLM 调用失败 (尝试 {attempt}/{max_retries}), {delay:.1f}秒后重试: {exception}` |
| 最终失败 | `logger.error` | `LLM 调用失败，已达最大重试次数: {exception}` |
| 重试成功后 | 不记录 | N/A |

**理由**：
- 与现有 `chat_with_retry` 行为一致
- 日志信息包含异常类型，可区分 RateLimit、connection error、timeout 等场景
- 重试成功不记录，避免日志噪音

### D9: 测试策略

**单元测试**：
- 位置：`tests/unit/test_retry.py`
- 使用 `pytest-mock` 模拟异常，不依赖真实 API
- 覆盖场景：
  1. 正常调用（无异常）→ 直接返回结果
  2. 第 1 次失败后成功 → 验证重试次数和返回值
  3. 达到 max_retries 后仍失败 → 抛出异常
  4. 非 retryable_exceptions 异常 → 不重试，直接抛出
  5. 状态码在 retryable_status_codes 中 → 重试
  6. 状态码不在 retryable_status_codes 中（如 401）→ 不重试
  7. 无 status_code 的异常（网络错误）→ 重试
  8. 纯 RateLimit 错误，达到 max_retries_on_rate_limit 后仍失败
  9. 混合场景：RateLimit + ServerError，验证计数逻辑
  10. 验证指数退避计算正确
  11. 验证 max_delay 上限生效
  12. 验证 jitter 范围（50%~100%）
  13. on_retry 回调被正确调用
  14. on_retry 参数正确（exception, attempt）
  15. 异步版与同步版行为一致
  16. max_retries=0 → 不重试
  17. base_delay=0 → 立即重试（无等待）

**集成测试**：
- 位置：`tests/integration/test_retry_integration.py`
- 需要 `.env` 配置：`ZHIPU_API_BASE_URL`, `ZHIPU_API_KEY`, `ZHIPU_MODEL_ID` 或 `LLM_API_BASE`, `LLM_API_KEY`, `LLM_MODEL_ID`
- 无配置时跳过测试（`pytest.mark.skipif`）
- 覆盖场景：
  1. 真实调用 LLM API 成功
  2. RateLimit 触发：5 并发，2-3 轮
  3. 验证重试日志输出

**测试依赖**：
```txt
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-cov>=4.1.0
pytest-mock>=3.12.0
```

### D10: 异常处理

**选择**：最终失败时抛出最后一次的原始异常

```python
raise last_error or LLMError("未知错误")
```

**理由**：与现有 `chat_with_retry` 行为一致，保持异常链。

### D11: 函数元数据保留

**选择**：使用 `@wraps(func)` 保留函数元数据

**理由**：保留 `__name__`, `__doc__` 等信息，便于调试和文档生成。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 异步函数误用同步装饰器 → 协程不被 await | 文档明确警告；`@llm_retry_async` 命名清晰区分 |
| 副作用在重试时重复执行（如 cost 追踪） | 提供 `on_retry` 回调；文档建议幂等设计或延迟副作用 |
| 装饰器参数过多，使用门槛高 | 合理默认值，90% 场景只需 `@llm_retry` 无参调用 |
| `chat_with_retry` 重构引入回归 | 保持其公开签名不变；单元测试覆盖 |
| 循环导入问题 | 迁移 `LLMError` 到 `utils/exceptions.py`，职责分离 |
| 集成测试依赖外部 API | 无配置时跳过测试，不影响 CI |

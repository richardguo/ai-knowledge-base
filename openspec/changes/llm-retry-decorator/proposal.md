## Why

`model_client.py` 中的 `chat_with_retry` 函数实现了 LLM 调用的重试逻辑（指数退避 + 异常捕获），但它是一个独立函数，其他需要重试的 LLM 调用点无法简单复用。当前 `pipeline.py` 的 `Step2Analyzer._analyze_batch` 直接调用 `chat_with_retry`，而未来新增的 LLM 调用点（如单条分析、摘要生成等）如果也想获得重试能力，必须手动复制重试逻辑或依赖 `chat_with_retry` 的函数签名——两者都不理想。

将重试机制抽象为装饰器 `@llm_retry`，让任何 LLM 调用函数只需加一行装饰即可获得重试能力，是更符合 Python 惯用做法的复用方式。

## What Changes

- 新增 `@llm_retry` 装饰器：同步函数的重试装饰器，支持指数退避 + jitter + max_delay 上限
- 新增 `@llm_retry_async` 装饰器：异步函数的重试装饰器（与同步版并行提供，非统一装饰器）
- 新增 `max_retries_on_rate_limit` 参数：RateLimit 场景单独设置最大重试次数（默认 20）
- 新增 `on_retry` 可选回调参数：重试触发时通知调用方，用于清理副作用
- 迁移 `LLMError` 到 `utils/exceptions.py`：解决循环导入问题
- 重构 `chat_with_retry` 函数：内部委托给 `@llm_retry` 装饰器，消除重复逻辑
- 新增测试依赖：`pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-mock`

**不做：**
- 不做 provider 级 fallback（例如 GLM 挂了切换到 DeepSeek）
- 不做 `should_retry` 自定义判断回调（用 `retryable_exceptions` + `retryable_status_codes` 组合即可覆盖需求）

## Capabilities

### New Capabilities
- `llm-retry`: LLM 调用重试装饰器，提供可配置的指数退避重试能力，包含同步版 `@llm_retry` 和异步版 `@llm_retry_async`

### Modified Capabilities

（无现有 spec 需要修改）

## Impact

- **代码变更**：
  - `utils/retry.py` — 新增 `@llm_retry` 和 `@llm_retry_async` 装饰器
  - `utils/exceptions.py` — 迁移 `LLMError` 类
  - `utils/__init__.py` — 导出 `LLMError`, `llm_retry`, `llm_retry_async`
  - `pipeline/model_client.py` — 删除 `LLMError` 定义，更新导入，重构 `chat_with_retry`
  - `pipeline/pipeline.py` — 更新 `LLMError` 导入路径
- **API 变更**：`chat_with_retry` 函数签名和行为保持不变（向后兼容），新增 `llm_retry` / `llm_retry_async` 装饰器作为公开 API
- **依赖**：
  - 运行时无新增第三方依赖（`time`, `random`, `asyncio`, `functools`, `typing` 均为标准库）
  - 测试依赖：新增 `requirements-dev.txt`，包含 `pytest>=8.0.0`, `pytest-asyncio>=0.23.0`, `pytest-cov>=4.1.0`, `pytest-mock>=3.12.0`
- **下游影响**：`pipeline.py` 中 `Step2Analyzer._analyze_batch` 的 `chat_with_retry` 调用无需变更；未来新增的 LLM 调用点可直接使用 `@llm_retry`

## 探索参考信息

### 同步 vs 异步装饰器的差异

同步和异步装饰器的核心差异：

| 方面 | 同步 `@llm_retry` | 异步 `@llm_retry_async` |
|------|-------------------|------------------------|
| 等待方式 | `time.sleep()` 阻塞 | `asyncio.sleep()` 非阻塞 |
| 包装器签名 | `def wrapper(*args, **kwargs) -> T` | `async def wrapper(*args, **kwargs) -> T` |
| 内部调用 | `return func(*args, **kwargs)` | `return await func(*args, **kwargs)` |
| 适用函数 | `def call_llm(...)` | `async def call_llm(...)` |

**为什么不用统一装饰器（运行时检测 `inspect.iscoroutinefunction`）：**

1. **类型提示问题**：统一装饰器的返回类型必须声明为 `Union[T, Awaitable[T]]`，IDE 无法根据被装饰函数是同步还是异步来准确推断
2. **代码复杂度**：统一装饰器需要在一个 `decorator` 函数内维护两条分支路径，增加维护成本
3. **Python 惯例**：Python 生态中（如 `tenacity`、`backoff`）通常对同步/异步提供分开的 API 或通过文档说明限制

**异步函数使用同步装饰器会怎样：**

```python
@llm_retry              # 同步装饰器
async def call_async():  # 异步函数
    return "result"

result = call_async()    # 返回协程对象，而非结果
# 协程从未被 await → 函数体不会执行
# 或产生 "coroutine was never awaited" 警告
```

**结论**：提供两个独立的装饰器 `@llm_retry` 和 `@llm_retry_async`，用户根据函数类型自行选择。类型提示清晰，代码简单。

### 可重试异常的边界设计

采用「异常类型 + 状态码」组合方案，不做 `should_retry` 回调：

```python
@llm_retry(
    retryable_exceptions=(LLMError,),                      # 哪些异常类型值得检查
    retryable_status_codes={429, 500, 502, 503, 504},      # 这些状态码才重试
)
```

判断逻辑：
1. 异常不在 `retryable_exceptions` 中 → 不重试
2. 异常是 `LLMError` 且有 `status_code` → 仅当 `status_code` 在 `retryable_status_codes` 中才重试
3. 异常是 `LLMError` 但无 `status_code`（网络错误）→ 重试
4. 其他异常 → 不重试

### RateLimit 单独处理

RateLimit（status_code=429）场景需要更长重试时间，单独设置最大重试次数：

```python
@llm_retry(
    max_retries=3,                    # 普通错误最大重试次数
    max_retries_on_rate_limit=20,     # RateLimit 场景最大重试次数
)
```

**混合场景计数逻辑**：统一计数器，每次失败时根据当前错误类型选择检查哪个阈值：
- 当前错误是 429 → 检查是否达到 `max_retries_on_rate_limit`
- 当前错误是其他可重试错误 → 检查是否达到 `max_retries`

**chat_with_retry 兼容性**：`chat_with_retry` 新增 `max_retries_on_rate_limit` 参数，透传给 `@llm_retry`，但通常使用默认值即可。

### 指数退避天花板 + jitter

参数：`max_retries=3`, `max_retries_on_rate_limit=20`, `base_delay=1.0`, `max_delay=180.0`, `exponential_base=2`, `jitter=True`

退避公式：
```python
delay = min(base_delay * (exponential_base ** attempt), max_delay)
if jitter:
    delay *= (0.5 + random.random() * 0.5)  # 50%~100% 抖动
```

### on_retry 回调与幂等性

- 装饰器只负责「重试」行为，幂等性由业务层保证
- `on_retry` 是可选回调，签名：`on_retry(exception: Exception, attempt: int) -> None`
- 用户不提供 `on_retry` 时，副作用可能重复执行（如 `_cost_tracker.record()` 被多次调用），这是可接受的行为

### 日志策略

装饰器内部记录日志：
- **重试时**：`logger.warning`，格式：`LLM 调用失败 (尝试 {attempt}/{max_retries}), {delay:.1f}秒后重试: {exception}`
- **最终失败时**：`logger.error`，格式：`LLM 调用失败，已达最大重试次数: {exception}`
- **重试成功后**：不记录日志，避免噪音

日志信息包含异常类型，可区分 RateLimit、connection error、timeout 等不同场景。

### 模块结构

```
utils/
├── __init__.py          # 导出 LLMError, llm_retry, llm_retry_async
├── exceptions.py        # LLMError 异常类
└── retry.py             # @llm_retry, @llm_retry_async 装饰器

tests/
├── unit/
│   └── test_retry.py    # 单元测试
└── integration/
    └── test_retry_integration.py  # 集成测试

requirements-dev.txt     # 测试依赖
```

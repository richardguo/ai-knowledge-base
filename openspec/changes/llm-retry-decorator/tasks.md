## 1. 创建模块结构

- [x] 1.1 创建 `utils/exceptions.py`，从 `pipeline/model_client.py` 迁移 `LLMError` 类
- [x] 1.2 创建 `utils/retry.py`，实现 `llm_retry` 和 `llm_retry_async` 装饰器
- [x] 1.3 创建 `utils/__init__.py`，导出 `LLMError`, `llm_retry`, `llm_retry_async`

## 2. 实现 llm_retry 同步装饰器

- [x] 2.1 在 `utils/retry.py` 中实现 `llm_retry` 装饰器：接受 `max_retries`, `max_retries_on_rate_limit`, `base_delay`, `max_delay`, `exponential_base`, `jitter`, `retryable_exceptions`, `retryable_status_codes`, `on_retry` 参数，使用 `ParamSpec` + `TypeVar` 保持类型签名
- [x] 2.2 实现异常判断逻辑：`retryable_exceptions` 类型过滤 → `LLMError.status_code` 检查 → 无 `status_code` 的网络错误默认重试
- [x] 2.3 实现 RateLimit 单独处理：检测 `status_code == 429`，使用 `max_retries_on_rate_limit` 阈值
- [x] 2.4 实现指数退避逻辑：`delay = min(base_delay * (exponential_base ** attempt), max_delay)`，jitter 时乘以 `[0.5, 1.0)` 随机因子
- [x] 2.5 实现 `on_retry` 回调：重试前调用 `on_retry(exception, attempt)`，`on_retry=None` 时跳过
- [x] 2.6 实现日志记录：重试时 `logger.warning`，最终失败时 `logger.error`

## 3. 实现 llm_retry_async 异步装饰器

- [x] 3.1 实现 `llm_retry_async` 装饰器：参数和行为与 `llm_retry` 一致，使用 `asyncio.sleep()` 替代 `time.sleep()`，包装器为 `async def`
- [x] 3.2 确保 `llm_retry_async` 使用与 `llm_retry` 相同的异常判断和退避逻辑，避免重复代码

## 4. 重构 chat_with_retry

- [x] 4.1 更新 `pipeline/model_client.py`：从 `utils.exceptions` 导入 `LLMError`，删除原有 `LLMError` 定义
- [x] 4.2 重构 `chat_with_retry`：内部定义一个被 `@llm_retry` 装饰的闭包函数，消除独立的 retry 循环
- [x] 4.3 新增 `max_retries_on_rate_limit` 参数（默认 20），透传给 `@llm_retry`
- [x] 4.4 确保 `chat_with_retry` 的公开签名、参数默认值、返回类型、异常行为保持不变

## 5. 更新导入路径

- [x] 5.1 更新 `pipeline/pipeline.py`：从 `utils.exceptions` 导入 `LLMError`
- [x] 5.2 确保所有现有功能不受影响

## 6. 测试基础设施

- [x] 6.1 创建 `requirements-dev.txt`，包含 `pytest>=8.0.0`, `pytest-asyncio>=0.23.0`, `pytest-cov>=4.1.0`, `pytest-mock>=3.12.0`
- [x] 6.2 创建 `tests/unit/` 目录
- [x] 6.3 创建 `tests/integration/` 目录

## 7. 单元测试

- [x] 7.1 创建 `tests/unit/test_retry.py`
- [x] 7.2 测试正常调用（无异常）→ 直接返回结果
- [x] 7.3 测试第 1 次失败后成功 → 验证重试次数和返回值
- [x] 7.4 测试达到 max_retries 后仍失败 → 抛出异常
- [x] 7.5 测试非 retryable_exceptions 异常 → 不重试，直接抛出
- [x] 7.6 测试状态码在 retryable_status_codes 中 → 重试
- [x] 7.7 测试状态码不在 retryable_status_codes 中（如 401）→ 不重试
- [x] 7.8 测试无 status_code 的异常（网络错误）→ 重试
- [x] 7.9 测试纯 RateLimit 错误，达到 max_retries_on_rate_limit 后仍失败
- [x] 7.10 测试混合场景：RateLimit + ServerError，验证计数逻辑
- [x] 7.11 测试指数退避计算正确
- [x] 7.12 测试 max_delay 上限生效
- [x] 7.13 测试 jitter 范围（50%~100%）
- [x] 7.14 测试 on_retry 回调被正确调用
- [x] 7.15 测试 on_retry 参数正确（exception, attempt）
- [x] 7.16 测试异步版与同步版行为一致
- [x] 7.17 测试 max_retries=0 → 不重试
- [x] 7.18 测试 base_delay=0 → 立即重试（无等待）

## 8. 集成测试

- [x] 8.1 创建 `tests/integration/test_retry_integration.py`
- [x] 8.2 测试真实调用 LLM API 成功（使用 `LLM_API_BASE` 或 `ZHIPU_API_BASE_URL`）
- [x] 8.3 测试 RateLimit 触发：5 并发，2-3 轮，使用 ZHIPU API
- [x] 8.4 验证重试日志输出
- [x] 8.5 无 API 配置时跳过测试（`pytest.mark.skipif`）

## 9. 验证与格式化

- [x] 9.1 激活 Python 环境：`D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat`
- [x] 9.2 安装测试依赖：`pip install -r requirements-dev.txt`
- [x] 9.3 运行单元测试：`pytest tests/unit/test_retry.py -v` (27 passed)
- [x] 9.4 运行集成测试：`pytest tests/integration/test_retry_integration.py -v` (skipped - no API config)
- [x] 9.5 运行覆盖率测试：`pytest --cov=utils tests/` (97% for retry.py)
- [x] 9.6 运行 `black` 格式化变更文件
- [x] 9.7 运行 `pipeline/model_client.py` 的 `__main__` 自测，确认 `chat_with_retry` 行为不变
- [x] 9.8 运行 `pipeline/pipeline.py --dry-run`，确认端到端流程正常

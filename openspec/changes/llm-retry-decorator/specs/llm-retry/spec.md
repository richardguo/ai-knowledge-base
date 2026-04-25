## ADDED Requirements

### Requirement: llm_retry decorator for synchronous functions
The system SHALL provide a `llm_retry` decorator that wraps synchronous functions with configurable retry logic. The decorator SHALL accept the following parameters with defaults:

- `max_retries: int = 3` — maximum number of retry attempts for regular errors
- `max_retries_on_rate_limit: int = 20` — maximum number of retry attempts for RateLimit errors (status_code=429)
- `base_delay: float = 1.0` — initial delay in seconds before first retry
- `max_delay: float = 180.0` — maximum delay in seconds (ceiling for exponential backoff)
- `exponential_base: int = 2` — base for exponential backoff calculation
- `jitter: bool = True` — whether to add random jitter to delay
- `retryable_exceptions: tuple[type[Exception], ...] = (LLMError,)` — exception types eligible for retry
- `retryable_status_codes: set[int] = {429, 500, 502, 503, 504}` — HTTP status codes eligible for retry
- `on_retry: Callable[[Exception, int], None] | None = None` — optional callback invoked on each retry

#### Scenario: Successful call on first attempt
- **WHEN** a function decorated with `@llm_retry` succeeds on the first call
- **THEN** the function returns the result directly with no retry or delay

#### Scenario: Retry on transient failure then success
- **WHEN** a function decorated with `@llm_retry(max_retries=2, base_delay=0.5)` raises an `LLMError` with `status_code=429` on the first call, then succeeds on the second call
- **THEN** the function returns the successful result after one retry with appropriate delay

#### Scenario: Exhaust all retries and raise
- **WHEN** a function decorated with `@llm_retry(max_retries=2)` raises `LLMError(status_code=503)` on every call
- **THEN** the decorator SHALL raise the last exception after 3 total attempts (1 initial + 2 retries)

#### Scenario: Non-retryable exception is raised immediately
- **WHEN** a function decorated with `@llm_retry()` raises `LLMError(status_code=401)`
- **THEN** the decorator SHALL raise the exception immediately without retry

#### Scenario: Exception not in retryable_exceptions is raised immediately
- **WHEN** a function decorated with `@llm_retry(retryable_exceptions=(LLMError,))` raises `ValueError`
- **THEN** the decorator SHALL raise `ValueError` immediately without retry

#### Scenario: LLMError without status_code is retried
- **WHEN** a function decorated with `@llm_retry()` raises `LLMError` with `status_code=None` (network error)
- **THEN** the decorator SHALL retry the call

### Requirement: RateLimit separate retry limit
The decorator SHALL support a separate, higher retry limit for RateLimit errors (HTTP 429).

#### Scenario: RateLimit uses max_retries_on_rate_limit
- **WHEN** a function decorated with `@llm_retry(max_retries=3, max_retries_on_rate_limit=20)` raises `LLMError(status_code=429)` repeatedly
- **THEN** the decorator SHALL retry up to 20 times (not 3)

#### Scenario: Mixed errors use unified counter with threshold selection
- **WHEN** a function decorated with `@llm_retry(max_retries=3, max_retries_on_rate_limit=20)` raises a sequence of errors: 429, 429, 500, 429...
- **THEN** the decorator SHALL use a unified counter, but check against different thresholds based on the current error type:
  - Current error is 429 → check against `max_retries_on_rate_limit` (20)
  - Current error is other retryable error → check against `max_retries` (3)

#### Scenario: Regular error exhausts max_retries even if RateLimit limit is higher
- **WHEN** a function decorated with `@llm_retry(max_retries=3, max_retries_on_rate_limit=20)` raises `LLMError(status_code=503)` on every call
- **THEN** the decorator SHALL raise after 3 retries (not 20), because 503 is not a RateLimit error

### Requirement: Exponential backoff with max_delay and jitter
The delay between retries SHALL follow exponential backoff with an upper bound and optional jitter.

Delay formula:
```
delay = min(base_delay * (exponential_base ** attempt), max_delay)
if jitter:
    delay *= (0.5 + random.random() * 0.5)
```

Where `attempt` starts at 0 for the first retry.

#### Scenario: Delay is capped by max_delay
- **WHEN** `base_delay=1.0, max_delay=10.0, exponential_base=2`, and the function fails on attempt 5 (delay would be 32s without cap)
- **THEN** the actual delay SHALL be at most `max_delay` (10.0s)

#### Scenario: Jitter reduces delay between 50% and 100%
- **WHEN** `jitter=True` and the calculated delay before jitter is 8.0s
- **THEN** the actual delay SHALL be in the range [4.0, 8.0]

#### Scenario: No jitter when disabled
- **WHEN** `jitter=False` and the calculated delay is 8.0s
- **THEN** the actual delay SHALL be exactly 8.0s

### Requirement: Exception filtering by status code
When the caught exception is an `LLMError` with a `status_code` attribute, the decorator SHALL only retry if the `status_code` is in `retryable_status_codes`. When `status_code` is `None` (network-level error), the decorator SHALL retry.

#### Scenario: Status code 429 is retried by default
- **WHEN** a function raises `LLMError(status_code=429)` and no custom `retryable_status_codes` is provided
- **THEN** the decorator SHALL retry (429 is in the default set)

#### Scenario: Status code 401 is not retried by default
- **WHEN** a function raises `LLMError(status_code=401)` and no custom `retryable_status_codes` is provided
- **THEN** the decorator SHALL raise immediately without retry

#### Scenario: Custom retryable_status_codes overrides default
- **WHEN** a function is decorated with `@llm_retry(retryable_status_codes={503})` and raises `LLMError(status_code=429)`
- **THEN** the decorator SHALL raise immediately without retry (429 not in custom set)

### Requirement: on_retry optional callback
The decorator SHALL accept an optional `on_retry` callback that is invoked after each failed attempt before the delay. The callback signature SHALL be `(exception: Exception, attempt: int) -> None`, where `attempt` is the retry number starting from 1.

#### Scenario: on_retry is called on each retry
- **WHEN** a function decorated with `@llm_retry(max_retries=2, on_retry=callback)` fails twice then succeeds
- **THEN** `callback` SHALL be called twice: once with `attempt=1`, once with `attempt=2`

#### Scenario: on_retry is not called on success
- **WHEN** a function decorated with `@llm_retry(on_retry=callback)` succeeds on the first call
- **THEN** `callback` SHALL NOT be called

#### Scenario: No callback when on_retry is None
- **WHEN** a function decorated with `@llm_retry(on_retry=None)` fails and is retried
- **THEN** no callback is invoked; the retry proceeds normally

### Requirement: Logging during retry
The decorator SHALL log retry attempts and final failures.

#### Scenario: Warning log on retry
- **WHEN** a function decorated with `@llm_retry()` fails and is being retried
- **THEN** the decorator SHALL log at `WARNING` level with format: `LLM 调用失败 (尝试 {attempt}/{max_retries}), {delay:.1f}秒后重试: {exception}`

#### Scenario: Error log on final failure
- **WHEN** a function decorated with `@llm_retry()` exhausts all retries
- **THEN** the decorator SHALL log at `ERROR` level with format: `LLM 调用失败，已达最大重试次数: {exception}`

#### Scenario: No log on retry success
- **WHEN** a function decorated with `@llm_retry()` fails once then succeeds on retry
- **THEN** the decorator SHALL NOT log a "retry success" message

### Requirement: llm_retry_async decorator for asynchronous functions
The system SHALL provide a `llm_retry_async` decorator with the same parameters and behavior as `llm_retry`, but designed for `async def` functions. The decorator SHALL use `asyncio.sleep()` instead of `time.sleep()` for non-blocking delays.

#### Scenario: Async function retries and succeeds
- **WHEN** an `async def` function decorated with `@llm_retry_async(max_retries=1, base_delay=0.1)` raises `LLMError(status_code=429)` on the first call, then succeeds
- **THEN** the coroutine returns the successful result after one retry

#### Scenario: Async function exhausts retries
- **WHEN** an `async def` function decorated with `@llm_retry_async(max_retries=1)` raises on every call
- **THEN** the last exception is raised after 2 total attempts

### Requirement: Type signature preservation
Both `llm_retry` and `llm_retry_async` SHALL preserve the decorated function's type signature using `functools.wraps`, `ParamSpec`, and `TypeVar`. IDEs SHALL be able to infer parameter types and return type of the decorated function.

#### Scenario: Type hints are preserved
- **WHEN** a function `def f(provider: LLMProvider, messages: list[dict[str, str]]) -> LLMResponse` is decorated with `@llm_retry()`
- **THEN** the decorated function's type signature SHALL be `Callable[[LLMProvider, list[dict[str, str]]], LLMResponse]`

### Requirement: Module location
The `llm_retry` and `llm_retry_async` decorators SHALL be located in `utils/retry.py`. The `LLMError` exception class SHALL be located in `utils/exceptions.py`. Both SHALL be exported from `utils/__init__.py`.

#### Scenario: Import from utils package
- **WHEN** a user writes `from utils import llm_retry, llm_retry_async, LLMError`
- **THEN** all three symbols SHALL be available

### Requirement: chat_with_retry refactored to use llm_retry
The existing `chat_with_retry` function SHALL be refactored to delegate retry logic to the `llm_retry` decorator internally. Its public API (function signature, parameters, return type, and behavior) SHALL remain unchanged.

#### Scenario: chat_with_retry behavior unchanged
- **WHEN** `chat_with_retry(provider, messages, max_retries=3, base_delay=1.0)` is called
- **THEN** it SHALL behave identically to the current implementation (retry on LLMError, exponential backoff, raise after exhaustion)

#### Scenario: chat_with_retry uses decorator internally
- **WHEN** reading the implementation of `chat_with_retry`
- **THEN** it SHALL contain an internal function decorated with `@llm_retry`, and no standalone retry loop

#### Scenario: chat_with_retry supports max_retries_on_rate_limit
- **WHEN** `chat_with_retry(provider, messages, max_retries_on_rate_limit=20)` is called
- **THEN** the parameter SHALL be passed to the internal `@llm_retry` decorator

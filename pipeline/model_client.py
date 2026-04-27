"""统一的 LLM 调用客户端模块。

支持多种 OpenAI 兼容 API 的模型提供商，包括 DeepSeek、Qwen、GLM、OpenAI 等。
通过环境变量配置 API Base URL、API Key 和模型 ID。

环境变量:
    LLM_API_BASE: API 基础地址，默认为 GLM API
    LLM_API_KEY: API 密钥
    LLM_MODEL_ID: 模型标识符

使用示例:
    >>> from pipeline.model_client import quick_chat
    >>> response = quick_chat("你好，请介绍一下自己")
    >>> print(response.content)
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from utils import LLMError, llm_retry

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Usage:
    """Token 使用量统计。

    Attributes:
        prompt_tokens: 提示词消耗的 Token 数量。
        completion_tokens: 生成内容消耗的 Token 数量。
        total_tokens: 总消耗的 Token 数量。
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        """转换为字典格式。

        Returns:
            包含 Token 使用量的字典。
        """
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class LLMResponse:
    """LLM 响应数据结构。

    Attributes:
        content: 生成的文本内容。
        usage: Token 使用量统计。
        model: 实际使用的模型标识符。
        finish_reason: 生成结束原因。
    """

    content: str
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    finish_reason: str = ""


@dataclass
class ModelPricing:
    """模型定价信息（单位：CNY/百万 Tokens）。

    Attributes:
        prompt_price: 提示词单价（每百万 Token）。
        completion_price: 生成内容单价（每百万 Token）。
    """

    prompt_price: float
    completion_price: float


MODEL_PRICING: dict[str, ModelPricing] = {
    "deepseek": ModelPricing(prompt_price=1, completion_price=2),
    "qwen": ModelPricing(prompt_price=4, completion_price=12),
    "gpt-4o-mini": ModelPricing(prompt_price=150, completion_price=600),
    "minimax": ModelPricing(prompt_price=2, completion_price=8),
    "glm-4.7": ModelPricing(prompt_price=4, completion_price=16),
}

DEFAULT_PRICING = ModelPricing(prompt_price=2, completion_price=8)


class LLMProvider(ABC):
    """LLM 提供商抽象基类。

    定义了 LLM 调用的标准接口，所有具体实现必须继承此类。
    """

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float = 120.0,
        **kwargs: Any,
    ) -> LLMResponse:
        """发送聊天请求到 LLM。

        Args:
            messages: 消息列表，每条消息包含 role 和 content。
            model: 模型标识符，为 None 时使用默认模型。
            temperature: 生成温度，控制随机性。
            max_tokens: 最大生成 Token 数。
            timeout: 请求超时时间（秒）。
            **kwargs: 其他模型特定参数。

        Returns:
            LLMResponse 对象，包含生成内容和使用量统计。

        Raises:
            LLMError: 当 API 调用失败时抛出。
        """
        pass

    @abstractmethod
    def get_model_pricing(self, model: str) -> ModelPricing:
        """获取模型定价信息。

        Args:
            model: 模型标识符。

        Returns:
            ModelPricing 对象，包含输入输出单价。
        """
        pass


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI 兼容 API 的 LLM 提供商实现。

    支持所有兼容 OpenAI API 格式的服务提供商。

    Attributes:
        api_base: API 基础地址。
        api_key: API 密钥。
        default_model: 默认模型标识符。
    """

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
        enable_token_count: bool | None = None,
    ):
        """初始化提供商实例。

        Args:
            api_base: API 基础地址，为 None 时从环境变量读取。
            api_key: API 密钥，为 None 时从环境变量读取。
            default_model: 默认模型，为 None 时从环境变量读取。
            enable_token_count: 是否启用本地 Token 估算，为 None 时从环境变量读取。
        """
        self.api_base = api_base or os.getenv(
            "LLM_API_BASE", "https://open.bigmodel.cn/api/paas/v4"
        )
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.default_model = default_model or os.getenv("LLM_MODEL_ID", "glm-4.7")

        if enable_token_count is not None:
            self.enable_token_count = enable_token_count
        else:
            env_val = os.getenv("LLM_ENABLE_TOKEN_COUNT", "false").lower()
            self.enable_token_count = env_val in ("true", "1", "yes")

        if not self.api_key:
            raise LLMError("缺少 API Key，请设置 LLM_API_KEY 环境变量")

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float = 120.0,
        **kwargs: Any,
    ) -> LLMResponse:
        """发送聊天请求到 OpenAI 兼容 API。

        Args:
            messages: 消息列表，每条消息包含 role 和 content。
            model: 模型标识符，为 None 时使用默认模型。
            temperature: 生成温度，控制随机性。
            max_tokens: 最大生成 Token 数。
            timeout: 请求超时时间（秒）。
            **kwargs: 其他模型特定参数。

        Returns:
            LLMResponse 对象，包含生成内容和使用量统计。

        Raises:
            LLMError: 当 API 调用失败时抛出。
        """
        model = model or self.default_model
        url = f"{self.api_base.rstrip('/')}/chat/completions"

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        payload.update(kwargs)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.debug(f"调用 LLM API: {url}, model={model}")

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, json=payload, headers=headers)

            if response.status_code != 200:
                error_msg = response.text
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", error_msg)
                except Exception:
                    pass
                raise LLMError(
                    f"API 请求失败 (status={response.status_code}): {error_msg}",
                    status_code=response.status_code,
                )

            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise LLMError("API 返回空结果")

            message = choices[0].get("message", {})
            content = message.get("content", "")
            finish_reason = choices[0].get("finish_reason", "")

            usage_data = data.get("usage", {})
            usage = Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )

            if self.enable_token_count:
                estimated_prompt = _count_messages_tokens(messages)
                estimated_completion = _count_text_tokens(content)
                logger.info(
                    f"LLM 响应成功: model={model}, "
                    f"tokens={usage.total_tokens} (prompt={usage.prompt_tokens}, "
                    f"completion={usage.completion_tokens}) | "
                    f"本地估算: prompt≈{estimated_prompt}, completion≈{estimated_completion}"
                )
            else:
                logger.info(
                    f"LLM 响应成功: model={model}, "
                    f"tokens={usage.total_tokens} (prompt={usage.prompt_tokens}, "
                    f"completion={usage.completion_tokens})"
                )

            _cost_tracker.record(usage, self)

            return LLMResponse(
                content=content,
                usage=usage,
                model=data.get("model", model),
                finish_reason=finish_reason,
            )

        except httpx.TimeoutException as e:
            raise LLMError(f"请求超时: {e}") from e
        except httpx.RequestError as e:
            raise LLMError(f"网络请求错误: {e}") from e

    def get_model_pricing(self, model: str) -> ModelPricing:
        """获取模型定价信息。

        Args:
            model: 模型标识符。

        Returns:
            ModelPricing 对象，包含输入输出单价。
        """
        model_lower = model.lower()
        for key, pricing in MODEL_PRICING.items():
            if key in model_lower:
                return pricing
        return DEFAULT_PRICING


def chat_with_retry(
    provider: LLMProvider,
    messages: list[dict[str, str]],
    model: str | None = None,
    max_retries: int = 3,
    max_retries_on_rate_limit: int = 20,
    base_delay: float = 1.0,
    timeout: float = 120.0,
    **kwargs: Any,
) -> LLMResponse:
    """带重试机制的聊天请求。

    当请求失败时，使用指数退避策略进行重试。
    RateLimit 错误（429）使用更高的重试次数。

    Args:
        provider: LLM 提供商实例。
        messages: 消息列表。
        model: 模型标识符。
        max_retries: 普通错误最大重试次数，默认 3 次。
        max_retries_on_rate_limit: RateLimit 错误最大重试次数，默认 20 次。
        base_delay: 基础延迟时间（秒），默认 1.0 秒。
        timeout: 单次请求超时时间（秒），默认 120 秒。
        **kwargs: 其他传递给 provider.chat 的参数。

    Returns:
        LLMResponse 对象。

    Raises:
        LLMError: 当所有重试都失败时抛出。
    """

    @llm_retry(
        max_retries=max_retries,
        max_retries_on_rate_limit=max_retries_on_rate_limit,
        base_delay=base_delay,
    )
    def _call() -> LLMResponse:
        return provider.chat(
            messages=messages, model=model, timeout=timeout, **kwargs
        )

    return _call()


def estimate_tokens(text: str) -> int:
    """估算文本的 Token 数量。

    使用简单的启发式方法：英文单词约 1 Token，中文字符约 1.5 Token。

    Args:
        text: 待估算的文本。

    Returns:
        估算的 Token 数量。
    """
    if not text:
        return 0

    chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    other_chars = len(text) - chinese_chars

    chinese_tokens = int(chinese_chars * 1.5)
    other_tokens = other_chars // 4

    return chinese_tokens + max(other_tokens, 0)


def _count_text_tokens(text: str) -> int:
    """估算单段文本的 Token 数量。

    Args:
        text: 待估算的文本。

    Returns:
        估算的 Token 数量。
    """
    return estimate_tokens(text)


def _count_messages_tokens(messages: list[dict[str, str]]) -> int:
    """估算消息列表的 Token 数量（含角色开销）。

    每条消息额外计算约 4 个 Token 的角色标记开销。

    Args:
        messages: 消息列表。

    Returns:
        估算的 Token 数量。
    """
    total = 0
    for msg in messages:
        total += estimate_tokens(msg.get("content", ""))
        total += 4
    total += 2
    return total


def calculate_cost(usage: Usage, pricing: ModelPricing) -> float:
    """计算 Token 消耗成本。

    Args:
        usage: Token 使用量。
        pricing: 模型定价信息（单位：元/百万 Tokens）。

    Returns:
        成本（单位：CNY）。
    """
    prompt_cost = (usage.prompt_tokens / 1_000_000) * pricing.prompt_price
    completion_cost = (usage.completion_tokens / 1_000_000) * pricing.completion_price
    return prompt_cost + completion_cost


def format_cost(cost: float) -> str:
    """格式化成本显示。

    Args:
        cost: 成本（单位：CNY）。

    Returns:
        格式化后的成本字符串。
    """
    if cost < 0.01:
        return f"¥{cost * 1000:.3f}厘"
    elif cost < 1:
        return f"¥{cost:.4f}"
    else:
        return f"¥{cost:.2f}"


@dataclass
class _CostRecord:
    """单次 API 调用记录。

    Attributes:
        model: 模型标识符。
        prompt_tokens: 输入 Token 数。
        completion_tokens: 输出 Token 数。
        cost: 本次调用成本（CNY）。
    """

    model: str
    prompt_tokens: int
    completion_tokens: int
    cost: float


class CostTracker:
    """LLM 调用成本追踪器。

    追踪每次 API 调用的 Token 消耗和成本，支持按模型汇总。

    Attributes:
        enabled: 是否启用追踪。
        records: 调用记录列表。
    """

    def __init__(self, enabled: bool = False) -> None:
        """初始化成本追踪器。

        Args:
            enabled: 是否启用追踪。
        """
        self.enabled = enabled
        self.records: list[_CostRecord] = []

    def record(self, usage: Usage, provider: LLMProvider) -> None:
        """记录一次 API 调用。

        Args:
            usage: Token 使用量。
            provider: LLM 提供商实例，用于获取模型定价。
        """
        if not self.enabled:
            return

        model = provider.default_model
        pricing = provider.get_model_pricing(model)
        cost = calculate_cost(usage, pricing)

        self.records.append(
            _CostRecord(
                model=model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                cost=cost,
            )
        )

    def estimated_cost(self, provider: LLMProvider | None = None) -> float:
        """返回估算总成本。

        Args:
            provider: LLM 提供商实例（未使用，保留接口兼容）。

        Returns:
            总成本（单位：CNY）。
        """
        return sum(r.cost for r in self.records)

    def report(self, provider: LLMProvider | None = None) -> None:
        """打印成本报告。

        按模型汇总 Token 消耗和成本，输出到日志。

        Args:
            provider: LLM 提供商实例（未使用，保留接口兼容）。
        """
        if not self.records:
            logger.info("[CostTracker] 无调用记录")
            return

        model_stats: dict[str, dict[str, Any]] = {}
        for r in self.records:
            if r.model not in model_stats:
                model_stats[r.model] = {
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cost": 0.0,
                }
            stats = model_stats[r.model]
            stats["calls"] += 1
            stats["prompt_tokens"] += r.prompt_tokens
            stats["completion_tokens"] += r.completion_tokens
            stats["cost"] += r.cost

        total_calls = len(self.records)
        total_prompt = sum(s["prompt_tokens"] for s in model_stats.values())
        total_completion = sum(s["completion_tokens"] for s in model_stats.values())
        total_cost = self.estimated_cost()

        lines = [
            "",
            "=" * 50,
            "  LLM 成本报告",
            "=" * 50,
        ]
        for model, stats in model_stats.items():
            lines.append(
                f"  {model}: "
                f"{stats['calls']}次调用, "
                f"输入{stats['prompt_tokens']:,} tokens, "
                f"输出{stats['completion_tokens']:,} tokens, "
                f"成本 {format_cost(stats['cost'])}"
            )
        lines.append("-" * 50)
        lines.append(
            f"  合计: "
            f"{total_calls}次调用, "
            f"输入{total_prompt:,} tokens, "
            f"输出{total_completion:,} tokens, "
            f"总成本 {format_cost(total_cost)}"
        )
        lines.append("=" * 50)

        for line in lines:
            logger.info(line)


_default_provider: LLMProvider | None = None

_cost_tracker = CostTracker(enabled=False)


def get_default_provider() -> LLMProvider:
    """获取默认的 LLM 提供商实例（单例）。

    Returns:
        OpenAICompatibleProvider 实例。
    """
    global _default_provider, _cost_tracker
    if _default_provider is None:
        _default_provider = OpenAICompatibleProvider()
        _cost_tracker.enabled = _default_provider.enable_token_count
    return _default_provider


def get_cost_tracker() -> CostTracker:
    """获取全局成本追踪器实例。

    Returns:
        CostTracker 实例。
    """
    return _cost_tracker


def quick_chat(
    prompt: str,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    provider: LLMProvider | None = None,
    **kwargs: Any,
) -> LLMResponse:
    """便捷的单轮对话函数。

    一句话调用 LLM，适合简单的问答场景。

    Args:
        prompt: 用户输入的提示词。
        system_prompt: 系统提示词（可选）。
        model: 模型标识符，为 None 时使用默认模型。
        temperature: 生成温度。
        provider: LLM 提供商实例，为 None 时使用默认提供商。
        **kwargs: 其他传递给 chat_with_retry 的参数。

    Returns:
        LLMResponse 对象。

    Example:
        >>> response = quick_chat("什么是机器学习？")
        >>> print(response.content)
    """
    if provider is None:
        provider = get_default_provider()

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    return chat_with_retry(
        provider=provider,
        messages=messages,
        model=model,
        temperature=temperature,
        **kwargs,
    )


if __name__ == "__main__":
    import json

    logger.info("=" * 60)
    logger.info("LLM 客户端测试")
    logger.info("=" * 60)

    logger.info("\n1. 测试默认提供商配置")
    try:
        provider = get_default_provider()
        logger.info(f"   API Base: {provider.api_base}")
        logger.info(f"   Default Model: {provider.default_model}")
        logger.info(
            f"   API Key: {'*' * 8}{provider.api_key[-4:] if len(provider.api_key) > 4 else '****'}"
        )
    except LLMError as e:
        logger.error(f"   配置错误: {e}")
        exit(1)

    logger.info("\n2. 测试 Token 估算")
    test_texts = [
        "Hello, world!",
        "这是一段中文测试文本。",
        "Mixed content: 你好 world! 123",
    ]
    for text in test_texts:
        tokens = estimate_tokens(text)
        logger.info(f"   文本: '{text}' -> 约 {tokens} tokens")

    logger.info("\n3. 测试成本计算")
    test_usage = Usage(prompt_tokens=100, completion_tokens=50)
    test_models = ["deepseek-v4-flash", "qwen-turbo", "glm-4", "unknown-model"]
    for model_name in test_models:
        pricing = provider.get_model_pricing(model_name)
        cost = calculate_cost(test_usage, pricing)
        logger.info(
            f"   {model_name}: {format_cost(cost)} "
            f"(prompt={pricing.prompt_price}/K, completion={pricing.completion_price}/K)"
        )

    logger.info("\n4. 测试 quick_chat 函数")
    test_prompt = "请用一句话回答：1+1等于几？"
    logger.info(f"   提示词: {test_prompt}")

    try:
        response = quick_chat(test_prompt, temperature=0.3)
        logger.info(f"   响应: {response.content}")
        logger.info(f"   模型: {response.model}")
        logger.info(
            f"   用量: {json.dumps(response.usage.to_dict(), ensure_ascii=False)}"
        )

        pricing = provider.get_model_pricing(response.model)
        cost = calculate_cost(response.usage, pricing)
        logger.info(f"   成本: {format_cost(cost)}")
    except LLMError as e:
        logger.error(f"   调用失败: {e}")

    logger.info("\n5. 测试带重试的调用")
    messages = [
        {"role": "system", "content": "你是一个有帮助的助手。"},
        {"role": "user", "content": "请列出三种编程语言的名称。"},
    ]
    try:
        response = chat_with_retry(provider, messages, max_retries=2)
        logger.info(f"   响应: {response.content[:100]}...")
        logger.info(
            f"   用量: {json.dumps(response.usage.to_dict(), ensure_ascii=False)}"
        )
    except LLMError as e:
        logger.error(f"   调用失败: {e}")

    logger.info("\n" + "=" * 60)
    logger.info("测试完成")
    logger.info("=" * 60)

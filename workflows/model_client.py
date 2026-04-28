"""LLM 客户端封装模块。

提供统一的 LLM 调用接口，支持普通对话和 JSON 结构化输出。
"""

import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def chat(
    prompt: str,
    system: str = "",
    response_format: Optional[dict] = None,
) -> tuple[str, dict]:
    """调用 LLM 进行对话。

    Args:
        prompt: 用户输入的提示文本。
        system: 系统提示文本，用于设定 AI 角色和行为。
        response_format: 响应格式配置。例如 {"type": "json_object"} 启用 JSON 模式。

    Returns:
        tuple[str, dict]: 返回 (LLM 响应文本, token 用量统计)。
            用量统计包含 total_tokens, input_tokens, output_tokens 字段。

    Raises:
        RuntimeError: API 调用失败时抛出。
    """
    api_base = os.getenv("LLM_API_BASE", "https://api.scnet.cn/api/llm/v1")
    api_key = os.getenv("LLM_API_KEY", "")
    model_id = os.getenv("LLM_MODEL_ID", "MiniMax-M2.5")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload_dict: dict[str, Any] = {"model": model_id, "messages": messages}

    if response_format:
        payload_dict["response_format"] = response_format

    payload = json.dumps(payload_dict).encode("utf-8")

    req = urllib.request.Request(
        f"{api_base}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"]
            usage = {
                "total_tokens": result.get("usage", {}).get("total_tokens", 0),
                "input_tokens": result.get("usage", {}).get("prompt_tokens", 0),
                "output_tokens": result.get("usage", {}).get("completion_tokens", 0),
            }
            return content, usage
    except Exception as e:
        raise RuntimeError(f"LLM API 调用失败: {e}") from e


def chat_json(
    prompt: str,
    system: str = "",
    use_json_mode: bool = True,
) -> tuple[dict[str, Any], dict]:
    """调用 LLM 并返回 JSON 结构化结果。

    Args:
        prompt: 用户输入的提示文本，应明确要求输出 JSON 格式。
        system: 系统提示文本，建议包含 JSON 格式说明。
        use_json_mode: 是否使用 JSON 模式（强制模型输出 JSON）。默认 True。

    Returns:
        tuple[dict[str, Any], dict]: 返回 (解析后的 JSON 对象, token 用量统计)。

    Raises:
        RuntimeError: API 调用失败或 JSON 解析失败时抛出。
    """
    if use_json_mode:
        response_format = {"type": "json_object"}
        enhanced_prompt = prompt
    else:
        response_format = None
        enhanced_prompt = f"{prompt}\n\n请以 JSON 格式输出，不要包含任何其他文本。"

    text, usage = chat(enhanced_prompt, system, response_format=response_format)

    try:
        json_str = text.strip()
        if not use_json_mode:
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()

        return json.loads(json_str), usage
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON 解析失败，原始响应: {text}") from e


def accumulate_usage(tracker: dict, usage: dict) -> None:
    """累加 token 用量到追踪器。

    Args:
        tracker: 用量追踪字典，会被原地修改。
        usage: 本次 API 调用的用量统计。
    """
    tracker["total_tokens"] = tracker.get("total_tokens", 0) + usage.get("total_tokens", 0)
    tracker["input_tokens"] = tracker.get("input_tokens", 0) + usage.get("input_tokens", 0)
    tracker["output_tokens"] = tracker.get("output_tokens", 0) + usage.get("output_tokens", 0)
    tracker["call_count"] = tracker.get("call_count", 0) + 1

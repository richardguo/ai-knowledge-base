"""LLM 客户端封装模块。

提供统一的 LLM 调用接口，支持普通对话、JSON 结构化输出和流式输出。
"""

import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any, Generator, Optional

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def chat(
    prompt: str,
    system: str = "",
    response_format: Optional[dict] = None,
    temperature: float = 0.7,
) -> tuple[str, dict]:
    """调用 LLM 进行对话。

    Args:
        prompt: 用户输入的提示文本。
        system: 系统提示文本，用于设定 AI 角色和行为。
        response_format: 响应格式配置。例如 {"type": "json_object"} 启用 JSON 模式。
        temperature: 生成温度，控制输出随机性。默认 0.7。

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

    payload_dict: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
    }

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


def chat_stream(
    prompt: str,
    system: str = "",
    response_format: Optional[dict] = None,
    temperature: float = 0.7,
) -> Generator[str, None, None]:
    """流式调用 LLM，逐步 yield 文本片段。

    通过 SSE 协议接收模型输出，每收到一个 chunk 即 yield 其文本内容。
    流结束后 yield 一个 JSON 字符串 "|||USAGE|||" + json.dumps(usage)，
    调用方可据此提取 token 用量。

    Args:
        prompt: 用户输入的提示文本。
        system: 系统提示文本。
        response_format: 响应格式配置，例如 {"type": "json_object"}。
        temperature: 生成温度，控制输出随机性。默认 0.7。

    Yields:
        str: 模型输出的文本片段。最后一个 yield 为 "|||USAGE|||" + usage_json。

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

    payload_dict: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
    }
    if response_format:
        payload_dict["response_format"] = response_format

    url = f"{api_base.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        with httpx.stream(
            "POST",
            url,
            json=payload_dict,
            headers=headers,
            timeout=120.0,
        ) as response:
            if response.status_code != 200:
                raise RuntimeError(
                    f"LLM API 调用失败 (status={response.status_code}): {response.text}"
                )

            usage: dict[str, int] = {
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            }

            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield content

                chunk_usage = chunk.get("usage")
                if chunk_usage:
                    usage["total_tokens"] = chunk_usage.get("total_tokens", 0)
                    usage["input_tokens"] = chunk_usage.get("prompt_tokens", 0)
                    usage["output_tokens"] = chunk_usage.get("completion_tokens", 0)

            yield f"|||USAGE|||{json.dumps(usage)}"

    except httpx.TimeoutException as e:
        raise RuntimeError(f"LLM 流式请求超时: {e}") from e
    except httpx.RequestError as e:
        raise RuntimeError(f"LLM 流式请求错误: {e}") from e


def chat_json_stream(
    prompt: str,
    system: str = "",
    use_json_mode: bool = True,
    temperature: float = 0.7,
) -> tuple[dict[str, Any], dict]:
    """流式调用 LLM 并返回 JSON 结构化结果。

    逐 chunk 接收并打印流式输出，最终拼合完整文本后解析为 JSON。
    接口签名与 chat_json 完全一致，可无缝替换。

    Args:
        prompt: 用户输入的提示文本。
        system: 系统提示文本。
        use_json_mode: 是否使用 JSON 模式。默认 True。
        temperature: 生成温度，控制输出随机性。默认 0.7。

    Returns:
        tuple[dict[str, Any], dict]: 返回 (解析后的 JSON 对象, token 用量统计)。

    Raises:
        RuntimeError: API 调用失败或 JSON 解析失败时抛出。
    """
    if use_json_mode:
        fmt = {"type": "json_object"}
        enhanced_prompt = prompt
    else:
        fmt = None
        enhanced_prompt = f"{prompt}\n\n请以 JSON 格式输出，不要包含任何其他文本。"

    full_text_parts: list[str] = []
    usage: dict = {}

    for chunk in chat_stream(enhanced_prompt, system, response_format=fmt, temperature=temperature):
        if chunk.startswith("|||USAGE|||"):
            usage = json.loads(chunk[len("|||USAGE|||") :])
        else:
            print(chunk, end="", flush=True)
            full_text_parts.append(chunk)

    print()

    text = "".join(full_text_parts).strip()
    if not use_json_mode:
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text), usage
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON 解析失败，原始响应: {text}") from e


def chat_json(
    prompt: str,
    system: str = "",
    use_json_mode: bool = True,
    temperature: float = 0.7,
) -> tuple[dict[str, Any], dict]:
    """调用 LLM 并返回 JSON 结构化结果。

    Args:
        prompt: 用户输入的提示文本，应明确要求输出 JSON 格式。
        system: 系统提示文本，建议包含 JSON 格式说明。
        use_json_mode: 是否使用 JSON 模式（强制模型输出 JSON）。默认 True。
        temperature: 生成温度，控制输出随机性。默认 0.7。

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

    text, usage = chat(enhanced_prompt, system, response_format=response_format, temperature=temperature)

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

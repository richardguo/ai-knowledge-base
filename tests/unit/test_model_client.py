"""LLM 客户端单元测试（真实调用 API）。"""

import json
import os

import pytest

from workflows.model_client import accumulate_usage, chat, chat_json


class TestChat:
    """chat() 函数测试。"""

    @pytest.mark.skipif(
        not os.getenv("LLM_API_KEY"),
        reason="LLM_API_KEY 未配置"
    )
    def test_chat_basic_call(self):
        """测试基本对话功能。"""
        prompt = "请用一句话回答：1+1等于几？"
        response, usage = chat(prompt)

        assert isinstance(response, str)
        assert len(response) > 0
        assert "2" in response or "二" in response

        assert isinstance(usage, dict)
        assert "total_tokens" in usage
        assert usage["total_tokens"] > 0

    @pytest.mark.skipif(
        not os.getenv("LLM_API_KEY"),
        reason="LLM_API_KEY 未配置"
    )
    def test_chat_with_system_prompt(self):
        """测试带系统提示的对话。"""
        system = "你是一个专业的技术助手，回答要简洁准确。"
        prompt = "Python 的列表推导式有什么优点？"

        response, usage = chat(prompt, system=system)

        assert isinstance(response, str)
        assert len(response) > 0
        assert usage["total_tokens"] > 0

    @pytest.mark.skipif(
        not os.getenv("LLM_API_KEY"),
        reason="LLM_API_KEY 未配置"
    )
    def test_chat_chinese_response(self):
        """测试中文对话。"""
        prompt = "请用中文简要描述 LangGraph 的主要用途。"
        response, usage = chat(prompt)

        assert isinstance(response, str)
        assert len(response) > 10
        assert usage["input_tokens"] > 0
        assert usage["output_tokens"] > 0


    @pytest.mark.skipif(
        not os.getenv("LLM_API_KEY"),
        reason="LLM_API_KEY 未配置"
    )
    def test_chat_with_response_format(self):
        """测试 response_format 参数。"""
        prompt = "生成一个包含 name 字段的 JSON 对象。"
        response, usage = chat(
            prompt,
            response_format={"type": "json_object"}
        )

        assert isinstance(response, str)
        # JSON 模式下，响应应该是有效的 JSON
        result = json.loads(response)
        assert isinstance(result, dict)


class TestChatJson:
    """chat_json() 函数测试。"""

    @pytest.mark.skipif(
        not os.getenv("LLM_API_KEY"),
        reason="LLM_API_KEY 未配置"
    )
    def test_chat_json_simple_object(self):
        """测试返回简单 JSON 对象。"""
        prompt = "生成一个包含 name 和 age 字段的 JSON 对象，name 为 '张三'，age 为 25。"
        result, usage = chat_json(prompt)

        assert isinstance(result, dict)
        assert "name" in result
        assert "age" in result
        assert result["name"] == "张三"
        assert result["age"] == 25

    @pytest.mark.skipif(
        not os.getenv("LLM_API_KEY"),
        reason="LLM_API_KEY 未配置"
    )
    def test_chat_json_with_json_mode(self):
        """测试 JSON 模式（强制输出 JSON）。"""
        prompt = "生成一个包含 status 字段的 JSON 对象，status 为 'success'。"
        result, usage = chat_json(prompt, use_json_mode=True)

        assert isinstance(result, dict)
        assert result["status"] == "success"

    @pytest.mark.skipif(
        not os.getenv("LLM_API_KEY"),
        reason="LLM_API_KEY 未配置"
    )
    def test_chat_json_without_json_mode(self):
        """测试不使用 JSON 模式（传统方式）。"""
        prompt = "生成一个包含 count 字段的 JSON 对象，count 为 42。"
        result, usage = chat_json(prompt, use_json_mode=False)

        assert isinstance(result, dict)
        assert result["count"] == 42

    @pytest.mark.skipif(
        not os.getenv("LLM_API_KEY"),
        reason="LLM_API_KEY 未配置"
    )
    def test_chat_json_nested_structure(self):
        """测试返回嵌套 JSON 结构。"""
        prompt = """生成一个 JSON 对象，包含以下字段：
- project: 项目名称
- tags: 标签数组（3 个标签）
- metadata: 元数据对象（包含 created_at 和 updated_at）

项目名称为 'AI知识库'，请输出 JSON。"""

        result, usage = chat_json(prompt)

        assert isinstance(result, dict)
        assert "project" in result
        assert "tags" in result
        assert "metadata" in result
        assert isinstance(result["tags"], list)
        assert len(result["tags"]) >= 2
        assert isinstance(result["metadata"], dict)

    @pytest.mark.skipif(
        not os.getenv("LLM_API_KEY"),
        reason="LLM_API_KEY 未配置"
    )
    def test_chat_json_analysis_format(self):
        """测试分析格式的 JSON 输出（与实际工作流相同）。"""
        system = """你是一个技术分析专家，负责分析 GitHub 项目并生成结构化摘要。
输出要求（JSON 格式）：
- summary: 50-100 字中文摘要
- tags: 3-5 个英文标签
- relevance_score: 相关度评分（0.0-1.0）
- category: 分类（agent-framework, llm-tool, python-library, other）"""

        prompt = """项目名称: langchain-ai/langchain
描述: Building applications with LLMs through composability
语言: Python
星标数: 90000

请分析该项目并输出 JSON 格式的结构化摘要。"""

        result, usage = chat_json(prompt, system=system)

        assert isinstance(result, dict)
        assert "summary" in result
        assert "tags" in result
        assert "relevance_score" in result
        assert "category" in result

        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 10
        assert isinstance(result["tags"], list)
        assert 0.0 <= result["relevance_score"] <= 1.0
        assert result["category"] in ["agent-framework", "llm-tool", "python-library", "other"]

    @pytest.mark.skipif(
        not os.getenv("LLM_API_KEY"),
        reason="LLM_API_KEY 未配置"
    )
    def test_chat_json_handles_code_block(self):
        """测试处理 markdown 代码块包裹的 JSON。"""
        prompt = "请返回一个包含 status 字段的 JSON，status 为 'success'。可以用 ```json 代码块包裹。"
        result, usage = chat_json(prompt)

        assert isinstance(result, dict)
        assert "status" in result


class TestAccumulateUsage:
    """accumulate_usage() 函数测试。"""

    def test_accumulate_usage_basic(self):
        """测试基本累加功能。"""
        tracker = {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0}
        usage = {"total_tokens": 100, "input_tokens": 80, "output_tokens": 20}

        accumulate_usage(tracker, usage)

        assert tracker["total_tokens"] == 100
        assert tracker["input_tokens"] == 80
        assert tracker["output_tokens"] == 20

    def test_accumulate_usage_multiple_calls(self):
        """测试多次累加。"""
        tracker = {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0}

        accumulate_usage(tracker, {"total_tokens": 100, "input_tokens": 80, "output_tokens": 20})
        accumulate_usage(tracker, {"total_tokens": 50, "input_tokens": 40, "output_tokens": 10})

        assert tracker["total_tokens"] == 150
        assert tracker["input_tokens"] == 120
        assert tracker["output_tokens"] == 30
        assert tracker["call_count"] == 2

    def test_accumulate_usage_partial_fields(self):
        """测试部分字段缺失的情况。"""
        tracker = {"total_tokens": 100}
        usage = {"total_tokens": 50, "input_tokens": 30}

        accumulate_usage(tracker, usage)

        assert tracker["total_tokens"] == 150
        assert tracker["input_tokens"] == 30

    def test_accumulate_usage_empty_usage(self):
        """测试空用量统计。"""
        tracker = {"total_tokens": 100}
        usage = {}

        accumulate_usage(tracker, usage)

        assert tracker["total_tokens"] == 100

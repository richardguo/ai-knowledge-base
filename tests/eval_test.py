"""AI 知识库评估测试。

使用 LLM 对知识库分析流水线进行质量评估，包含正面/负面/边界场景。
"""

from __future__ import annotations

import pytest

from workflows.model_client import chat_json


_CASE_IDS = ["positive-tech-article", "negative-irrelevant", "boundary-minimal-input"]

EVAL_CASES: list[dict] = [
    {
        "name": "正面案例-技术文章",
        "input": {
            "title": "LangGraph: Building Stateful AI Agents",
            "description": "LangGraph is a library for building stateful, multi-actor applications with LLMs. It extends LangChain with graph-based workflow orchestration, supporting cycles, persistence, and human-in-the-loop patterns.",
            "topics": ["llm", "agent", "workflow"],
        },
        "expected": {
            "has_summary": True,
            "has_tags": True,
            "min_relevance": 7,
            "category_in": ["agent-framework", "llm-tool", "developer-tool"],
        },
    },
    {
        "name": "负面案例-无关内容",
        "input": {
            "title": "Best Pasta Recipes 2025",
            "description": "A collection of Italian pasta recipes including carbonara, bolognese, and cacio e pepe. Step-by-step cooking instructions for beginners.",
            "topics": ["cooking", "recipes", "food"],
        },
        "expected": {
            "has_summary": True,
            "has_tags": True,
            "max_relevance": 5,
            "category_in": ["irrelevant", "non-tech"],
        },
    },
    {
        "name": "边界案例-极短输入",
        "input": {
            "title": "AI",
            "description": "AI",
            "topics": [],
        },
        "expected": {
            "has_summary": True,
            "has_tags": True,
            "no_crash": True,
        },
    },
]


def _analyze_with_llm(input_data: dict) -> dict:
    """调用 LLM 对输入数据生成分析结果。

    Args:
        input_data: 包含 title/description/topics 的输入字典。

    Returns:
        LLM 返回的分析结果字典。
    """
    system_prompt = (
        "你是一个 AI 技术情报分析助手。根据输入的项目信息，生成结构化分析结果。\n"
        '输出 JSON 格式：{"summary": str, "tags": list[str], "relevance_score": int(1-10), "category": str}\n'
        "- summary: 中文摘要（1-3 句）\n"
        "- tags: 英文小写标签列表\n"
        "- relevance_score: 与 AI/LLM/Agent 领域的相关度评分\n"
        "- category: 分类（agent-framework / llm-tool / developer-tool / irrelevant / non-tech）"
    )
    import json

    prompt = json.dumps(input_data, ensure_ascii=False)
    result, _usage = chat_json(prompt, system=system_prompt)
    return result


@pytest.fixture(params=EVAL_CASES, ids=_CASE_IDS)
def eval_case(request):
    return request.param


class TestEvalCasesStructure:
    """本地验证测试，不调用 LLM。"""

    def test_cases_count(self):
        assert len(EVAL_CASES) >= 3

    def test_each_case_has_required_fields(self):
        for case in EVAL_CASES:
            assert "name" in case, f"缺少 name 字段: {case}"
            assert "input" in case, f"缺少 input 字段: {case['name']}"
            assert "expected" in case, f"缺少 expected 字段: {case['name']}"

    def test_each_input_has_core_fields(self):
        for case in EVAL_CASES:
            inp = case["input"]
            assert "title" in inp, f"input 缺少 title: {case['name']}"
            assert "description" in inp, f"input 缺少 description: {case['name']}"

    def test_expected_has_valid_checks(self):
        for case in EVAL_CASES:
            exp = case["expected"]
            assert any(
                k in exp for k in ("has_summary", "min_relevance", "max_relevance", "no_crash")
            ), f"expected 无有效检查项: {case['name']}"


class TestEvalWithLLM:
    """LLM 驱动的评估测试。"""

    def test_analysis_output_structure(self, eval_case):
        result = _analyze_with_llm(eval_case["input"])
        assert isinstance(result, dict)
        assert "summary" in result
        assert "tags" in result
        assert "relevance_score" in result
        assert "category" in result

    def test_summary_present_when_expected(self, eval_case):
        exp = eval_case["expected"]
        if not exp.get("has_summary"):
            pytest.skip("该用例不检查摘要")
        result = _analyze_with_llm(eval_case["input"])
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) >= 1

    def test_tags_present_when_expected(self, eval_case):
        exp = eval_case["expected"]
        if not exp.get("has_tags"):
            pytest.skip("该用例不检查标签")
        result = _analyze_with_llm(eval_case["input"])
        assert isinstance(result["tags"], list)
        assert len(result["tags"]) >= 1

    def test_relevance_score_range(self, eval_case):
        exp = eval_case["expected"]
        result = _analyze_with_llm(eval_case["input"])
        score = result["relevance_score"]
        assert isinstance(score, (int, float))
        if "min_relevance" in exp:
            assert score >= exp["min_relevance"], (
                f"{eval_case['name']}: 相关度 {score} < 最低要求 {exp['min_relevance']}"
            )
        if "max_relevance" in exp:
            assert score <= exp["max_relevance"], (
                f"{eval_case['name']}: 相关度 {score} > 最高阈值 {exp['max_relevance']}"
            )

    def test_category_in_expected_set(self, eval_case):
        exp = eval_case["expected"]
        if "category_in" not in exp:
            pytest.skip("该用例不检查分类")
        result = _analyze_with_llm(eval_case["input"])
        assert result["category"] in exp["category_in"], (
            f"{eval_case['name']}: 分类 '{result['category']}' 不在 {exp['category_in']}"
        )

    def test_no_crash_on_boundary_input(self, eval_case):
        exp = eval_case["expected"]
        if not exp.get("no_crash"):
            pytest.skip("非边界案例")
        result = _analyze_with_llm(eval_case["input"])
        assert isinstance(result, dict)
        assert "summary" in result


@pytest.mark.slow
class TestLLMAsJudge:
    """LLM-as-Judge 评估：让 LLM 对分析结果打分。"""

    def test_judge_analysis_quality(self):
        case = EVAL_CASES[0]
        analysis = _analyze_with_llm(case["input"])

        judge_prompt = (
            "你是一个 AI 系统质量评估专家。请对以下分析结果进行打分（1-10 分）。\n"
            "评估标准：摘要准确性、标签相关性、评分合理性。\n\n"
            f"原始输入：{case['input']}\n\n"
            f"分析结果：{analysis}\n\n"
            '请以 JSON 格式输出：{"score": int, "reason": str}'
        )
        judge_result, _usage = chat_json(
            judge_prompt,
            system="你是一个严格的 QA 评审员，只输出 JSON。",
            temperature=0.3,
        )

        score = judge_result["score"]
        assert isinstance(score, (int, float))
        assert score >= 5, f"LLM-as-Judge 评分 {score} < 5，原因：{judge_result.get('reason', '')}"

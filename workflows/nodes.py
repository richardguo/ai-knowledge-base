"""LangGraph 工作流节点定义。

每个节点是纯函数：接收 KBState，返回 dict（部分状态更新）。
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workflows.model_client import accumulate_usage, chat_json
from workflows.state import KBState


def collect_node(state: KBState) -> dict[str, Any]:
    """采集节点：调用 GitHub Search API 获取 AI 相关仓库。

    Args:
        state: 当前工作流状态。

    Returns:
        dict: 包含 sources 和更新后的 cost_tracker。
    """
    print("[CollectNode] 开始采集 GitHub 数据")

    api_key = os.getenv("GITHUB_TOKEN", "")
    if not api_key:
        raise RuntimeError("GITHUB_TOKEN 未配置")

    query = "AI OR LLM OR agent language:Python sort:stars"
    url = f"https://api.github.com/search/repositories?q={quote(query)}&per_page=30"

    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "AI-Knowledge-Base",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"GitHub API 调用失败: {e}") from e

    sources = []
    for item in data.get("items", []):
        sources.append(
            {
                "title": item.get("full_name", ""),
                "url": item.get("html_url", ""),
                "description": item.get("description", ""),
                "readme": "",
                "popularity": {
                    "stars": item.get("stargazers_count", 0),
                    "forks": item.get("forks_count", 0),
                },
                "author": item.get("owner", {}).get("login", ""),
                "created_at": item.get("created_at", ""),
                "updated_at": item.get("updated_at", ""),
                "language": item.get("language", ""),
                "topics": item.get("topics", []),
            }
        )

    print(f"[CollectNode] 采集完成，共 {len(sources)} 条数据")

    cost_tracker = state.get("cost_tracker", {})
    return {"sources": sources, "cost_tracker": cost_tracker}


BATCH_SIZE = 10


def _build_batch_prompt(sources: list[dict]) -> str:
    """为一批 source 构建批量分析 prompt。

    Args:
        sources: 当前批次的 source 列表。

    Returns:
        str: 批量分析 prompt。
    """
    items_lines = []
    for idx, source in enumerate(sources):
        items_lines.append(
            f"[{idx}] 项目名称: {source.get('title', '')}\n"
            f"    描述: {source.get('description', '无')}\n"
            f"    语言: {source.get('language', '未知')}\n"
            f"    星标数: {source.get('popularity', {}).get('stars', 0)}\n"
            f"    话题: {', '.join(source.get('topics', []))}"
        )
    return (
        f"以下共有 {len(sources)} 个 GitHub 项目需要分析：\n\n"
        f"{chr(10).join(items_lines)}\n\n"
        f"请逐一分析每个项目，输出 JSON 数组格式的结构化摘要。"
        f"数组长度必须与输入项目数一致。"
    )


def _extract_analyses(result: Any, sources: list[dict]) -> list[dict]:
    """从 LLM 批量返回结果中提取分析列表，并附加溯源字段。

    Args:
        result: chat_json 返回的解析结果（list 或 dict）。
        sources: 对应的 source 列表，用于填充 url / collected_at。

    Returns:
        list[dict]: 分析结果列表。
    """
    if isinstance(result, list):
        analyses = result
    elif isinstance(result, dict):
        analyses = result.get("results", result.get("analyses", [result]))
    else:
        analyses = []

    for i, analysis in enumerate(analyses):
        if i < len(sources) and isinstance(analysis, dict):
            analysis["url"] = sources[i].get("url", "")
            analysis["collected_at"] = sources[i].get("created_at", "")
    return analyses


def analyze_node(state: KBState) -> dict[str, Any]:
    """分析节点：用 LLM 批量分析数据，生成中文摘要、标签、评分。

    以 BATCH_SIZE 为单位分批调用 LLM，每批一次性发送多条数据，
    要求模型返回 JSON 数组，减少 API 调用次数。

    Args:
        state: 当前工作流状态。

    Returns:
        dict: 包含 analyses 和更新后的 cost_tracker。
    """
    print("[AnalyzeNode] 开始批量分析数据")

    sources = state.get("sources", [])
    cost_tracker = state.get("cost_tracker", {})
    analyses: list[dict] = []

    if not sources:
        print("[AnalyzeNode] 无数据需要分析")
        return {"analyses": [], "cost_tracker": cost_tracker}

    system_prompt = """你是一个技术分析专家，负责批量分析 GitHub 项目并生成结构化摘要。

输出要求（JSON 数组格式）：
返回一个 JSON 数组，每个元素对应一个输入项目，包含：
- summary: 50-100 字中文摘要，说明项目核心功能和价值
- tags: 3-5 个英文标签（小写，用连字符分隔）
- relevance_score: 相关度评分（0.0-1.0），基于 AI/LLM/Agent 相关性
- category: 分类（agent-framework, llm-tool, python-library, other）
- highlights: 2-3 个核心亮点（中文列表）

必须返回 JSON 数组，例如：[{"summary": "...", "tags": [...], ...}]"""

    total = len(sources)
    for batch_start in range(0, total, BATCH_SIZE):
        batch = sources[batch_start : batch_start + BATCH_SIZE]
        batch_end = min(batch_start + BATCH_SIZE, total)
        print(f"[AnalyzeNode] 批量分析第 {batch_start + 1}-{batch_end}/{total} 条")

        prompt = _build_batch_prompt(batch)

        try:
            result, usage = chat_json(prompt, system_prompt)
            accumulate_usage(cost_tracker, usage)
            batch_analyses = _extract_analyses(result, batch)
            analyses.extend(batch_analyses)
        except Exception as e:
            print(f"[AnalyzeNode] 批量分析失败: {e}")
            for source in batch:
                analyses.append(
                    {
                        "url": source.get("url", ""),
                        "summary": source.get("description", "")[:100],
                        "tags": [],
                        "relevance_score": 0.5,
                        "category": "other",
                        "highlights": [],
                    }
                )

    print(f"[AnalyzeNode] 分析完成，共 {len(analyses)} 条结果")
    return {"analyses": analyses, "cost_tracker": cost_tracker}


def organize_node(state: KBState) -> dict[str, Any]:
    """整理节点：过滤、去重、根据审核反馈修正。

    Args:
        state: 当前工作流状态。

    Returns:
        dict: 包含 articles 和更新后的 cost_tracker。
    """
    print("[OrganizeNode] 开始整理数据")

    analyses = state.get("analyses", [])
    cost_tracker = state.get("cost_tracker", {})
    review_feedback = state.get("review_feedback", "")
    iteration = state.get("iteration", 0)

    filtered = [a for a in analyses if a.get("relevance_score", 0) >= 0.6]
    print(f"[OrganizeNode] 过滤后剩余 {len(filtered)}/{len(analyses)} 条")

    seen_urls = set()
    articles = []
    for analysis in filtered:
        url = analysis.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            articles.append(
                {
                    "id": url.split("/")[-1] if url else "",
                    "title": analysis.get("title", ""),
                    "url": url,
                    "source": "github",
                    "collected_at": analysis.get("collected_at", ""),
                    "processed_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
                    "summary": analysis.get("summary", ""),
                    "highlights": analysis.get("highlights", []),
                    "relevance_score": analysis.get("relevance_score", 0),
                    "tags": analysis.get("tags", []),
                    "category": analysis.get("category", "other"),
                }
            )

    if iteration > 0 and review_feedback:
        print(f"[OrganizeNode] 根据审核反馈修正（第 {iteration} 轮）")
        system_prompt = """你是一个技术编辑，负责根据审核意见改进知识条目。
输出要求：返回修正后的 articles JSON 数组。"""

        prompt = f"""原始条目:
{json.dumps(articles, ensure_ascii=False, indent=2)}

审核反馈:
{review_feedback}

请根据反馈修正上述条目，保持 JSON 格式输出。"""

        try:
            corrected, usage = chat_json(prompt, system_prompt)
            accumulate_usage(cost_tracker, usage)
            if isinstance(corrected, list):
                articles = corrected
        except Exception as e:
            print(f"[OrganizeNode] 修正失败: {e}")

    print(f"[OrganizeNode] 整理完成，共 {len(articles)} 条知识条目")
    return {"articles": articles, "cost_tracker": cost_tracker}


def review_node(state: KBState) -> dict[str, Any]:
    """审核节点：LLM 四维度评分，iteration >= 2 强制通过。

    Args:
        state: 当前工作流状态。

    Returns:
        dict: 包含 review_passed, review_feedback, iteration, cost_tracker。
    """
    print("[ReviewNode] 开始审核")

    iteration = state.get("iteration", 0)
    articles = state.get("articles", [])
    cost_tracker = state.get("cost_tracker", {})

    if iteration >= 2:
        print("[ReviewNode] 已达到最大迭代次数，强制通过")
        return {
            "review_passed": True,
            "review_feedback": "",
            "iteration": iteration + 1,
            "cost_tracker": cost_tracker,
        }

    if not articles:
        return {
            "review_passed": False,
            "review_feedback": "无有效条目需要审核",
            "iteration": iteration + 1,
            "cost_tracker": cost_tracker,
        }

    system_prompt = """你是一个质量控制专家，负责审核知识条目质量。

评分维度（每项 0-10 分）：
1. 摘要质量：信息量、准确性、语言流畅度
2. 标签准确：相关性、覆盖度、规范性
3. 分类合理：类别选择是否恰当
4. 一致性：字段间逻辑是否自洽

输出 JSON 格式：
{
  "passed": true/false,
  "overall_score": 0.0-10.0,
  "feedback": "具体改进建议（如果未通过）",
  "scores": {
    "summary_quality": 0-10,
    "tag_accuracy": 0-10,
    "category_fit": 0-10,
    "consistency": 0-10
  }
}

判定标准：overall_score >= 7.0 且各维度 >= 5.0 则通过。"""

    prompt = f"""待审核条目:
{json.dumps(articles[:5], ensure_ascii=False, indent=2)}

请对上述条目进行质量审核，输出 JSON 格式的审核结果。"""

    try:
        result, usage = chat_json(prompt, system_prompt)
        accumulate_usage(cost_tracker, usage)

        passed = result.get("passed", False)
        overall_score = result.get("overall_score", 0)
        feedback = result.get("feedback", "")
        scores = result.get("scores", {})

        print(f"[ReviewNode] 总分: {overall_score}, 通过: {passed}")
        print(f"[ReviewNode] 维度得分: {scores}")

        return {
            "review_passed": passed,
            "review_feedback": feedback if not passed else "",
            "iteration": iteration + 1,
            "cost_tracker": cost_tracker,
        }
    except Exception as e:
        print(f"[ReviewNode] 审核失败: {e}")
        return {
            "review_passed": True,
            "review_feedback": "",
            "iteration": iteration + 1,
            "cost_tracker": cost_tracker,
        }


def review_node_test(state: KBState) -> dict[str, Any]:
    """审核节点：临时 Mock 版本，用于测试审核循环。

    前 2 次返回 review_passed=False，第 3 次（iteration >= 2）返回 True。
    验证完成后需替换回 review_node。

    Args:
        state: 当前工作流状态。

    Returns:
        dict: 包含 review_passed, review_feedback, iteration, cost_tracker。
    """
    print("[ReviewNode] 开始审核 (Mock)")

    iteration = state.get("iteration", 0)
    cost_tracker = state.get("cost_tracker", {})

    mock_feedbacks = [
        "摘要过于简略，缺少项目核心价值说明；标签数量不足，建议补充 3-5 个相关标签",
        "分类不够准确，部分条目应归入 agent-framework 而非 other；highlights 缺少具体数据支撑",
    ]

    if iteration >= 2:
        print(f"[ReviewNode] iteration={iteration}, review_passed=True")
        return {
            "review_passed": True,
            "review_feedback": "",
            "iteration": iteration + 1,
            "cost_tracker": cost_tracker,
        }

    feedback = mock_feedbacks[iteration] if iteration < len(mock_feedbacks) else "需要进一步改进"
    print(f"[ReviewNode] iteration={iteration}, review_passed=False")
    print(f"[ReviewNode] feedback: {feedback}")

    return {
        "review_passed": False,
        "review_feedback": feedback,
        "iteration": iteration + 1,
        "cost_tracker": cost_tracker,
    }


def save_node(state: KBState) -> dict[str, Any]:
    """保存节点：将 articles 写入知识库文件。

    Args:
        state: 当前工作流状态。

    Returns:
        dict: 包含 cost_tracker。
    """
    print("[SaveNode] 开始保存知识条目")

    articles = state.get("articles", [])
    cost_tracker = state.get("cost_tracker", {})

    articles_dir = "knowledge/articles"
    os.makedirs(articles_dir, exist_ok=True)

    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    saved_count = 0

    for article in articles:
        slug = article.get("id", article.get("title", "unknown").replace("/", "-"))
        filename = f"{today}-{slug}.json"
        filepath = os.path.join(articles_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(article, f, ensure_ascii=False, indent=2)
        saved_count += 1

    index_path = os.path.join(articles_dir, "index.json")
    index_data = {"articles": articles, "updated_at": datetime.now(timezone(timedelta(hours=8))).isoformat()}

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f"[SaveNode] 保存完成，共 {saved_count} 条条目")

    return {"cost_tracker": cost_tracker}

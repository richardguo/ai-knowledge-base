"""Supervisor 监督模式实现。

Worker-Supervisor 协作模式：
1. Worker Agent：接收任务，输出 JSON 格式的分析报告
2. Supervisor Agent：对 Worker 的输出进行质量审核
3. 审核循环：通过则返回，不通过则带反馈重做（最多 3 轮）

评分维度：
- 准确性(accuracy): 1-10
- 深度(depth): 1-10
- 格式(format): 1-10
- 综合评分 = (accuracy + depth + format) / 3
"""

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from pipeline.model_client import quick_chat

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WORKER_SYSTEM_PROMPT = """你是一个专业的分析助手。根据用户任务，输出 JSON 格式的分析报告。

输出格式（必须严格遵循）：
{
    "summary": "任务摘要（一句话）",
    "analysis": "详细分析内容",
    "conclusion": "结论或建议",
    "confidence": 0.8
}

注意：
- analysis 字段应包含充分的细节和推理过程
- confidence 为 0-1 之间的数值，表示对分析结果的置信度
"""

SUPERVISOR_SYSTEM_PROMPT = """你是一个质量审核员。评估 Worker 输出的分析报告质量。

评分维度（每项 1-10 分）：
- accuracy: 准确性，内容是否正确、有无明显错误
- depth: 深度，分析是否充分、有无遗漏关键点
- format: 格式，JSON 结构是否正确、字段是否完整

输出格式（必须严格遵循）：
{
    "accuracy": 8,
    "depth": 7,
    "format": 9,
    "passed": true,
    "feedback": "简要说明评分理由和改进建议"
}

passed 为 true 当且仅当综合评分 >= 7。
feedback 应具体指出问题和改进方向。
"""


def extract_json(content: str) -> dict[str, Any]:
    """从文本中提取 JSON 对象。

    Args:
        content: 可能包含 JSON 的文本。

    Returns:
        解析后的 JSON 字典。

    Raises:
        ValueError: 当无法解析 JSON 时抛出。
    """
    content = content.strip()
    json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
    else:
        json_str = content

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"无法解析 JSON: {e}\n原始内容: {content[:200]}") from e


def worker_execute(task: str, feedback: str | None = None) -> dict[str, Any]:
    """Worker 执行任务并返回分析报告。

    Args:
        task: 用户任务描述。
        feedback: Supervisor 的反馈（重做时提供）。

    Returns:
        分析报告（JSON 格式）。
    """
    prompt = f"任务：{task}"
    if feedback:
        prompt += f"\n\n请根据以下反馈改进你的分析：\n{feedback}"

    response = quick_chat(
        prompt=prompt,
        system_prompt=WORKER_SYSTEM_PROMPT,
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    return extract_json(response.content)


def supervisor_review(task: str, worker_output: dict[str, Any]) -> dict[str, Any]:
    """Supervisor 审核 Worker 输出。

    Args:
        task: 原始任务描述。
        worker_output: Worker 的分析报告。

    Returns:
        审核结果（包含 accuracy, depth, format, passed, feedback）。
    """
    prompt = f"""原始任务：{task}

Worker 输出：
{json.dumps(worker_output, ensure_ascii=False, indent=2)}

请对上述输出进行质量评估。"""

    response = quick_chat(
        prompt=prompt,
        system_prompt=SUPERVISOR_SYSTEM_PROMPT,
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    return extract_json(response.content)


def calculate_score(review: dict[str, Any]) -> int:
    """计算综合评分。

    Args:
        review: Supervisor 审核结果。

    Returns:
        综合评分（整数，1-10）。
    """
    accuracy = review.get("accuracy", 0)
    depth = review.get("depth", 0)
    format_score = review.get("format", 0)

    if not all(isinstance(s, (int, float)) for s in [accuracy, depth, format_score]):
        return 0

    return round((accuracy + depth + format_score) / 3)


def supervisor(task: str, max_retries: int = 3) -> dict[str, Any]:
    """Supervisor 监督模式主函数。

    Args:
        task: 用户任务描述。
        max_retries: 最大重试次数，默认 3 次。

    Returns:
        包含以下字段的字典：
        - output: Worker 最终输出
        - attempts: 尝试次数
        - final_score: 最终评分
        - warning: 警告信息（可选，超次时存在）
    """
    if not task or not task.strip():
        return {
            "output": None,
            "attempts": 0,
            "final_score": 0,
            "warning": "任务不能为空",
        }

    worker_output = None
    feedback = None
    attempts = 0

    for attempt in range(1, max_retries + 1):
        attempts = attempt
        logger.info(f"[尝试 {attempt}/{max_retries}] Worker 执行任务...")

        try:
            worker_output = worker_execute(task, feedback)
            logger.info(f"Worker 输出: {json.dumps(worker_output, ensure_ascii=False)[:100]}...")
        except Exception as e:
            logger.error(f"Worker 执行失败: {e}")
            feedback = f"Worker 执行出错: {e}"
            continue

        logger.info("Supervisor 审核中...")
        try:
            review = supervisor_review(task, worker_output)
            score = calculate_score(review)
            passed = review.get("passed", False)
            feedback = review.get("feedback", "")

            logger.info(f"评分: {score}/10 | 通过: {passed} | 反馈: {feedback[:50]}...")

            if passed or score >= 7:
                logger.info(f"✓ 审核通过（评分: {score}）")
                return {
                    "output": worker_output,
                    "attempts": attempts,
                    "final_score": score,
                }

            logger.info(f"✗ 审核未通过，准备重做...")

        except Exception as e:
            logger.error(f"Supervisor 审核失败: {e}")
            feedback = f"审核过程出错: {e}"

    logger.warning(f"达到最大重试次数 {max_retries}，强制返回")
    warning_msg = (
        f"*** WARNING: MAX RETRIES EXCEEDED ({max_retries}) ***\n"
        f"质量审核未通过，结果可能不达标。建议人工复核。"
    )
    return {
        "output": worker_output,
        "attempts": attempts,
        "final_score": score if "score" in dir() else 0,
        "warning": warning_msg,
    }


if __name__ == "__main__":
    test_cases = [
        {
            "task": "分析 Python 和 JavaScript 在异步编程模型上的本质区别，包括事件循环机制、协程实现、错误处理策略等方面",
            "max_retries": 4,
        },
        {
            "task": "深入解释微服务架构中的服务发现机制，对比 Consul、Eureka、Nacos 三种方案的实现原理和适用场景",
            "max_retries": 4,
        },
        {
            "task": "从存储引擎、索引结构、事务隔离级别、复制机制四个维度，对比 MySQL InnoDB 和 PostgreSQL 的技术差异",
            "max_retries": 4,
        },
    ]

    print("=" * 70)
    print("                    Supervisor 监督模式测试")
    print("=" * 70)

    for i, case in enumerate(test_cases, 1):
        task = case["task"]
        max_retries = case["max_retries"]

        print(f"\n{'=' * 70}")
        print(f"测试 {i}: {task[:50]}...")
        print(f"最大重试次数: {max_retries}")
        print("-" * 70)

        result = supervisor(task, max_retries=max_retries)

        print(f"\n[结果汇总]")
        print(f"  尝试次数: {result['attempts']}")
        print(f"  最终评分: {result['final_score']}/10")

        if result.get("warning"):
            print(f"\n  *** WARNING ***")
            print(f"  {result['warning']}")

        if result["output"]:
            output = result["output"]
            print(f"\n[Worker 输出]")
            print(f"  摘要: {output.get('summary', 'N/A')}")
            print(f"  置信度: {output.get('confidence', 'N/A')}")
            analysis = output.get("analysis", "")
            if len(analysis) > 150:
                print(f"  分析: {analysis[:150]}...")
            else:
                print(f"  分析: {analysis}")
            print(f"  结论: {output.get('conclusion', 'N/A')}")

    print("\n" + "=" * 70)
    print("                         测试完成")
    print("=" * 70)

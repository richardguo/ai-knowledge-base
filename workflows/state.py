"""LangGraph 工作流状态定义。

遵循"报告式通信"原则：字段存储结构化摘要，而非原始数据。
"""

from typing import TypedDict


class KBState(TypedDict):
    """知识库工作流的共享状态。

    用于在 Collector、Analyzer、Organizer、Reviewer 四个节点间传递数据。
    所有字段均为结构化摘要，便于下游节点快速消费。

    Attributes:
        sources: 采集到的原始数据列表。每项包含 title, url, description, readme, popularity 等字段。
        analyses: LLM 分析后的结构化结果列表。每项包含 summary, tags, relevance_score, category 等字段。
        articles: 格式化、去重后的知识条目列表。符合 knowledge/articles/ 的输出格式。
        review_feedback: 审核反馈意见。当 review_passed 为 False 时，包含具体的改进建议。
        review_passed: 审核是否通过。True 表示质量达标，可进入下一阶段。
        iteration: 当前审核循环次数。从 0 开始，最多 3 次，避免无限循环。
        cost_tracker: Token 用量追踪。包含 total_tokens, input_tokens, output_tokens 等字段。
    """

    sources: list[dict]
    analyses: list[dict]
    articles: list[dict]
    review_feedback: str
    review_passed: bool
    iteration: int
    cost_tracker: dict

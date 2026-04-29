"""多 Agent 预算守卫模块。

提供 LLM 调用成本追踪、预算预警和超限保护机制。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


class BudgetExceededError(Exception):
    """预算超限异常。"""

    pass


@dataclass
class CostRecord:
    """单次 LLM 调用记录。

    Attributes:
        timestamp: 调用时间戳。
        node_name: 节点名称。
        prompt_tokens: 输入 Token 数。
        completion_tokens: 输出 Token 数。
        cost_yuan: 本次调用成本（CNY）。
        model: 模型标识符。
    """

    timestamp: str
    node_name: str
    prompt_tokens: int
    completion_tokens: int
    cost_yuan: float
    model: str


class CostGuard:
    """LLM 调用预算守卫。

    三重保护机制：成本记录、预算预警、超限拦截。

    Args:
        budget_yuan: 总预算（CNY）。
        alert_threshold: 预警阈值（0-1），占预算比例。
        input_price_per_million: 输入价格（元/百万 Tokens）。
        output_price_per_million: 输出价格（元/百万 Tokens）。
    """

    def __init__(
        self,
        budget_yuan: float = 1.0,
        alert_threshold: float = 0.8,
        input_price_per_million: float = 1.0,
        output_price_per_million: float = 2.0,
    ) -> None:
        self.budget_yuan = budget_yuan
        self.alert_threshold = alert_threshold
        self.input_price_per_million = input_price_per_million
        self.output_price_per_million = output_price_per_million
        self.records: list[CostRecord] = []
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_cost_yuan: float = 0.0

    def record(
        self,
        node_name: str,
        usage: dict[str, int],
        model: str = "",
    ) -> None:
        """记录一次 LLM 调用的 Token 用量。

        Args:
            node_name: 节点名称。
            usage: Token 用量，格式 {"prompt_tokens": int, "completion_tokens": int}。
            model: 模型标识符。
        """
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cost = (
            prompt_tokens / 1_000_000 * self.input_price_per_million
            + completion_tokens / 1_000_000 * self.output_price_per_million
        )

        rec = CostRecord(
            timestamp=datetime.now().isoformat(),
            node_name=node_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_yuan=cost,
            model=model,
        )
        self.records.append(rec)
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_cost_yuan += cost

    def check(self) -> dict[str, Any]:
        """检查预算状态。

        Returns:
            预算状态字典，包含 status、total_cost、budget、usage_ratio、message。

        Raises:
            BudgetExceededError: 总成本超出预算时抛出。
        """
        usage_ratio = self.total_cost_yuan / self.budget_yuan if self.budget_yuan > 0 else 0.0

        if self.total_cost_yuan >= self.budget_yuan:
            raise BudgetExceededError(
                f"预算超限：总成本 ¥{self.total_cost_yuan:.4f} 已超出预算 ¥{self.budget_yuan:.4f}"
            )

        if usage_ratio >= self.alert_threshold:
            return {
                "status": "warning",
                "total_cost": self.total_cost_yuan,
                "budget": self.budget_yuan,
                "usage_ratio": usage_ratio,
                "message": f"预算预警：已使用 {usage_ratio:.1%}，成本 ¥{self.total_cost_yuan:.4f} / 预算 ¥{self.budget_yuan:.4f}",
            }

        return {
            "status": "ok",
            "total_cost": self.total_cost_yuan,
            "budget": self.budget_yuan,
            "usage_ratio": usage_ratio,
            "message": f"预算正常：已使用 {usage_ratio:.1%}，成本 ¥{self.total_cost_yuan:.4f} / 预算 ¥{self.budget_yuan:.4f}",
        }

    def get_report(self) -> dict[str, Any]:
        """生成成本报告，按节点分组统计。

        Returns:
            成本报告字典。
        """
        node_stats: dict[str, dict[str, Any]] = {}
        for r in self.records:
            if r.node_name not in node_stats:
                node_stats[r.node_name] = {
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cost_yuan": 0.0,
                    "models": [],
                }
            stats = node_stats[r.node_name]
            stats["calls"] += 1
            stats["prompt_tokens"] += r.prompt_tokens
            stats["completion_tokens"] += r.completion_tokens
            stats["cost_yuan"] += r.cost_yuan
            if r.model and r.model not in stats["models"]:
                stats["models"].append(r.model)

        return {
            "total_calls": len(self.records),
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_cost_yuan": self.total_cost_yuan,
            "budget_yuan": self.budget_yuan,
            "usage_ratio": round(
                self.total_cost_yuan / self.budget_yuan if self.budget_yuan > 0 else 0.0, 4
            ),
            "by_node": node_stats,
        }

    def save_report(self, path: str | Path | None = None) -> Path:
        """保存成本报告到 JSON 文件。

        Args:
            path: 输出文件路径，默认为 knowledge/processed/cost-report-{timestamp}.json。

        Returns:
            保存的文件路径。
        """
        if path is None:
            ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
            path = Path(f"knowledge/processed/cost-report-{ts}.json")
        else:
            path = Path(path)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.get_report(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path


if __name__ == "__main__":
    guard = CostGuard(budget_yuan=1.0, alert_threshold=0.8, input_price_per_million=1.0, output_price_per_million=2.0)

    guard.record("collector", {"prompt_tokens": 500_000, "completion_tokens": 100_000}, model="deepseek-v3")
    assert guard.total_prompt_tokens == 500_000
    assert guard.total_cost_yuan == 0.5 + 0.2
    print(f"[PASS] 成本追踪正确：prompt={guard.total_prompt_tokens}, cost=¥{guard.total_cost_yuan:.4f}")

    result = guard.check()
    assert result["status"] == "ok"
    print(f"[PASS] 预算状态正常：{result['message']}")

    guard.record("analyzer", {"prompt_tokens": 150_000, "completion_tokens": 50_000}, model="qwen-plus")
    assert guard.total_prompt_tokens == 650_000
    assert abs(guard.total_cost_yuan - (0.65 + 0.3)) < 1e-9
    print(f"[PASS] 追加记录后：prompt={guard.total_prompt_tokens}, cost=¥{guard.total_cost_yuan:.4f}")

    result = guard.check()
    assert result["status"] == "warning"
    print(f"[PASS] 预警阈值触发：status={result['status']}")

    guard2 = CostGuard(budget_yuan=0.5, alert_threshold=0.8, input_price_per_million=1.0, output_price_per_million=2.0)
    guard2.record("collector", {"prompt_tokens": 500_000, "completion_tokens": 100_000}, model="deepseek-v3")
    try:
        guard2.check()
        assert False, "应抛出 BudgetExceededError"
    except BudgetExceededError:
        print("[PASS] 预算超限检测：正确抛出 BudgetExceededError")

    report = guard.get_report()
    assert "by_node" in report
    assert "collector" in report["by_node"]
    assert "analyzer" in report["by_node"]
    print(f"[PASS] 成本报告生成：{report['total_calls']} 次调用，按节点分组 {list(report['by_node'].keys())}")

    saved = guard.save_report("knowledge/processed/cost-guard-test.json")
    assert saved.exists()
    loaded = json.loads(saved.read_text(encoding="utf-8"))
    assert loaded["total_calls"] == 2
    print(f"[PASS] 报告已保存到 {saved}")
    saved.unlink()

    print("\n所有测试通过！")

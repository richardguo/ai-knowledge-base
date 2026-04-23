"""知识条目 5 维度质量评分。

Usage:
    python hooks/check_quality.py [json_file ...]
    python hooks/check_quality.py                     # 默认扫描 knowledge/articles/*.json
"""

import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

GMT8 = timezone(timedelta(hours=8))


def setup_logger(name: str) -> logging.Logger:
    """创建同时输出到 stderr 和日志文件的 logger。"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z"
    )

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.INFO)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(GMT8).strftime("%Y-%m-%d-%H%M%S")
    log_path = log_dir / f"check_quality-{timestamp}.log"

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

TECH_KEYWORDS: set[str] = {
    "llm", "gpt", "transformer", "agent", "rag", "fine-tun",
    "embed", "token", "inference", "model", "neural", "deep-learning",
    "reinforcement", "diffusion", "multimodal", "prompt",
    "api", "sdk", "framework", "deploy", "docker", "kubernetes",
    "微调", "推理", "部署", "框架", "模型", "代理", "向量", "嵌入",
}

STANDARD_TAGS: set[str] = {
    "large-language-model", "agent-framework", "rag", "fine-tuning",
    "prompt-engineering", "multimodal", "code-generation", "tool-use",
    "autonomous-agents", "reinforcement-learning", "diffusion-model",
    "embedding", "vector-database", "inference", "deployment",
    "python", "typescript", "rust", "go", "java",
    "open-source", "api", "sdk", "mcp", "workflow",
    "chatbot", "code-assistant", "data-analysis",
    "benchmark", "evaluation", "training", "safety",
}

BUZZWORDS_CN: set[str] = {
    "赋能", "抓手", "闭环", "打通", "全链路", "底层逻辑",
    "颗粒度", "对齐", "拉通", "沉淀", "强大的", "革命性的",
}

BUZZWORDS_EN: set[str] = {
    "groundbreaking", "revolutionary", "game-changing",
    "cutting-edge", "game changing",
}


@dataclass
class DimensionScore:
    """单维度评分结果。"""

    name: str
    score: float
    max_score: float
    details: str = ""


@dataclass
class QualityReport:
    """知识条目质量报告。"""

    path: str
    dimensions: list[DimensionScore] = field(default_factory=list)

    @property
    def total_score(self) -> float:
        return sum(d.score for d in self.dimensions)

    @property
    def max_score(self) -> float:
        return sum(d.max_score for d in self.dimensions)

    @property
    def grade(self) -> str:
        ratio = self.total_score / self.max_score * 100 if self.max_score else 0
        if ratio >= 80:
            return "A"
        if ratio >= 60:
            return "B"
        return "C"


def _score_summary(data: dict) -> DimensionScore:
    """摘要质量 (25 分)：>= 50 字满分，>= 20 字基本分，含技术关键词有奖励。"""
    summary: str = data.get("summary", "")
    length = len(summary)
    score = 0.0
    details_parts: list[str] = []

    if length >= 50:
        score += 15
        details_parts.append(f"长度 {length}>=50")
    elif length >= 20:
        score += 10
        details_parts.append(f"长度 {length}>=20")
    else:
        score += max(0, length / 20 * 10)
        details_parts.append(f"长度 {length}<20")

    lower = summary.lower()
    keyword_hits = [kw for kw in TECH_KEYWORDS if kw in lower]
    keyword_bonus = min(len(keyword_hits) * 2, 10)
    score += keyword_bonus
    if keyword_hits:
        details_parts.append(f"技术关键词 +{keyword_bonus}")

    return DimensionScore("摘要质量", score, 25, "; ".join(details_parts))


def _score_depth(data: dict) -> DimensionScore:
    """技术深度 (25 分)：relevance_score 1-10 映射到 0-25。"""
    rs = data.get("relevance_score")
    if not isinstance(rs, (int, float)):
        return DimensionScore("技术深度", 0, 25, "缺少 relevance_score")
    rs = max(1, min(10, rs))
    score = rs / 10 * 25
    return DimensionScore("技术深度", score, 25, f"relevance_score={rs}")


def _score_format(data: dict) -> DimensionScore:
    """格式规范 (20 分)：id/title/url/highlights/时间戳五项各 4 分。"""
    checks: list[tuple[str, bool]] = [
        ("id", bool(data.get("id"))),
        ("title", bool(data.get("title"))),
        ("url", isinstance(data.get("url"), str) and bool(re.match(r"^https?://", data.get("url", "")))),
        ("highlights", isinstance(data.get("highlights"), list) and len(data["highlights"]) > 0),
        (
            "时间戳",
            bool(data.get("collected_at")) or bool(data.get("processed_at")),
        ),
    ]
    score = sum(4 for _, ok in checks if ok)
    missing = [name for name, ok in checks if not ok]
    detail = "全部合规" if not missing else f"缺: {', '.join(missing)}"
    return DimensionScore("格式规范", score, 20, detail)


def _score_tags(data: dict) -> DimensionScore:
    """标签精度 (15 分)：1-3 个合法标签最佳，有标准标签列表校验。"""
    tags = data.get("tags")
    if not isinstance(tags, list):
        return DimensionScore("标签精度", 0, 15, "缺少 tags 字段")

    count = len(tags)
    if count == 0:
        return DimensionScore("标签精度", 0, 15, "无标签")

    if 1 <= count <= 3:
        count_score = 8
    else:
        count_score = max(2, 8 - (count - 3))

    standard_count = sum(1 for t in tags if isinstance(t, str) and t in STANDARD_TAGS)
    standard_score = min(standard_count * 3, 7)

    score = count_score + standard_score
    non_standard = [t for t in tags if isinstance(t, str) and t not in STANDARD_TAGS]
    detail_parts = [f"数量 {count}"]
    if non_standard:
        detail_parts.append(f"非标准标签: {', '.join(non_standard[:3])}")
    else:
        detail_parts.append("全部为标准标签")
    return DimensionScore("标签精度", score, 15, "; ".join(detail_parts))


def _score_buzzword(data: dict) -> DimensionScore:
    """空洞词检测 (15 分)：不含空洞词满分。"""
    text = data.get("summary", "")
    if isinstance(data.get("highlights"), list):
        text += " ".join(str(h) for h in data["highlights"])

    found: list[str] = []
    lower = text.lower()
    for word in BUZZWORDS_CN:
        if word in text:
            found.append(word)
    for word in BUZZWORDS_EN:
        if word in lower:
            found.append(word)

    if not found:
        return DimensionScore("空洞词检测", 15, 15, "未检测到空洞词")

    score = max(0, 15 - len(found) * 5)
    return DimensionScore("空洞词检测", score, 15, f"检测到: {', '.join(found)}")


def score_file(path: Path) -> QualityReport:
    """对单个知识条目进行 5 维度评分。"""
    report = QualityReport(path=str(path))

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        report.dimensions.append(
            DimensionScore("读取失败", 0, 100, str(exc))
        )
        return report

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        report.dimensions.append(
            DimensionScore("JSON 解析失败", 0, 100, str(exc))
        )
        return report

    if not isinstance(data, dict):
        report.dimensions.append(
            DimensionScore("格式错误", 0, 100, "顶层结构应为 dict")
        )
        return report

    report.dimensions = [
        _score_summary(data),
        _score_depth(data),
        _score_format(data),
        _score_tags(data),
        _score_buzzword(data),
    ]
    return report


def _expand_arg(arg: str) -> list[Path]:
    """展开单个参数，支持通配符；无通配符时视为字面路径。"""
    p = Path(arg)
    if "*" in arg or "?" in arg:
        parent = p.parent
        pattern = p.name
        if not parent.is_dir():
            print(f"目录不存在: {parent}", file=sys.stderr)
            return []
        return sorted(
            f for f in parent.glob(pattern) if f.is_file() and f.name != "index.json"
        )
    if p.is_file():
        return [p]
    print(f"文件不存在: {p}", file=sys.stderr)
    return []


def collect_targets(args: list[str]) -> list[Path]:
    """根据命令行参数收集待评分文件。"""
    if args:
        results: list[Path] = []
        for a in args:
            results.extend(_expand_arg(a))
        return results

    articles_dir = Path("knowledge/articles")
    if not articles_dir.is_dir():
        print(f"默认目录不存在: {articles_dir}", file=sys.stderr)
        return []

    return sorted(
        p for p in articles_dir.glob("*.json") if p.name != "index.json"
    )


_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
    "dim": "\033[2m",
}

_GRADE_COLOR = {"A": "green", "B": "yellow", "C": "red"}


def _color(text: str, color: str) -> str:
    return f"{_ANSI[color]}{text}{_ANSI['reset']}"


def _progress_bar(current: int, total: int, width: int = 30) -> str:
    """生成彩色进度条。"""
    filled = int(width * current / total) if total else 0
    ratio = current / total if total else 0
    if ratio >= 0.8:
        bar_color = "green"
    elif ratio >= 0.6:
        bar_color = "yellow"
    else:
        bar_color = "red"
    bar = "█" * filled + "░" * (width - filled)
    return f"{_ANSI[bar_color]}[{bar}]{_ANSI['reset']} {current}/{total}"


def main() -> None:
    """入口函数。"""
    logger = setup_logger("check_quality")
    logger.info("开始质量评分")

    targets = collect_targets(sys.argv[1:])

    if not targets:
        print("未找到待评分的 JSON 文件", file=sys.stderr)
        logger.warning("未找到待评分的 JSON 文件")
        sys.exit(1)

    reports: list[QualityReport] = []
    total = len(targets)

    for i, path in enumerate(targets, 1):
        print(f"  {_color(f'[{i}/{total}]', 'dim')} {path.name}", flush=True)
        report = score_file(path)
        reports.append(report)
        logger.debug(f"[{i}/{total}] {path.name}: 等级 {report.grade}, 分数 {report.total_score:.0f}/{report.max_score}")

    grade_counts = {"A": 0, "B": 0, "C": 0}

    for report in reports:
        grade_counts[report.grade] += 1
        grade_col = _GRADE_COLOR[report.grade]
        print(f"\n{'─' * 60}")
        print(f"  {report.path}")
        print(
            f"  总分: {report.total_score:.0f}/{report.max_score}  "
            f"等级: {_color(report.grade, grade_col)}"
        )
        for d in report.dimensions:
            bar_filled = int(d.score / d.max_score * 20) if d.max_score else 0
            bar = "■" * bar_filled + "□" * (20 - bar_filled)
            ratio = d.score / d.max_score if d.max_score else 0
            if ratio >= 0.8:
                bar = _color(bar, "green")
            elif ratio >= 0.6:
                bar = _color(bar, "yellow")
            else:
                bar = _color(bar, "red")
            print(
                f"  {d.name:<6} {bar} {d.score:5.1f}/{d.max_score:.0f}  {d.details}"
            )
        logger.info(f"{report.path}: 等级 {report.grade}, 分数 {report.total_score:.0f}/{report.max_score}")

    print(f"\n{'═' * 60}")
    a_str = _color(f"A={grade_counts['A']}", "green")
    b_str = _color(f"B={grade_counts['B']}", "yellow")
    c_str = _color(f"C={grade_counts['C']}", "red")
    print(f"  汇总: {a_str}  {b_str}  {c_str}  共 {total} 个文件")

    logger.info(f"汇总: A={grade_counts['A']}, B={grade_counts['B']}, C={grade_counts['C']}, 共 {total} 个文件")

    if grade_counts["C"] > 0:
        logger.error(f"检测到 {grade_counts['C']} 个 C 级文件")
        sys.exit(1)

    logger.info("质量检查通过")


if __name__ == "__main__":
    main()

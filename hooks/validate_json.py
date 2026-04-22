"""校验知识条目 JSON 文件。

Usage:
    python hooks/validate_json.py [json_file ...]
    python hooks/validate_json.py                  # 默认扫描 knowledge/articles/*.json
"""

import json
import re
import sys
from pathlib import Path

REQUIRED_FIELDS: dict[str, type] = {
    "id": str,
    "title": str,
    "url": str,
    "summary": str,
    "tags": list,
}

URL_PATTERN = re.compile(r"^https?://.+")
VALID_AUDIENCES = {"beginner", "intermediate", "advanced"}


def validate_file(path: Path) -> list[str]:
    """校验单个 JSON 文件，返回错误列表。"""
    errors: list[str] = []

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path}: 无法读取文件: {exc}"]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [f"{path}: JSON 解析失败: {exc}"]

    if not isinstance(data, dict):
        return [f"{path}: 顶层结构应为 dict，实际为 {type(data).__name__}"]

    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in data:
            errors.append(f"{path}: 缺少必填字段 '{field}'")
        elif not isinstance(data[field], expected_type):
            errors.append(
                f"{path}: 字段 '{field}' 类型错误，期望 {expected_type.__name__}，"
                f"实际 {type(data[field]).__name__}"
            )

    if isinstance(data.get("url"), str) and not URL_PATTERN.match(data["url"]):
        errors.append(f"{path}: URL 格式无效: {data['url']}")

    if isinstance(data.get("summary"), str) and len(data["summary"]) < 20:
        errors.append(f"{path}: summary 长度不足 20 字（当前 {len(data['summary'])} 字）")

    if isinstance(data.get("tags"), list) and len(data["tags"]) < 1:
        errors.append(f"{path}: tags 至少需要 1 个标签")

    if "relevance_score" in data:
        score = data["relevance_score"]
        if not isinstance(score, (int, float)) or not (1 <= score <= 10):
            errors.append(f"{path}: relevance_score 应为 1-10 的数值，实际: {score}")

    if "audience" in data:
        audience = data["audience"]
        if audience not in VALID_AUDIENCES:
            errors.append(
                f"{path}: audience 应为 {VALID_AUDIENCES} 之一，实际: {audience}"
            )

    return errors


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
    """根据命令行参数收集待校验文件。"""
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


def main() -> None:
    """入口函数。"""
    targets = collect_targets(sys.argv[1:])

    if not targets:
        print("未找到待校验的 JSON 文件", file=sys.stderr)
        sys.exit(1)

    all_errors: list[str] = []
    passed = 0
    failed = 0

    for path in targets:
        errors = validate_file(path)
        if errors:
            failed += 1
            all_errors.extend(errors)
        else:
            passed += 1

    if all_errors:
        print("\n=== 校验错误 ===")
        for err in all_errors:
            print(f"  ✗ {err}")
        print(f"\n=== 汇总: 通过 {passed}, 失败 {failed}, 共 {len(targets)} 个文件 ===")
        sys.exit(1)

    print(f"=== 校验通过: {passed} 个文件全部有效 ===")


if __name__ == "__main__":
    main()

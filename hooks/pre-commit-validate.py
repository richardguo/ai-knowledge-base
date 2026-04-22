#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pre-commit JSON 校验脚本。

校验 knowledge/ 目录下的 JSON 文件是否符合对应的 JSON Schema。
支持三种调用模式：
  1. 无参数：校验 git diff --cached 中的 JSON 文件（pre-commit 模式）
  2. --all：全量校验 knowledge/ 下所有 JSON 文件
  3. 指定文件路径：仅校验指定文件
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

try:
    import jsonschema
    from jsonschema import Draft202012Validator

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "openspec" / "specs" / "schemas"

PATH_SCHEMA_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"knowledge[/\\]raw[/\\]github-search-.*\.json$"), "collector-output.json"),
    (re.compile(r"knowledge[/\\]raw[/\\]github-trending-.*\.json$"), "collector-output.json"),
    (re.compile(r"knowledge[/\\]processed[/\\]analyzer-.*\.json$"), "analyzer-output.json"),
    (re.compile(r"knowledge[/\\]articles[/\\]index\.json$"), "index.json"),
    (re.compile(r"knowledge[/\\]articles[/\\]\d{4}-\d{2}-\d{2}-.*\.json$"), "knowledge-article.json"),
]

SKIP_PATTERNS: list[re.Pattern] = [
    re.compile(r"knowledge[/\\]processed[/\\]collector-.*-status\.json$"),
    re.compile(r"knowledge[/\\]processed[/\\]organizer-.*-status\.json$"),
    re.compile(r"knowledge[/\\]processed[/\\]analyzer-.*-status\.json$"),
]


def _match_schema(file_path: str) -> Optional[str]:
    """根据文件路径模式匹配对应的 schema 文件名。

    Args:
        file_path: 相对于项目根目录的文件路径。

    Returns:
        匹配的 schema 文件名，不匹配返回 None。
    """
    for pattern in SKIP_PATTERNS:
        if pattern.search(file_path.replace("\\", "/")):
            return None

    normalized = file_path.replace("\\", "/")
    for pattern, schema_name in PATH_SCHEMA_MAP:
        if pattern.search(normalized):
            return schema_name

    return None


def _load_schema(schema_name: str) -> dict[str, Any]:
    """加载 JSON Schema 文件。

    Args:
        schema_name: schema 文件名。

    Returns:
        解析后的 schema 字典。

    Raises:
        FileNotFoundError: schema 文件不存在。
        json.JSONDecodeError: schema 文件不是合法 JSON。
    """
    schema_path = SCHEMA_DIR / schema_name
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _validate_file(file_path: str, schema: dict[str, Any]) -> list[tuple[str, str]]:
    """校验单个 JSON 文件是否符合 schema。

    Args:
        file_path: 要校验的文件路径。
        schema: JSON Schema 字典。

    Returns:
        错误列表，每个元素为 (json_path, error_message) 元组。
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [("<root>", f"JSON 解析失败: {e}")]
    except OSError as e:
        return [("<root>", f"文件读取失败: {e}")]

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))

    return [
        (
            ".".join(str(p) for p in err.absolute_path) if err.absolute_path else "<root>",
            err.message,
        )
        for err in errors
    ]


def _get_staged_json_files() -> list[str]:
    """获取 git diff --cached 中匹配 knowledge/**/*.json 的文件列表。

    Returns:
        文件路径列表。
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            return []
    except FileNotFoundError:
        return []

    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().replace("\\", "/").startswith("knowledge/") and line.strip().endswith(".json")
    ]


def _get_all_json_files() -> list[str]:
    """获取 knowledge/ 下所有 JSON 文件列表。

    Returns:
        文件路径列表。
    """
    project_root = Path(__file__).resolve().parent.parent
    knowledge_dir = project_root / "knowledge"
    if not knowledge_dir.exists():
        return []

    files = []
    for json_file in knowledge_dir.rglob("*.json"):
        rel = str(json_file.relative_to(project_root))
        files.append(rel)

    return sorted(files)


def validate_files(file_paths: list[str]) -> tuple[int, int]:
    """校验一组 JSON 文件。

    Args:
        file_paths: 要校验的文件路径列表。

    Returns:
        (总错误数, 有错误的文件数) 元组。
    """
    schema_cache: dict[str, dict[str, Any]] = {}
    total_errors = 0
    files_with_errors = 0

    for file_path in sorted(file_paths):
        schema_name = _match_schema(file_path)
        if schema_name is None:
            continue

        if schema_name not in schema_cache:
            try:
                schema_cache[schema_name] = _load_schema(schema_name)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"FAIL: {file_path}", file=sys.stderr)
                print(f"  <schema>: 无法加载 schema {schema_name}: {e}", file=sys.stderr)
                files_with_errors += 1
                total_errors += 1
                continue

        errors = _validate_file(file_path, schema_cache[schema_name])
        if errors:
            print(f"FAIL: {file_path}", file=sys.stderr)
            for json_path, message in errors:
                print(f"  {json_path}: {message}", file=sys.stderr)
            files_with_errors += 1
            total_errors += len(errors)

    if total_errors > 0:
        print(
            f"\nValidation failed: {total_errors} error(s) in {files_with_errors} file(s)",
            file=sys.stderr,
        )

    return total_errors, files_with_errors


def main() -> int:
    """主函数。

    Returns:
        退出码：0 表示通过，1 表示校验失败。
    """
    if not HAS_JSONSCHEMA:
        print(
            "WARNING: jsonschema not installed, skipping validation. "
            "Install with: pip install jsonschema",
            file=sys.stderr,
        )
        return 0

    parser = argparse.ArgumentParser(
        description="校验 knowledge/ 目录下的 JSON 文件是否符合 schema"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="全量校验 knowledge/ 下所有 JSON 文件",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="指定要校验的文件路径",
    )
    args = parser.parse_args()

    if args.files:
        file_paths = args.files
    elif args.all:
        file_paths = _get_all_json_files()
    else:
        file_paths = _get_staged_json_files()

    if not file_paths:
        return 0

    total_errors, _ = validate_files(file_paths)
    return 1 if total_errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

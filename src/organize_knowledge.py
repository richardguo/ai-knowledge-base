#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
整理 GitHub 分析数据，生成标准化知识条目。

输入: analyzer-2026-04-22-110236.json
输出:
  - knowledge/articles/2026-04-22-{slug}.json (知识条目文件)
  - knowledge/articles/index.json (更新后的索引)
  - knowledge/processed/organizer-2026-04-22-status.json (状态文件)
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def slugify(title: str) -> str:
    """将标题转换为 slug 格式。"""
    # 转换为小写，替换非字母数字字符为连字符
    slug = re.sub(r"[^a-z0-9]", "-", title.lower())
    # 移除连续的连字符
    slug = re.sub(r"-+", "-", slug)
    # 移除首尾的连字符
    slug = slug.strip("-")
    return slug


def create_knowledge_entry(item: Dict[str, Any]) -> Dict[str, Any]:
    """从分析项目创建标准化知识条目。"""
    analysis = item.get("analysis", {})

    # 构建 metadata
    metadata = {
        "author": item.get("author", ""),
        "language": item.get("language", ""),
        "popularity": item.get("popularity", 0),
        "popularity_type": item.get("popularity_type", "total_stars"),
        "topics": item.get("topics", []),
        "created_at": item.get("created_at", ""),
        "updated_at": item.get("updated_at", ""),
        "category": analysis.get("category", ""),
        "maturity": analysis.get("maturity", ""),
    }

    # 构建知识条目
    slug = slugify(item.get("title", ""))
    source = item.get("source", "github-search")

    entry = {
        "id": f"github-{source}-{slug}",
        "title": item.get("title", ""),
        "source": source,
        "url": item.get("url", ""),
        "collected_at": item.get("collected_at", ""),
        "summary": analysis.get("summary", item.get("summary", "")),
        "tags": analysis.get("tags", []),
        "relevance_score": analysis.get("relevance_score", 0),
        "metadata": metadata,
    }

    return entry


def save_knowledge_entry(entry: Dict[str, Any], output_dir: Path, date_str: str) -> str:
    """保存知识条目到文件。"""
    slug = slugify(entry["title"])
    filename = f"{date_str}-{slug}.json"
    filepath = output_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)

    return str(filepath)


def load_index(index_path: Path) -> List[Dict[str, Any]]:
    """加载索引文件。"""
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_index(index: List[Dict[str, Any]], index_path: Path) -> None:
    """保存索引文件。"""
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def update_index(index: List[Dict[str, Any]], entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """更新索引，添加新条目。"""
    existing_ids = {item["id"] for item in index}

    for entry in entries:
        if entry["id"] not in existing_ids:
            index_item = {
                "id": entry["id"],
                "title": entry["title"],
                "url": entry["url"],
                "collected_at": entry["collected_at"],
                "tags": entry["tags"],
                "relevance_score": entry["relevance_score"],
            }
            index.append(index_item)
            existing_ids.add(entry["id"])

    return index


def save_status_file(
    status_path: Path,
    organized_at: str,
    input_file: str,
    entries_created: int,
    entry_files: List[str],
) -> None:
    """保存状态文件。"""
    status = {
        "organized_at": organized_at,
        "version": "1.0",
        "input_file": input_file,
        "entries_created": entries_created,
        "entry_files": entry_files,
        "status": "completed",
    }

    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def main() -> Dict[str, Any]:
    """主函数，执行整理流程。"""
    # 路径配置
    base_dir = Path("D:/Development/PythonProject/Practice_workspace/ai-knowledge-base_v2")
    input_file = base_dir / "knowledge/processed/analyzer-2026-04-22-110236.json"
    articles_dir = base_dir / "knowledge/articles"
    processed_dir = base_dir / "knowledge/processed"
    index_file = articles_dir / "index.json"

    # 确保目录存在
    articles_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    # 读取分析文件
    print(f"读取分析文件: {input_file}")
    with open(input_file, "r", encoding="utf-8") as f:
        analyzer_data = json.load(f)

    # 处理每个项目
    date_str = "2026-04-22"
    entries = []
    entry_files = []
    skipped = 0

    print(f"处理 {len(analyzer_data['items'])} 个项目...")
    for item in analyzer_data["items"]:
        analysis = item.get("analysis", {})
        relevance_score = analysis.get("relevance_score", 0)

        # 只保留 relevance_score >= 6 的项目
        if relevance_score < 6:
            skipped += 1
            continue

        # 创建知识条目
        entry = create_knowledge_entry(item)
        entries.append(entry)

        # 保存到文件
        filepath = save_knowledge_entry(entry, articles_dir, date_str)
        entry_files.append(filepath)
        print(f"  已生成: {Path(filepath).name}")

    # 更新索引
    print(f"\n更新索引文件: {index_file}")
    index = load_index(index_file)
    index = update_index(index, entries)
    save_index(index, index_file)
    print(f"  索引条目数: {len(index)}")

    # 保存状态文件
    organized_at = datetime.now().isoformat()
    status_file = processed_dir / "organizer-2026-04-22-status.json"
    save_status_file(
        status_file,
        organized_at,
        str(input_file.relative_to(base_dir)),
        len(entries),
        [str(Path(f).relative_to(base_dir)) for f in entry_files],
    )
    print(f"\n状态文件已保存: {status_file}")

    # 返回结果
    result = {
        "entries_created": len(entries),
        "entries_skipped": skipped,
        "index_file": str(index_file.relative_to(base_dir)),
        "status_file": str(status_file.relative_to(base_dir)),
        "entry_files": [str(Path(f).relative_to(base_dir)) for f in entry_files],
    }

    print("\n" + "=" * 60)
    print("整理完成!")
    print(f"  成功生成知识条目: {result['entries_created']}")
    print(f"  跳过低分项目: {result['entries_skipped']}")
    print(f"  索引文件: {result['index_file']}")
    print(f"  状态文件: {result['status_file']}")
    print("=" * 60)

    return result


if __name__ == "__main__":
    main()

"""
GitHub Organizer 脚本 - 将 Analyzer 输出转换为标准化知识条目
"""

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from common import (
    GMT8,
    generate_collected_at,
    generate_timestamp,
    setup_logger,
    find_project_root,
)


def load_analyzer_data(input_file: Path) -> dict[str, Any]:
    """加载 Analyzer 输出文件。

    Args:
        input_file: 输入文件路径。

    Returns:
        解析后的 JSON 数据。
    """
    with open(input_file, encoding='utf-8') as f:
        return json.load(f)


def generate_slug(title: str) -> str:
    """从标题生成 slug。

    Args:
        title: 项目标题。

    Returns:
        URL 友好的 slug。
    """
    title_lower = title.lower()
    title_clean = re.sub(r'[^a-z0-9-]', '-', title_lower)
    title_clean = re.sub(r'-+', '-', title_clean)
    return title_clean.strip('-')


def extract_collected_at(item: dict[str, Any], input_data: dict[str, Any]) -> str:
    """从条目或输入数据提取采集时间。

    Args:
        item: 分析条目。
        input_data: Analyzer 输出数据。

    Returns:
        采集时间字符串。
    """
    if item.get('collected_at'):
        return item['collected_at']
    
    source = item.get('source', '')
    collected_ats = input_data.get('collected_ats', {})
    if source in collected_ats:
        return collected_ats[source]
    
    return generate_collected_at()


def process_item(item: dict[str, Any], collected_at: str) -> dict[str, Any]:
    """处理单个分析条目，生成知识条目。

    Args:
        item: 分析条目。
        collected_at: 采集时间。

    Returns:
        知识条目字典。
    """
    analysis = item.get('analysis', {})

    result = {
        'id': str(uuid.uuid4()),
        'title': item.get('title', ''),
        'url': item.get('url', ''),
        'source': item.get('source', ''),
        'collected_at': collected_at,
        'processed_at': generate_collected_at(),
        'summary': analysis.get('summary', ''),
        'highlights': analysis.get('highlights', []),
        'relevance_score': analysis.get('relevance_score', 0),
        'tags': analysis.get('tags', []),
        'category': analysis.get('category', ''),
        'maturity': analysis.get('maturity', ''),
    }

    return result


def generate_markdown(item: dict[str, Any]) -> str:
    """生成 Markdown 内容。

    Args:
        item: 知识条目。

    Returns:
        Markdown 字符串。
    """
    title = item.get('title', '')
    url = item.get('url', '')
    source = item.get('source', '')
    relevance_score = item.get('relevance_score', 0)
    category = item.get('category', '')
    maturity = item.get('maturity', '')
    tags = item.get('tags', [])
    collected_at = item.get('collected_at', '')
    processed_at = item.get('processed_at', '')
    summary = item.get('summary', '')
    highlights = item.get('highlights', [])
    item_id = item.get('id', '')

    tag_str = ', '.join(tags)
    source_display = source.replace('-', ' ').capitalize()

    content = f"""---
id: {item_id}
source: {source}
relevance_score: {relevance_score}
---

# {title}

**来源**: {source_display} | **评分**: {relevance_score}
**分类**: {category} | **成熟度**: {maturity}
**标签**: {tag_str}

**采集时间**: {collected_at}
**处理时间**: {processed_at}

## 摘要
{summary}

## 核心亮点
"""

    for highlight in highlights:
        content += f"- {highlight}\n"

    content += f"\n[原始链接]({url})"

    return content


def write_json(item: dict[str, Any], output_dir: Path) -> Path:
    """写入 JSON 文件。

    Args:
        item: 知识条目。
        output_dir: 输出目录。

    Returns:
        输出文件路径。
    """
    title = item.get('title', '')
    slug = generate_slug(title)
    collected_date = item.get('collected_at', '')[:10]
    filename = f"{collected_date}-{slug}.json"
    output_path = output_dir / filename

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(item, f, ensure_ascii=False, indent=2)

    return output_path


def write_markdown(item: dict[str, Any], output_dir: Path) -> Path:
    """写入 Markdown 文件。

    Args:
        item: 知识条目。
        output_dir: 输出目录。

    Returns:
        输出文件路径。
    """
    title = item.get('title', '')
    slug = generate_slug(title)
    collected_date = item.get('collected_at', '')[:10]
    filename = f"{collected_date}-{slug}.md"
    output_path = output_dir / filename

    markdown_content = generate_markdown(item)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown_content)

    return output_path


def load_index(output_dir: Path) -> dict[str, Any]:
    """加载索引文件。

    Args:
        output_dir: 输出目录。

    Returns:
        索引数据，不存在则返回空索引。
    """
    index_path = output_dir / 'index.json'
    if index_path.exists():
        with open(index_path, encoding='utf-8') as f:
            return json.load(f)

    return {
        'last_updated': '',
        'total_entries': 0,
        'entries': []
    }


def update_index(index_data: dict[str, Any], item: dict[str, Any], json_path: Path, md_path: Path) -> dict[str, Any]:
    """更新索引数据。

    Args:
        index_data: 索引数据。
        item: 知识条目。
        json_path: JSON 文件路径。
        md_path: Markdown 文件路径。

    Returns:
        更新后的索引数据。
    """
    entry = {
        'id': item['id'],
        'title': item['title'],
        'source': item['source'],
        'category': item['category'],
        'relevance_score': item['relevance_score'],
        'json_path': str(json_path),
        'md_path': str(md_path),
        'url': item['url']
    }

    index_data['entries'].append(entry)
    index_data['last_updated'] = generate_collected_at()
    index_data['total_entries'] = len(index_data['entries'])

    return index_data


def write_index(index_data: dict[str, Any], output_dir: Path) -> None:
    """写入索引文件。

    Args:
        index_data: 索引数据。
        output_dir: 输出目录。
    """
    index_path = output_dir / 'index.json'

    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)


def create_status_file(
    processed_dir: Path,
    task_id: str,
    input_file: str,
    output_file: str,
    status: str = "started"
) -> tuple[Path, dict[str, Any]]:
    """创建状态文件。

    Args:
        processed_dir: processed 目录。
        task_id: 任务 ID。
        input_file: 输入文件。
        output_file: 输出文件路径。
        status: 初始状态。

    Returns:
        (状态文件路径, 状态数据字典) 元组。
    """
    timestamp = datetime.now(GMT8).strftime('%Y-%m-%d-%H%M%S')
    status_filename = f"organizer-{timestamp}-status.json"
    status_path = processed_dir / status_filename

    status_data = {
        'agent': 'organizer',
        'task_id': task_id,
        'status': status,
        'input_file': input_file,
        'output_file': output_file,
        'entries_created': 0,
        'entries_skipped': 0,
        'processed_urls': [],
        'start_time': generate_collected_at(),
        'end_time': ''
    }

    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(status_data, indent=2, ensure_ascii=False), encoding='utf-8')

    return status_path, status_data


def update_status_file(status_path: Path, status_data: dict[str, Any], **kwargs: Any) -> None:
    """更新状态文件。

    Args:
        status_path: 状态文件路径。
        status_data: 状态数据字典。
        **kwargs: 要更新的字段。
    """
    for key, value in kwargs.items():
        status_data[key] = value
    status_path.write_text(json.dumps(status_data, indent=2, ensure_ascii=False), encoding='utf-8')


def find_resume_status(processed_dir: Path, input_file: str) -> tuple[Path, dict[str, Any]] | None:
    """查找可恢复的状态文件。

    Args:
        processed_dir: processed 目录。
        input_file: 输入文件路径。

    Returns:
        (状态文件路径, 状态数据) 元组，未找到返回 None。
    """
    if not processed_dir.exists():
        return None

    input_path = str(Path(input_file).resolve())

    for status_file in sorted(
        processed_dir.glob("organizer-*-status.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    ):
        try:
            content = status_file.read_text(encoding='utf-8')
            data = json.loads(content)

            stored_input = data.get('input_file', '')
            if Path(stored_input).resolve() != Path(input_path).resolve():
                continue

            if data.get('status') not in ['completed', 'failed']:
                return (status_file, data)
        except Exception:
            continue

    return None


def load_existing_articles(output_dir: Path) -> dict[str, dict[str, Any]]:
    """加载已存在的知识条目，用于断点续传。

    Args:
        output_dir: 输出目录。

    Returns:
        URL 到条目的映射字典。
    """
    existing: dict[str, dict[str, Any]] = {}
    if not output_dir.exists():
        return existing

    for json_file in output_dir.glob("*.json"):
        if json_file.name == "index.json":
            continue
        try:
            with open(json_file, encoding='utf-8') as f:
                data = json.load(f)
            url = data.get('url', '')
            if url:
                existing[url] = data
        except Exception:
            continue

    return existing


def main():
    parser = argparse.ArgumentParser(description='GitHub Organizer 数据处理脚本')
    parser.add_argument('--input', type=str, required=True, help='Analyzer 输出文件路径')
    parser.add_argument('--output-dir', type=str, default='knowledge/articles', help='输出目录，默认 knowledge/articles')
    parser.add_argument('--processed-dir', type=str, default='knowledge/processed', help='processed 目录，默认 knowledge/processed')
    parser.add_argument('--resume_run', action='store_true', help='从断点续传')

    args = parser.parse_args()

    project_root = find_project_root()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    processed_dir = Path(args.processed_dir)
    logs_dir = project_root / "logs"

    if not input_path.is_absolute():
        input_path = project_root / input_path

    if not input_path.exists():
        print(f"错误: 输入文件不存在: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(GMT8).strftime('%Y-%m-%d-%H%M%S')
    logger = setup_logger('github-organizer', str(logs_dir), timestamp)

    logger.info(f"加载 Analyzer 数据: {input_path}")
    analyzer_data = load_analyzer_data(input_path)

    items = analyzer_data.get('items', [])
    logger.info(f"发现 {len(items)} 个条目")

    task_id = str(uuid.uuid4())
    status_path = None
    status_data = None
    processed_urls: set[str] = set()

    if args.resume_run:
        result = find_resume_status(processed_dir, str(input_path))
        if result:
            status_path, status_data = result
            processed_urls = set(status_data.get('processed_urls', []))
            logger.info(f"恢复任务: {status_data.get('task_id')}, 已处理 {len(processed_urls)} 条")
        else:
            logger.warning("未找到可恢复的任务，创建新任务")

    if not status_path:
        output_file = str(output_dir / "index.json")
        status_path, status_data = create_status_file(
            processed_dir, task_id, str(input_path), output_file
        )
        logger.info(f"开始新任务: {task_id}")

    update_status_file(status_path, status_data, status="running")

    index_data = load_index(output_dir)
    output_files: list[str] = []
    entries_created = 0
    entries_skipped = 0
    total_items = len(items)

    print(f"📋 发现 {total_items} 个条目待处理", file=sys.stderr)

    for idx, item in enumerate(items, 1):
        url = item.get('url', '')
        title = item.get('title', '')
        relevance_score = item.get('analysis', {}).get('relevance_score', 0)

        if relevance_score < 6:
            print(f"[{idx}/{total_items}] ⏭️ 跳过 {title} (评分: {relevance_score})", file=sys.stderr)
            logger.info(f"跳过 {title} (评分: {relevance_score})")
            entries_skipped += 1
            continue

        if url in processed_urls:
            print(f"[{idx}/{total_items}] ⏭️ 跳过已处理: {title}", file=sys.stderr)
            logger.info(f"跳过已处理: {title}")
            continue

        collected_at = extract_collected_at(item, analyzer_data)
        processed_item = process_item(item, collected_at)

        json_path = write_json(processed_item, output_dir)
        md_path = write_markdown(processed_item, output_dir)

        index_data = update_index(index_data, processed_item, json_path, md_path)

        output_files.extend([str(json_path), str(md_path)])
        entries_created += 1
        processed_urls.add(url)

        print(f"[{idx}/{total_items}] ✅ {title} (评分: {relevance_score})", file=sys.stderr)
        logger.info(f"处理完成: {title} (评分: {relevance_score})")

        update_status_file(
            status_path, status_data,
            entries_created=entries_created,
            entries_skipped=entries_skipped,
            processed_urls=list(processed_urls)
        )

    write_index(index_data, output_dir)
    output_files.append(str(output_dir / 'index.json'))

    update_status_file(
        status_path, status_data,
        status="completed",
        output_file=str(output_dir / 'index.json'),
        entries_created=entries_created,
        entries_skipped=entries_skipped,
        end_time=generate_collected_at()
    )

    print(
        f"🎉 整理完成: 创建 {entries_created} 个条目，跳过 {entries_skipped} 个 → {output_dir}",
        file=sys.stderr
    )
    logger.info(f"任务完成:")
    logger.info(f"   - 创建: {entries_created} 个条目")
    logger.info(f"   - 跳过: {entries_skipped} 个条目")
    logger.info(f"   - 索引: {len(index_data['entries'])} 个总条目")
    logger.info(f"   - 输出: {output_dir}")

    print(str(output_dir / 'index.json'))


if __name__ == '__main__':
    main()

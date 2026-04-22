"""
GitHub Search API 采集脚本 - 搜索 AI/LLM/Agent 相关仓库并输出结构化 JSON
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from common import (
    GMT8,
    create_status_file,
    fetch_readme,
    find_project_root,
    find_resume_status,
    generate_collected_at,
    generate_task_id,
    generate_timestamp,
    load_env,
    merge_items,
    parse_timestamp_from_filename,
    read_raw_file,
    setup_logger,
    to_gmt8,
    update_status_file,
    write_raw_file,
)


DEFAULT_KEYWORDS = [
    "AI", "LLM", "agent", "large language model",
    "Harness", "SDD", "RAG", "machine learning",
]

BATCH_SIZE = 3


def build_batch_queries(keywords: list[str]) -> list[str]:
    """将关键词分批构建 GitHub Search API 查询字符串。

    每 BATCH_SIZE 个关键词组成一个查询，避免查询字符串过长被 API 拒绝。

    Args:
        keywords: 搜索关键词列表。

    Returns:
        查询字符串列表，每批一个。
    """
    now = datetime.now(GMT8)
    pushed_after = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    queries = []
    for i in range(0, len(keywords), BATCH_SIZE):
        batch = keywords[i : i + BATCH_SIZE]
        query = f"{' OR '.join(batch)} pushed:>{pushed_after}"
        queries.append(query)

    return queries


def _call_search_api(
    token: str,
    query: str,
    per_page: int,
    logger,
) -> list[dict] | None:
    """调用单次 GitHub Search API 请求。

    Args:
        token: GitHub token。
        query: 查询字符串。
        per_page: 每页返回数量。
        logger: 日志记录器。

    Returns:
        仓库列表，失败返回 None。
    """
    import requests
    import time

    url = "https://api.github.com/search/repositories"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": per_page,
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=30
            )

            logger.info(f"Search API 响应: HTTP {response.status_code}")

            if response.status_code == 429:
                reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
                current_time = int(time.time())
                wait_seconds = max(reset_time - current_time, 60)
                logger.warning(f"API 限流，等待 {wait_seconds} 秒")
                time.sleep(wait_seconds)
                continue

            if response.status_code >= 500:
                wait = 2 ** attempt
                logger.warning(
                    f"服务器错误，{wait}秒后重试 (尝试 {attempt + 1}/{max_retries})"
                )
                time.sleep(wait)
                continue

            if response.status_code >= 400:
                logger.error(f"Search API 请求失败: HTTP {response.status_code}")
                return None

            data = response.json()
            items = data.get("items", [])
            logger.info(f"查询 [{query[:50]}...] 返回 {len(items)} 个仓库")
            return items

        except Exception as e:
            wait = 2 ** attempt
            logger.warning(
                f"请求异常: {e}，{wait}秒后重试 (尝试 {attempt + 1}/{max_retries})"
            )
            if attempt < max_retries - 1:
                time.sleep(wait)
                continue
            else:
                logger.error("Search API 请求失败，已达到最大重试次数")
                return None

    logger.error("Search API 请求失败，已达到最大重试次数")
    return None


def search_repositories(
    token: str,
    top: int,
    keywords: list[str],
    logger,
) -> list[dict] | None:
    """分批调用 GitHub Search API，合并去重后返回结果。

    关键词按 BATCH_SIZE 分组，每批独立查询，结果按 URL 去重（保留 star 数更高的），
    最终按 star 数降序排列并截取 top N。

    Args:
        token: GitHub token。
        top: 返回结果数量。
        keywords: 搜索关键词列表。
        logger: 日志记录器。

    Returns:
        仓库列表，失败返回 None。
    """
    queries = build_batch_queries(keywords)
    logger.info(f"分批查询: {len(keywords)} 个关键词分为 {len(queries)} 批")

    merged: dict[str, dict] = {}
    any_success = False

    for batch_idx, query in enumerate(queries, 1):
        logger.info(f"第 {batch_idx}/{len(queries)} 批查询: {query}")

        items = _call_search_api(token, query, min(top, 100), logger)
        if items is None:
            logger.warning(f"第 {batch_idx} 批查询失败，跳过")
            continue

        any_success = True
        for item in items:
            item_url = item.get("html_url", "")
            item_stars = item.get("stargazers_count", 0)
            existing = merged.get(item_url)
            if existing is None or item_stars > existing.get("stargazers_count", 0):
                merged[item_url] = item

    if not any_success:
        return None

    sorted_items = sorted(
        merged.values(), key=lambda x: x.get("stargazers_count", 0), reverse=True
    )
    result = sorted_items[:top]
    logger.info(
        f"合并去重后: {len(merged)} 个唯一仓库，取 Top {len(result)}"
    )
    return result


def process_repository(
    item: dict,
    token: str,
    logger,
    skip_readme: bool = False
) -> dict:
    """处理单个仓库数据。

    Args:
        item: API 返回的仓库数据。
        token: GitHub token。
        logger: 日志记录器。
        skip_readme: 是否跳过 README 获取。

    Returns:
        处理后的仓库数据字典。
    """
    owner = item.get("owner", {}).get("login", "")
    repo_name = item.get("name", "")

    title = repo_name
    url = item.get("html_url", "")
    popularity = item.get("stargazers_count", 0)
    author = owner
    created_at = to_gmt8(item.get("created_at", ""))
    updated_at = to_gmt8(item.get("updated_at", ""))
    language = item.get("language") or "N/A"
    topics = item.get("topics", [])
    description = item.get("description") or ""

    readme = ""
    if not skip_readme:
        readme = fetch_readme(owner, repo_name, token, logger)

    logger.info(
        f"处理: {owner}/{repo_name} | stars={popularity} | "
        f"topics={topics[:3]}{'...' if len(topics) > 3 else ''}"
    )

    return {
        "title": title,
        "url": url,
        "popularity": popularity,
        "popularity_type": "total_stars",
        "author": author,
        "created_at": created_at,
        "updated_at": updated_at,
        "language": language,
        "topics": topics,
        "description": description,
        "readme": readme,
        "summary": "",
    }


def main():
    parser = argparse.ArgumentParser(description="GitHub Search API 采集脚本")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="knowledge/raw",
        help="输出目录，默认 knowledge/raw"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="取 Top N 项目，默认 20，最大 50"
    )
    parser.add_argument(
        "--keywords",
        type=str,
        default=None,
        help="搜索关键词，逗号分隔，默认 AI,LLM,agent,large language model,Harness,SDD,RAG,machine learning"
    )
    parser.add_argument(
        "--resume_run",
        action="store_true",
        help="继续未完成的任务"
    )

    args = parser.parse_args()

    if args.top > 50:
        print("错误: --top 最大值为 50", file=sys.stderr)
        sys.exit(1)

    keywords = DEFAULT_KEYWORDS
    if args.keywords:
        keywords = [kw.strip() for kw in args.keywords.split(",") if kw.strip()]

    project_root = find_project_root()
    config = load_env()
    token = config["github_token"]

    output_dir = project_root / args.output_dir
    processed_dir = project_root / "knowledge" / "processed"
    logs_dir = project_root / "logs"

    timestamp = None
    task_id = None
    status_data = None
    status_path = None
    raw_items_url = []
    raw_path = None

    if args.resume_run:
        result = find_resume_status(processed_dir, "github-search")
        if not result:
            print("错误: 找不到未完成的任务", file=sys.stderr)
            sys.exit(1)

        status_path, status_data = result
        timestamp = parse_timestamp_from_filename(status_path.name)
        if not timestamp:
            print("错误: 无法解析状态文件时间戳", file=sys.stderr)
            sys.exit(1)

        task_id = status_data.get("task_id", generate_task_id())
        raw_items_url = status_data.get("raw_items_url", [])
        output_files = status_data.get("output_files", [])
        if output_files:
            raw_path = project_root / output_files[0]

        logger = setup_logger("github-search", str(logs_dir), timestamp)
        logger.info(f"恢复任务: {task_id}")

        update_status_file(status_path, status_data, status="running")

    else:
        timestamp = generate_timestamp()
        task_id = generate_task_id()
        logger = setup_logger("github-search", str(logs_dir), timestamp)

        logger.info(f"开始新任务: {task_id}")

        raw_filename = f"github-search-{timestamp}.json"
        raw_path = output_dir / raw_filename
        status_filename = f"collector-search-{timestamp}-status.json"
        status_path = processed_dir / status_filename

        status_data = create_status_file(
            status_path,
            task_id,
            "github-search",
            str(raw_path.relative_to(project_root))
        )

        update_status_file(status_path, status_data, status="running")

    collected_at = generate_collected_at()

    items = search_repositories(token, args.top, keywords, logger)
    if items is None:
        update_status_file(status_path, status_data, status="failed")
        logger.error("Search API 请求失败")
        sys.exit(1)

    existing_data = read_raw_file(raw_path) if raw_path else {"items": []}
    existing_items = existing_data.get("items", [])

    processed_count = 0
    for item in items:
        url = item.get("html_url", "")

        skip_readme = url in raw_items_url

        processed = process_repository(item, token, logger, skip_readme)

        existing_items = merge_items(existing_items, processed)

        if not skip_readme:
            raw_items_url.append(url)

        write_raw_file(raw_path, collected_at, "github-search", existing_items)

        update_status_file(
            status_path, status_data,
            raw_items_url=raw_items_url,
            status="running"
        )

        processed_count += 1

    quality = "ok" if len(existing_items) >= 15 else "below_threshold"

    update_status_file(
        status_path,
        status_data,
        status="completed",
        quality=quality,
        end_time=generate_collected_at()
    )

    logger.info(f"任务完成: 处理 {processed_count} 个仓库，输出 {len(existing_items)} 个条目")
    logger.info(f"质量判定: {quality}")

    print(str(raw_path))


if __name__ == "__main__":
    main()

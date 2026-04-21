"""
GitHub Trending 采集脚本 - 抓取热门 AI/LLM/Agent 仓库并输出结构化 JSON
"""

import argparse
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from common import (
    create_status_file,
    fetch_readme,
    fetch_repo_details,
    find_project_root,
    find_resume_status,
    generate_collected_at,
    generate_task_id,
    generate_timestamp,
    is_excluded,
    load_env,
    matches_ai,
    merge_items,
    parse_timestamp_from_filename,
    read_raw_file,
    setup_logger,
    update_status_file,
    write_raw_file,
    TARGET_TOPICS,
)

SINCE_DEFAULTS = {
    "daily": 20,
    "weekly": 25,
    "monthly": 30,
}


def scrape_trending_page(since: str, logger) -> str | None:
    """抓取 GitHub Trending 页面 HTML。

    Args:
        since: 时间范围 (daily/weekly/monthly)。
        logger: 日志记录器。

    Returns:
        HTML 字符串，失败返回 None。
    """
    url = f"https://github.com/trending?since={since}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    logger.info(f"抓取 Trending 页面: {url}")

    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            response.encoding = "utf-8"
            logger.info(f"Trending 页面响应: HTTP {response.status_code}")
            return response.text
        except Exception as e:
            import time
            wait = 2 ** attempt
            logger.warning(f"页面抓取失败: {e}，{wait}秒后重试 (尝试 {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(wait)
                continue
            else:
                logger.error(f"Trending 页面抓取失败，已达到最大重试次数")
                return None

    return None


def extract_topics_from_html(article, description: str) -> list[str]:
    """从 HTML 元素提取 topics。

    Args:
        article: BeautifulSoup article 元素。
        description: 项目描述。

    Returns:
        topics 列表。
    """
    topics_elems = []
    selectors = [
        "a.topic-tag",
        "a[data-ga-click*='topic']",
        "a[href*='topics']",
        "div.tags a",
        "span.Label--topic",
    ]

    for selector in selectors:
        topics_elems = article.select(selector)
        if topics_elems:
            break

    topics = [t.text.strip().lower() for t in topics_elems if t.text.strip()]

    if not topics and description:
        desc_lower = description.lower()
        for topic in TARGET_TOPICS:
            if topic in desc_lower:
                topics.append(topic)
            if len(topics) >= 5:
                break

    return topics


def extract_language(article) -> str:
    """从 HTML 元素提取编程语言。

    Args:
        article: BeautifulSoup article 元素。

    Returns:
        编程语言字符串。
    """
    lang_elem = article.select_one("[itemprop='programmingLanguage']")
    if lang_elem:
        return lang_elem.text.strip()

    lang_elem = article.select_one("span.d-inline-block.ml-0.mr-3")
    if lang_elem:
        return lang_elem.text.strip()

    for color_div in article.select("div.d-inline-flex"):
        span = color_div.select_one("span")
        if span and span.text.strip():
            return span.text.strip()

    return ""


def extract_star_growth(article, since: str, logger) -> int | None:
    """从 HTML 元素提取 star 增长数。

    Args:
        article: BeautifulSoup article 元素。
        since: 时间范围。
        logger: 日志记录器。

    Returns:
        star 增长数，解析失败返回 None。
    """
    try:
        float_elem = article.select_one("span.d-inline-block.float-sm-right")
        if float_elem:
            text = float_elem.text.strip()
            match = re.search(r"([\d,]+)\s*stars?", text, re.IGNORECASE)
            if match:
                num_str = match.group(1).replace(",", "")
                return int(num_str)

        stars_elem = article.select_one("[href$='stargazers']")
        if stars_elem:
            for sibling in stars_elem.parent.find_all(string=True, recursive=False):
                text = sibling.strip()
                match = re.search(r"([\d,]+)\s*stars?", text, re.IGNORECASE)
                if match:
                    num_str = match.group(1).replace(",", "")
                    return int(num_str)

        all_text = article.get_text()
        patterns = [
            r"([\d,]+)\s*stars?\s*(?:today|this\s*week|this\s*month)",
            r"([\d,]+)\s*stars?",
        ]

        for pattern in patterns:
            match = re.search(pattern, all_text, re.IGNORECASE)
            if match:
                num_str = match.group(1).replace(",", "")
                return int(num_str)

        logger.warning("star 增长数解析失败，使用 0")
        return 0

    except Exception as e:
        logger.error(f"star 增长数解析异常: {e}")
        return None


def parse_trending_html(
    html: str,
    since: str,
    top: int,
    token: str,
    logger
) -> list[dict] | None:
    """解析 Trending 页面 HTML 并提取仓库信息。

    Args:
        html: HTML 字符串。
        since: 时间范围。
        top: 返回结果数量。
        token: GitHub token。
        logger: 日志记录器。

    Returns:
        仓库列表，失败返回 None。
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        repos: list[dict] = []

        articles = soup.select("article.Box-row")
        logger.info(f"找到 {len(articles)} 个仓库条目")

        for article in articles:
            repo_link = article.select_one("h2 a")
            if not repo_link:
                continue

            href = repo_link.get("href", "").strip("/")
            if not href:
                continue

            parts = href.split("/")
            if len(parts) < 2:
                continue

            author = parts[0]
            title = parts[1]
            url = f"https://github.com/{href}"

            desc_elem = article.select_one("p")
            description = desc_elem.text.strip() if desc_elem else ""

            if is_excluded(title, description):
                logger.info(f"排除: {title}")
                continue

            language = extract_language(article)
            html_topics = extract_topics_from_html(article, description)

            topic_match = any(t.lower() in TARGET_TOPICS for t in html_topics)

            api_topics = []
            if not topic_match and not matches_ai(html_topics, description):
                details = fetch_repo_details(author, title, token, logger)
                api_topics = details.get("topics", [])
                topic_match = any(t.lower() in TARGET_TOPICS for t in api_topics)

                if not matches_ai(api_topics if api_topics else html_topics, description):
                    logger.info(f"未匹配 AI 主题: {title}")
                    continue

            final_topics = api_topics if api_topics else html_topics

            star_growth = extract_star_growth(article, since, logger)
            if star_growth is None:
                logger.error(f"star 增长数解析失败: {title}")
                return None

            popularity_type_map = {
                "daily": "daily_stars",
                "weekly": "weekly_stars",
                "monthly": "monthly_stars",
            }

            repo_data = {
                "title": title,
                "url": url,
                "popularity": star_growth,
                "popularity_type": popularity_type_map.get(since, "daily_stars"),
                "author": author,
                "language": language or "N/A",
                "topics": final_topics,
                "description": description,
                "readme": "",
                "created_at": "",
                "updated_at": "",
            }

            repos.append(repo_data)
            logger.info(
                f"匹配: {title} | +{star_growth} stars | topics={final_topics[:3]}"
            )

            if len(repos) >= top:
                break

        return repos

    except Exception as e:
        logger.error(f"HTML 解析失败: {e}")
        return None


def supplement_repository(
    repo: dict,
    token: str,
    logger,
    skip_api: bool = False
) -> dict:
    """补全仓库缺失字段。

    Args:
        repo: 仓库数据字典。
        token: GitHub token。
        logger: 日志记录器。
        skip_api: 是否跳过 API 调用。

    Returns:
        补全后的仓库数据。
    """
    if skip_api:
        return repo

    author = repo.get("author", "")
    title = repo.get("title", "")

    details = fetch_repo_details(author, title, token, logger)
    repo["created_at"] = details.get("created_at", "")
    repo["updated_at"] = details.get("updated_at", "")

    api_topics = details.get("topics", [])
    if api_topics:
        repo["topics"] = api_topics

    readme = fetch_readme(author, title, token, logger)
    repo["readme"] = readme

    return repo


def main():
    parser = argparse.ArgumentParser(description="GitHub Trending 采集脚本")
    parser.add_argument(
        "--since",
        type=str,
        choices=["daily", "weekly", "monthly"],
        default="daily",
        help="时间范围: daily (默认), weekly, monthly"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="knowledge/raw",
        help="输出目录，默认 knowledge/raw"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="取 Top N 项目，默认随 since 变化: daily=20, weekly=25, monthly=30"
    )
    parser.add_argument(
        "--resume_run",
        action="store_true",
        help="继续未完成的任务"
    )

    args = parser.parse_args()

    top = args.top if args.top is not None else SINCE_DEFAULTS.get(args.since, 20)

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
        result = find_resume_status(processed_dir, "github-trending")
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
        raw_output_file = status_data.get("raw_output_file", "")
        if raw_output_file:
            raw_path = project_root / raw_output_file

        logger = setup_logger("github-trending", str(logs_dir), timestamp)
        logger.info(f"恢复任务: {task_id}")

        update_status_file(status_path, status_data, status="running")

    else:
        timestamp = generate_timestamp()
        task_id = generate_task_id()
        logger = setup_logger("github-trending", str(logs_dir), timestamp)

        logger.info(f"开始新任务: {task_id}")

        raw_filename = f"github-trending-{timestamp}-raw.json"
        raw_path = output_dir / raw_filename
        status_filename = f"collector-trending-{timestamp}-status.json"
        status_path = processed_dir / status_filename

        status_data = create_status_file(
            status_path,
            task_id,
            "github-trending",
            str(raw_path.relative_to(project_root))
        )

        update_status_file(status_path, status_data, status="running")

    collected_at = generate_collected_at()

    html = scrape_trending_page(args.since, logger)
    if html is None:
        update_status_file(status_path, status_data, status="failed")
        logger.error("Trending 页面抓取失败")
        sys.exit(1)

    repos = parse_trending_html(html, args.since, top, token, logger)
    if repos is None:
        update_status_file(status_path, status_data, status="failed")
        logger.error("HTML 解析失败")
        sys.exit(1)

    if not repos:
        logger.warning("没有匹配的仓库")

    existing_data = read_raw_file(raw_path) if raw_path else {"items": []}
    existing_items = existing_data.get("items", [])

    processed_count = 0
    for repo in repos:
        url = repo.get("url", "")

        skip_api = url in raw_items_url

        repo = supplement_repository(repo, token, logger, skip_api)

        existing_items = merge_items(existing_items, repo)

        if not skip_api:
            raw_items_url.append(url)

        write_raw_file(
            raw_path, collected_at, "github-trending", existing_items, args.since
        )

        update_status_file(
            status_path, status_data,
            raw_items_url=raw_items_url,
            status="running"
        )

        processed_count += 1

    quality = "ok" if len(existing_items) >= 10 else "below_threshold"

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

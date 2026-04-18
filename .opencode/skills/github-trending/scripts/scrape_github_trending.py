"""
GitHub Trending 采集脚本 - 抓取热门 AI/LLM/Agent 仓库并输出结构化 JSON
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

TARGET_TOPICS = {
    "ai", "llm", "agent", "ml", "machine-learning", "large-language-model",
    "generative-ai", "deeplearning", "deep-learning", "transformer",
    "rlhf", "reinforcement-learning", "nlp", "neural-network",
    "artificial-intelligence", "language-model", "openai", "anthropic",
    "claude", "chatgpt", "gpt", "huggingface", "transformers",
}

EXCLUDE_PATTERNS = {
    "awesome-", "curated list", "book", "course", "tutorial",
    "roadmap", "interview", "cheatsheet",
}

DESC_KEYWORDS = [
    "ai", "llm", "agent", "machine learning", "neural",
    "deep learning", "nlp", "language model", "ml",
]

RAW_DIR = Path("knowledge/raw")


def _is_excluded(name: str, description: str) -> bool:
    name_lower = name.lower()
    desc_lower = description.lower()
    for pattern in EXCLUDE_PATTERNS:
        if pattern in name_lower or pattern in desc_lower:
            return True
    return False


def _extract_topics(article, description: str) -> list[str]:
    topics_elems = []
    for selector in [
        "a.topic-tag",
        "a[data-ga-click*='topic']",
        "a[href*='topics']",
        "div.tags a",
        "span.Label--topic",
    ]:
        topics_elems = article.select(selector)
        if topics_elems:
            break

    topics = [t.text.strip().lower() for t in topics_elems]

    if not topics and description:
        desc_lower = description.lower()
        for topic in TARGET_TOPICS:
            if topic in desc_lower:
                topics.append(topic)
            if len(topics) >= 5:
                break

    return topics


def _extract_language(article) -> str:
    lang_elem = article.select_one(
        "[itemprop='programmingLanguage']"
    ) or article.select_one("span.d-inline-block.ml-0.mr-3")
    if lang_elem:
        return lang_elem.text.strip()
    for color_div in article.select("div.d-inline-flex"):
        span = color_div.select_one("span")
        if span and span.text.strip():
            return span.text.strip()
    return ""


def _matches_ai(topic_match: bool, description: str) -> bool:
    if topic_match:
        return True
    desc_lower = description.lower()
    return any(kw in desc_lower for kw in DESC_KEYWORDS)


def scrape_github_trending(max_items: int = 50) -> list[dict]:
    try:
        url = "https://github.com/trending"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = "utf-8"

        soup = BeautifulSoup(response.text, "html.parser")
        repos: list[dict] = []

        for article in soup.select("article.Box-row"):
            repo_link = article.select_one("h2 a")
            if not repo_link:
                continue

            name = repo_link.get("href", "").strip("/")
            repo_url = f"https://github.com/{name}"

            desc_elem = article.select_one("p")
            description = desc_elem.text.strip() if desc_elem else ""

            if _is_excluded(name, description):
                print(f"排除: {name}", file=sys.stderr)
                continue

            stars_elem = article.select_one("[href$='stargazers']")
            stars = (
                int(re.sub(r"[^0-9]", "", stars_elem.text.strip()))
                if stars_elem
                else 0
            )

            language = _extract_language(article)
            topics = _extract_topics(article, description)
            topic_match = any(t in TARGET_TOPICS for t in topics)

            if not _matches_ai(topic_match, description):
                print(f"未匹配: {name}", file=sys.stderr)
                continue

            print(f"匹配: {name} | stars={stars} | topics={topics}", file=sys.stderr)

            repos.append({
                "name": name,
                "url": repo_url,
                "summary": "",
                "stars": stars,
                "language": language,
                "topics": topics,
            })

            if len(repos) >= max_items:
                break

        repos.sort(key=lambda r: r["stars"], reverse=True)
        return repos

    except requests.exceptions.RequestException as e:
        print(f"网络错误: {e}", file=sys.stderr)
        return []
    except (ValueError, TypeError) as e:
        print(f"解析错误: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"未知错误: {e}", file=sys.stderr)
        return []


def build_output(repos: list[dict], top_n: int = 15) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    items = repos[:top_n]
    return {
        "source": "github",
        "skill": "github-trending",
        "collected_at": now,
        "items": items,
    }


def save_output(data: dict) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filepath = RAW_DIR / f"github-trending-{date_str}.json"
    filepath.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return filepath


if __name__ == "__main__":
    start = time.time()
    repos = scrape_github_trending(max_items=50)
    output = build_output(repos, top_n=15)

    elapsed = time.time() - start
    print(f"执行时间: {elapsed:.2f}s | 条目数: {len(output['items'])}", file=sys.stderr)

    if elapsed > 9.5:
        print("[]")
    else:
        filepath = save_output(output)
        print(f"已保存: {filepath}", file=sys.stderr)
        print(json.dumps(output, indent=2, ensure_ascii=False))

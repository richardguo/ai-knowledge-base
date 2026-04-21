"""为采集的原始数据生成中文摘要"""

import json
import os
import sys
from pathlib import Path

import requests

PROMPT_TEMPLATE = """请为以下 GitHub 项目生成 50-200 字的中文摘要，介绍其核心功能和价值。

项目名称：{title}
作者：{author}
语言：{language}
标签：{topics}
描述：{description}
README 片段：{readme}

请直接输出摘要，不要有其他内容。"""


def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ[key] = value


def generate_summary(api_base: str, api_key: str, model: str, item: dict) -> str:
    prompt = PROMPT_TEMPLATE.format(
        title=item.get("title", ""),
        author=item.get("author", ""),
        language=item.get("language", ""),
        topics=", ".join(item.get("topics", [])),
        description=item.get("description", "")[:500],
        readme=item.get("readme", "")[:2000],
    )

    url = f"{api_base.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300,
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    result = response.json()

    message = result["choices"][0]["message"]
    if "reasoning_content" in message and message["reasoning_content"]:
        return message["reasoning_content"].strip()
    return (message.get("content") or "").strip()


def process_raw_file(raw_path: Path, output_path: Path):
    load_env()

    api_base = os.environ.get("LLM_API_BASE", "")
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL_ID", "GLM-4.7")

    if not api_key:
        print("错误: LLM_API_KEY 未配置")
        sys.exit(1)

    with open(raw_path, encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items", [])
    print(f"处理 {len(items)} 个条目...")

    processed_items = []
    for i, item in enumerate(items, 1):
        print(f"  [{i}/{len(items)}] 生成摘要: {item.get('title', '')}")
        try:
            summary = generate_summary(api_base, api_key, model, item)
        except Exception as e:
            print(f"    警告: 摘要生成失败 - {e}")
            summary = item.get("description", "")[:200]

        processed_item = {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "popularity": item.get("popularity", 0),
            "popularity_type": item.get("popularity_type", ""),
            "author": item.get("author", ""),
            "language": item.get("language", ""),
            "topics": item.get("topics", []),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
            "summary": summary,
        }
        processed_items.append(processed_item)

    output_data = {
        "collected_at": data.get("collected_at", ""),
        "source": data.get("source", ""),
        "version": "1.0",
        "items": processed_items,
    }

    if "since" in data:
        output_data["since"] = data["since"]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"输出文件: {output_path}")
    return len(processed_items)


def main():
    if len(sys.argv) < 2:
        print("用法: python summarize_raw.py <raw_file>")
        sys.exit(1)

    raw_path = Path(sys.argv[1])
    if not raw_path.exists():
        print(f"错误: 文件不存在 {raw_path}")
        sys.exit(1)

    if raw_path.name.endswith("-raw.json"):
        output_name = raw_path.name.replace("-raw.json", ".json")
    else:
        output_name = raw_path.stem + ".json"

    output_path = raw_path.parent / output_name

    count = process_raw_file(raw_path, output_path)
    print(f"完成: 处理 {count} 个条目")


if __name__ == "__main__":
    main()

"""
摘要生成脚本 - 基于 description 和 readme 生成中文摘要
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

MAX_CONCURRENT = 5


def load_config():
    """从 .env 加载 LLM 配置"""
    from dotenv import load_dotenv
    import os

    project_root = Path(__file__).resolve().parents[4]
    env_path = project_root / ".env"
    load_dotenv(env_path)

    return {
        "api_base": os.getenv("LLM_API_BASE", ""),
        "api_key": os.getenv("LLM_API_KEY", ""),
        "model_id": os.getenv("LLM_MODEL_ID", ""),
    }


def generate_summary(
    title: str,
    description: str,
    readme: str,
    config: dict
) -> str:
    """调用 LLM 生成中文摘要。

    Args:
        title: 项目名称。
        description: 项目描述。
        readme: README 内容。
        config: LLM 配置。

    Returns:
        中文摘要字符串。
    """
    if not config["api_base"] or not config["api_key"]:
        print("LLM 配置缺失", file=sys.stderr)
        return "摘要生成失败"

    content = f"""请基于以下信息，用中文写一个50-200字的项目摘要，重点介绍项目功能和特点：

项目名称：{title}

项目描述：
{description or '无'}

README 内容（前3000字）：
{readme[:3000] if readme else '无'}

请直接输出摘要内容，不要添加任何前缀或后缀。"""

    try:
        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": config["model_id"],
            "messages": [
                {"role": "user", "content": content}
            ],
            "max_tokens": 500,
            "temperature": 0.7,
        }

        url = config["api_base"].rstrip("/") + "/chat/completions"
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()
            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                result = msg.get("content", "")
                if not result:
                    result = msg.get("reasoning_content", "")
                result = result.strip() if result else ""
            else:
                result = ""
            if not result:
                print(f"LLM 返回空内容: {data}", file=sys.stderr)
            return result if result else "摘要生成失败"
        else:
            print(f"LLM API 错误: HTTP {response.status_code}", file=sys.stderr)
            print(f"Response: {response.text[:500]}", file=sys.stderr)
            return "摘要生成失败"

    except Exception as e:
        print(f"摘要生成异常: {e}", file=sys.stderr)
        return "摘要生成失败"


def process_raw_file(raw_path: Path, config: dict) -> dict:
    """处理中间文件，生成摘要。

    Args:
        raw_path: 中间文件路径。
        config: LLM 配置。

    Returns:
        处理后的数据字典。
    """
    with open(raw_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items", [])
    total = len(items)
    print(f"处理 {total} 个项目 (并发 {MAX_CONCURRENT})...", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        future_to_index = {}
        for i, item in enumerate(items):
            future = executor.submit(
                generate_summary,
                item.get("title", ""),
                item.get("description", ""),
                item.get("readme", ""),
                config,
            )
            future_to_index[future] = i

        done_count = 0
        for future in as_completed(future_to_index):
            i = future_to_index[future]
            item = items[i]
            try:
                summary = future.result()
            except Exception as e:
                print(f"摘要生成异常: {e}", file=sys.stderr)
                summary = "摘要生成失败"
            item["summary"] = summary
            del item["readme"]
            del item["description"]
            done_count += 1
            print(f"[{done_count}/{total}] 完成: {item.get('title', '')}", file=sys.stderr)

    return data


def main():
    import argparse

    parser = argparse.ArgumentParser(description="基于 description 和 readme 生成中文摘要")
    parser.add_argument(
        "raw_file",
        nargs="?",
        help="中间文件路径 (位置参数)"
    )
    parser.add_argument(
        "--input", "-i",
        help="中间文件路径 (命名参数)"
    )
    parser.add_argument(
        "--output", "-o",
        help="输出文件路径 (可选，默认自动命名)"
    )

    args = parser.parse_args()

    # 优先使用 --input，其次是位置参数
    raw_file_path = args.input or args.raw_file
    if not raw_file_path:
        parser.print_help()
        sys.exit(1)

    raw_path = Path(raw_file_path)
    if not raw_path.is_absolute():
        project_root = Path(__file__).resolve().parents[4]
        raw_path = project_root / raw_path
    if not raw_path.exists():
        print(f"❌ 错误: 文件不存在 {raw_path}", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    print(f"📄 输入文件: {raw_path}", file=sys.stderr)
    print(f"🔧 LLM 配置: base={config['api_base']}, model={config['model_id']}", file=sys.stderr)

    data = process_raw_file(raw_path, config)

    # 确定输出路径
    if args.output:
        final_path = Path(args.output)
    else:
        final_filename = raw_path.name.replace("-raw.json", ".json")
        final_path = raw_path.parent / final_filename

    with open(final_path, "w", encoding="utf-8") as f:
        json.dump(data, indent=2, fp=f, ensure_ascii=False)

    print(f"✅ 最终文件: {final_path}", file=sys.stderr)
    print(str(final_path))


if __name__ == "__main__":
    main()

"""验证 rss_sources.yaml 格式和 URL 可用性."""
import sys
from pathlib import Path

import httpx
import yaml

YAML_PATH = Path("pipeline/rss_sources.yaml")
TIMEOUT = 15.0


def validate_yaml(path: Path) -> dict:
    """验证 YAML 格式并返回数据."""
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert "sources" in data, "缺少顶层 'sources' 键"
    sources = data["sources"]
    assert isinstance(sources, list), "'sources' 必须是列表"

    required_fields = {"name", "url", "category", "enabled"}
    for idx, src in enumerate(sources):
        missing = required_fields - set(src.keys())
        assert not missing, f"第 {idx + 1} 个源 '{src.get('name', '?')}' 缺少字段: {missing}"
        assert isinstance(src["enabled"], bool), f"'{src['name']}' 的 enabled 必须是布尔值"

    return data


def check_urls(sources: list[dict]) -> None:
    """快速探测 RSS URL 可访问性."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    print("\n--- URL 可用性探测 ---")
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        for src in sources:
            name = src["name"]
            url = src["url"]
            try:
                resp = client.get(url, headers=headers)
                status = resp.status_code
                content_type = resp.headers.get("content-type", "unknown")
                # 简单判断是否是 RSS/XML 内容
                is_feed = "xml" in content_type.lower() or resp.text.strip().startswith("<?xml")
                print(f"  [{status}] {name}: {url}")
                if status == 200 and not is_feed:
                    print(f"       ⚠️  返回 200 但 Content-Type 不是 XML ({content_type})")
                elif status != 200:
                    print(f"       ⚠️  非 200 状态码，可能需要确认")
            except httpx.TimeoutException:
                print(f"  [TIMEOUT] {name}: {url}")
            except Exception as e:
                print(f"  [ERROR] {name}: {e}")


def main() -> int:
    """主函数."""
    print("=== RSS 数据源配置验证 ===")
    print(f"文件: {YAML_PATH.resolve()}")

    try:
        data = validate_yaml(YAML_PATH)
    except Exception as e:
        print(f"YAML 验证失败: {e}")
        return 1

    sources = data["sources"]
    print(f"YAML 格式: OK")
    print(f"源数量: {len(sources)}")

    enabled_count = sum(1 for s in sources if s["enabled"])
    disabled_count = len(sources) - enabled_count
    print(f"  enabled: {enabled_count}, disabled: {disabled_count}")

    for s in sources:
        flag = "✅" if s["enabled"] else "❌"
        print(f"  {flag} [{s['category']}] {s['name']}")

    check_urls(sources)

    print("\n=== 验证完成 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

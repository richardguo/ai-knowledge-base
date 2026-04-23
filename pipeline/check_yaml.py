import yaml
from pathlib import Path

data = yaml.safe_load(Path('pipeline/rss_sources.yaml').read_text())
sources = data.get('sources', [])
enabled = [s for s in sources if s.get('enabled')]

print(f'总数据源: {len(sources)} 个')
print(f'已启用: {len(enabled)} 个')
for s in enabled:
    print(f'  - {s["name"]} ({s["category"]})')

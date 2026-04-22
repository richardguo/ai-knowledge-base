import json
from datetime import datetime
from pathlib import Path

# 读取分析数据
with open('knowledge/processed/analyzer-2026-04-22-110236.json', 'r', encoding='utf-8') as f:
    analysis_data = json.load(f)

print(f"Total items: {len(analysis_data['items'])}")

# 知识条目输出目录
articles_dir = Path('knowledge/articles')
articles_dir.mkdir(exist_ok=True)

# 生成的知识条目列表
entries = []
output_files = []

# 当前日期
today = datetime.now().strftime('%Y-%m-%d')

# 转换为知识条目
for item in analysis_data['items']:
    # 生成 slug
    slug = item['title'].lower().replace(' ', '-')

    # 生成知识条目
    entry = {
        'id': f"github-{item['source']}-{slug}",
        'title': item['title'],
        'source': item['source'],
        'url': item['url'],
        'collected_at': item.get('updated_at', item.get('created_at', '')),
        'summary': item['summary'],
        'tags': item['analysis']['tags'],
        'relevance_score': item['analysis']['relevance_score'],
        'metadata': {
            'author': item['author'],
            'language': item.get('language', 'N/A'),
            'popularity': item['popularity'],
            'popularity_type': item['popularity_type'],
            'topics': item.get('topics', []),
            'created_at': item['created_at'],
            'updated_at': item['updated_at'],
            'category': item['analysis']['category'],
            'maturity': item['analysis']['maturity']
        }
    }

    # 写入文件
    output_file = articles_dir / f"{today}-{slug}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)

    output_files.append(str(output_file))

    # 添加到索引
    index_entry = {
        'id': entry['id'],
        'title': item['title'],
        'source': item['source'],
        'url': item['url'],
        'file_path': str(output_file),
        'tags': item['analysis']['tags'],
        'relevance_score': item['analysis']['relevance_score'],
        'collected_at': item.get('updated_at', item.get('created_at', ''))
    }
    entries.append(index_entry)

    print(f"Created: {output_file}")

# 更新索引文件
index_file = articles_dir / 'index.json'

# 读取现有索引（如果存在）
existing_index = {'entries': []}
if index_file.exists():
    with open(index_file, 'r', encoding='utf-8') as f:
        existing_index = json.load(f)

# 合并新条目
existing_entries = {e['id']: e for e in existing_index.get('entries', [])}
new_entries = {e['id']: e for e in entries}
existing_entries.update(new_entries)

# 写入新索引
new_index = {
    'version': '1.0',
    'last_updated': datetime.now().isoformat(),
    'total_entries': len(existing_entries),
    'entries': list(existing_entries.values())
}

with open(index_file, 'w', encoding='utf-8') as f:
    json.dump(new_index, f, ensure_ascii=False, indent=2)

print(f"\nUpdated index: {index_file}")
print(f"Total entries in index: {len(existing_entries)}")
print(f"New entries added: {len(entries)}")

# 生成状态文件
status_dir = Path('knowledge/processed')
status_file = status_dir / f"organizer-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}-status.json"

status_data = {
    'agent': 'organizer',
    'task_id': f"{datetime.now().strftime('%Y-%m-%d-%H%M%S')}-manual",
    'status': 'completed',
    'input_files': ['knowledge/processed/analyzer-2026-04-22-110236.json'],
    'output_files': output_files,
    'index_file': str(index_file),
    'total_entries': len(entries),
    'filtered_entries': 0,
    'quality': 'ok',
    'start_time': analysis_data['analyzed_at'],
    'end_time': datetime.now().isoformat()
}

with open(status_file, 'w', encoding='utf-8') as f:
    json.dump(status_data, f, ensure_ascii=False, indent=2)

print(f"Created status file: {status_file}")
print(f"\n✅ Organization completed!")
print(f"- Knowledge entries: {len(entries)}")
print(f"- Index file: {index_file}")
print(f"- Status file: {status_file}")

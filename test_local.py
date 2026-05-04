import json
d = json.load(open('knowledge/articles/index.json'))
print(f'索引共 {len(d["entries"])} 条')
print('样例:', d["entries"][0])


import json
import datetime
from distribution.formatter import json_to_markdown, json_to_feishu

article = json.load(open('knowledge/articles/2026-05-03-open-webui.json'))

print('=== Markdown ===')
print(json_to_markdown(article))
print()
print('=== Feishu (前 200 字符) ===')
print(json.dumps(json_to_feishu(article), ensure_ascii=False)[:200])


from distribution.formatter import generate_daily_digest
result = generate_daily_digest(date=datetime.date(2026, 5, 3), top_n=5)
print('=== Markdown 简报 ===')
print(result['markdown'])

import asyncio
from distribution.publisher import publish_daily_digest

async def test():
    results = await publish_daily_digest(
        knowledge_dir='knowledge/articles',
        date='2026-05-04',  # 改成你知识库里有数据的日期
        channel=['feishu']
    )
    for r in results:
        status = '✅' if r.success else '❌'
        print(f'{status} {r.channel}: {r.message_id or r.error}')

asyncio.run(test())


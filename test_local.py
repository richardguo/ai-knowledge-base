# import json
# d = json.load(open('knowledge/articles/index.json'))
# print(f'索引共 {len(d["entries"])} 条')
# print('样例:', d["entries"][0])
#
#
# import json
# import datetime
# from distribution.formatter import json_to_markdown, json_to_feishu
#
# article = json.load(open('knowledge/articles/2026-05-03-open-webui.json'))
#
# print('=== Markdown ===')
# print(json_to_markdown(article))
# print()
# print('=== Feishu (前 200 字符) ===')
# print(json.dumps(json_to_feishu(article), ensure_ascii=False)[:200])
#
#
# from distribution.formatter import generate_daily_digest
# result = generate_daily_digest(date=datetime.date(2026, 5, 3), top_n=5)
# print('=== Markdown 简报 ===')
# print(result['markdown'])
#
# import asyncio
# from distribution.publisher import publish_daily_digest
#
# async def test():
#     results = await publish_daily_digest(
#         knowledge_dir='knowledge/articles',
#         date='2026-05-04',  # 改成你知识库里有数据的日期
#         channel=['feishu']
#     )
#     for r in results:
#         status = '✅' if r.success else '❌'
#         print(f'{status} {r.channel}: {r.message_id or r.error}')
#
# asyncio.run(test())

####################################################################
####################################################################
####################################################################
from bot.knowledge_bot import KnowledgeBot, recognize_intent, Intent, format_search_results

# 测试意图识别
tests = [
    ('/search MCP', Intent.SEARCH, 'MCP'),
    ('/today', Intent.TODAY, ''),
    ('/top', Intent.TOP, ''),
    ('搜索 Agent 文章', Intent.SEARCH, ''),
    ('今天有什么新内容', Intent.TODAY, ''),
    ('随便聊聊', Intent.UNKNOWN, ''),
]

print('=== 意图识别测试 ===')
for text, expected_intent, _ in tests:
    intent, args = recognize_intent(text)
    status = '✅' if intent == expected_intent else '❌'
    print(f'{status} "{text}" → {intent.value} (args={args!r})')

# 测试 Bot 完整流程
bot = KnowledgeBot()
print()
print('=== Bot 消息处理测试 ===')
for text in ['/help', '/search Agent', '/today', '搜索 MCP 协议']:
    print(f'输入: {text}')
    print(f'回复: {bot.handle_message("test-user", text)[:80]}...')
    print()






import sys; sys.path.insert(0, '.')
from bot.knowledge_bot import KnowledgeSearchEngine, recognize_intent

# 1. 意图识别
print('--- 意图识别 ---')
for q in ['/search agent', '/today', '/top 3', '/help', '搜一下 RAG']:
    intent, payload = recognize_intent(q)
    print(f'  {q!r:25s} → {intent.name:18s} payload={payload!r}')

# 2. 加权搜索
print()
print('--- /search agent (top 3) ---')
engine = KnowledgeSearchEngine('knowledge/articles')
results = engine.search(keyword='agent', limit=3)
print(format_search_results(results=results, custom_query_input='agent'))
# print(results)
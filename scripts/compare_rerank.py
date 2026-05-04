"""对比 Rerank 前后搜索结果的脚本。"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(".env"))

from bot.knowledge_bot import (
    KnowledgeSearchEngine,
    Reranker,
    SynonymExpander,
    _article_to_document,
)

engine = KnowledgeSearchEngine("knowledge/articles")
expander = SynonymExpander("bot/synonyms.json")
reranker = Reranker()

query = "智能体"
expanded = expander.expand(query)
print(f"原始查询: {query}")
print(f"同义词扩展: {expanded}")
print()

results_before = engine.search(keyword=expanded, limit=10)
print("=== Rerank 前（规则匹配 top 10，按 relevance_score 排序）===")
for i, a in enumerate(results_before):
    title = a.get("title", "")
    score = a.get("relevance_score", "N/A")
    tags = a.get("tags", [])
    print(f"  {i}. {title}  [score={score}]  tags={tags}")
print()

if reranker.is_configured and results_before:
    docs = [_article_to_document(a) for a in results_before]
    indices = reranker.rerank(query, docs, top_n=5)
    reranked = [results_before[i] for i in indices if i < len(results_before)]
    remaining_set = set(indices)
    remaining = [r for i, r in enumerate(results_before) if i not in remaining_set]
    results_after = reranked + remaining

    print("=== Rerank 后（bge-reranker-v2-m3 重排，取 top 5）===")
    print(f"Rerank 返回的索引: {indices}")
    for i, a in enumerate(results_after):
        title = a.get("title", "")
        score = a.get("relevance_score", "N/A")
        tags = a.get("tags", [])
        marker = " <-- reranked top5" if i < len(reranked) else ""
        print(f"  {i}. {title}  [score={score}]  tags={tags}{marker}")
else:
    print("Reranker 未配置，跳过")

print()
print("--- 第二个查询: 大模型 ---")
query2 = "大模型"
expanded2 = expander.expand(query2)
print(f"原始查询: {query2}")
print(f"同义词扩展: {expanded2}")
print()

results_before2 = engine.search(keyword=expanded2, limit=10)
print("=== Rerank 前 ===")
for i, a in enumerate(results_before2):
    title = a.get("title", "")
    score = a.get("relevance_score", "N/A")
    tags = a.get("tags", [])
    print(f"  {i}. {title}  [score={score}]  tags={tags}")
print()

if reranker.is_configured and results_before2:
    docs2 = [_article_to_document(a) for a in results_before2]
    indices2 = reranker.rerank(query2, docs2, top_n=5)
    reranked2 = [results_before2[i] for i in indices2 if i < len(results_before2)]
    remaining_set2 = set(indices2)
    remaining2 = [r for i, r in enumerate(results_before2) if i not in remaining_set2]
    results_after2 = reranked2 + remaining2

    print("=== Rerank 后 ===")
    print(f"Rerank 返回的索引: {indices2}")
    for i, a in enumerate(results_after2):
        title = a.get("title", "")
        score = a.get("relevance_score", "N/A")
        tags = a.get("tags", [])
        marker = " <-- reranked top5" if i < len(reranked2) else ""
        print(f"  {i}. {title}  [score={score}]  tags={tags}{marker}")

---
name: github-trending
description: |
  采集 GitHub Trending 热门 AI/LLM/Agent 仓库并输出结构化 JSON。当用户提到
  GitHub Trending、热门 AI 项目、trending repos、最新 agent 框架、
  开源情报采集、技术趋势时触发。
allowed-tools: [Bash, WebSearch, Read, Grep, Glob, WebFetch]
---

# GitHub Trending 采集技能

## 使用场景

- 每日技术情报收集
- AI 技术趋势分析
- 开源项目发现与评估
- 知识库数据源更新

## 执行流程

### 步骤 1: 采集热门仓库
- 方式一（推荐）：运行 `python scripts/scrape_github_trending.py`
- 方式二：使用 WebFetch 直接抓取 https://github.com/trending 并解析 HTML
- 为每个仓库提取以下信息：

| 字段 | 说明 | 提取方式 |
|------|------|----------|
| name | 仓库名称，格式 owner/repo | `article.select_one("h2 a")` 的 href |
| url | 完整 GitHub 仓库 URL | 拼接 `https://github.com/{name}` |
| description | 项目原始描述 | `article.select_one("p")` 的文本 |
| stars | 当前 star 总数 | `[href$='stargazers']` 元素解析数字 |
| language | 主要编程语言 | `[itemprop='programmingLanguage']` 等备选选择器 |
| topics | 主题标签列表 | 多选择器降级 + 描述关键词回退（见步骤 2） |

### 步骤 2: 内容过滤

**纳入标准**（符合任意一项）：
- 仓库 topics 命中 TARGET_TOPICS 集合（23 个词：ai, llm, agent, ml, machine-learning, large-language-model, generative-ai, deeplearning, deep-learning, transformer, rlhf, reinforcement-learning, nlp, neural-network, artificial-intelligence, language-model, openai, anthropic, claude, chatgpt, gpt, huggingface, transformers）
- 项目描述命中 DESC_KEYWORDS（ai, llm, agent, machine learning, neural, deep learning, nlp, language model, ml）

**排除标准**（符合任意一项）：
- 仓库名称或描述含以下模式：awesome-、curated list、book、course、tutorial、roadmap、interview、cheatsheet

**Topics 提取降级策略**：
1. 依次尝试 CSS 选择器：`a.topic-tag` → `a[data-ga-click*='topic']` → `a[href*='topics']` → `div.tags a` → `span.Label--topic`
2. 若均未命中，从 description 中匹配 TARGET_TOPICS 关键词（最多 5 个）

### 步骤 3: 去重处理
- 基于仓库 URL 去重
- 检查 `knowledge/raw/` 是否已有当日数据文件，避免重复采集

### 步骤 4: 排序与输出
- 按 star 数降序排列，取 Top 15
- summary 字段留空，由下游 Analyzer Agent 生成中文摘要
- 保存到 `knowledge/raw/github-trending-YYYY-MM-DD.json`

## 输出格式

**文件命名**：`knowledge/raw/github-trending-YYYY-MM-DD.json`
**编码**：UTF-8，2 空格缩进，ensure_ascii=False

```json
{
  "source": "github",
  "skill": "github-trending",
  "collected_at": "2026-04-18T10:00:00Z",
  "items": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "summary": "",
      "stars": 1234,
      "language": "Python",
      "topics": ["ai", "llm"]
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| source | string | 是 | 固定值 "github" |
| skill | string | 是 | 固定值 "github-trending" |
| collected_at | string | 是 | ISO 8601 采集时间戳 |
| items | array | 是 | 最多 15 个条目 |
| items[].name | string | 是 | owner/repo 格式 |
| items[].url | string | 是 | 完整 GitHub 仓库 URL |
| items[].summary | string | 是 | 留空，由下游 Analyzer 填充 |
| items[].stars | integer | 是 | 当前 star 总数 |
| items[].language | string | 否 | 主要编程语言，可能为空字符串 |
| items[].topics | array | 是 | 主题标签列表，英文小写 |

## 错误处理
- 网络错误（RequestException）/ 解析错误（ValueError, TypeError）/ 未知错误：分类记录到 stderr
- 失败时返回空数组，不抛异常
- 单次执行 < 10 秒（超过 9.5s 返回空数组）
- 单个项目解析失败跳过，不影响整体流程
- 使用 HTML 解析，不依赖 GitHub API（避免 rate limit）

## 质量检查清单
- [ ] 条目数量 ≤ 15，均为 AI/LLM/Agent 相关
- [ ] 所有必填字段无缺失
- [ ] summary 字段为空字符串（非 null）
- [ ] 按 star 数降序排列
- [ ] JSON 格式正确，UTF-8 编码，2 空格缩进
- [ ] collected_at 为有效 ISO 8601 时间戳

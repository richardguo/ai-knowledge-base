# skill: github-trending · 需求规格

## 功能概述

采集 GitHub Trending 热门开源项目，过滤 AI/LLM/Agent/ML 相关仓库，输出结构化 JSON 并自动保存到 `knowledge/raw/`。

## 要做什么

### 数据采集
- 抓取 https://github.com/trending 页面（HTML 解析，不调 GitHub API）
- 解析全部 trending 仓库条目
- 为每个仓库提取以下信息：

| 字段 | 说明 | 提取方式 |
|------|------|----------|
| name | 仓库名称，格式 owner/repo | `article.select_one("h2 a")` 的 href |
| url | 完整 GitHub 仓库 URL | 拼接 `https://github.com/{name}` |
| description | 项目原始描述 | `article.select_one("p")` 的文本 |
| stars | 当前 star 总数 | `[href$='stargazers']` 元素解析数字 |
| language | 主要编程语言 | `[itemprop='programmingLanguage']` 等备选选择器 |
| topics | 主题标签列表 | 多选择器降级 + 描述关键词回退（见 Topics 提取策略） |

### 内容过滤

**纳入标准**（符合任意一项即保留）：
- 仓库 topics 命中 TARGET_TOPICS 集合
- 项目描述命中 DESC_KEYWORDS 关键词

**排除标准**（符合任意一项即丢弃）：
- 仓库名称或描述含 EXCLUDE_PATTERNS 中的模式（awesome-、curated list、book、course、tutorial、roadmap、interview、cheatsheet）

### 关键词扩展

TARGET_TOPICS 包含 23 个扩展词，覆盖主词及变体：
```
ai, llm, agent, ml, machine-learning, large-language-model,
generative-ai, deeplearning, deep-learning, transformer,
rlhf, reinforcement-learning, nlp, neural-network,
artificial-intelligence, language-model, openai, anthropic,
claude, chatgpt, gpt, huggingface, transformers
```

DESC_KEYWORDS 用于描述文本匹配：
```
ai, llm, agent, machine learning, neural,
deep learning, nlp, language model, ml
```

### Topics 提取策略

1. 依次尝试多个 CSS 选择器：`a.topic-tag` → `a[data-ga-click*='topic']` → `a[href*='topics']` → `div.tags a` → `span.Label--topic`
2. 若均未命中，则从 description 中提取 TARGET_TOPICS 匹配词（最多 5 个）

### 排序与截取
- 按 star 数降序排列
- 取 Top 15 条目

### 去重
- 基于仓库 URL 去重
- 检查 `knowledge/raw/` 是否已有当日数据文件，避免重复采集

### 输出
- 自动保存到 `knowledge/raw/github-trending-YYYY-MM-DD.json`（详见文件命名规范）
- 同时输出到 stdout

## 不做什么
- 不调 GitHub API（rate limit 太紧）· 走 HTML 解析
- 不存数据库
- 不做中文摘要生成（summary 字段留空，由下游 Agent 处理）

## 输出格式

```json
{
  "source": "github",
  "skill": "github-trending",
  "collected_at": "2026-04-18T03:49:08Z",
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
| items[].summary | string | 是 | 留空，由下游 Analyzer Agent 填充 |
| items[].stars | integer | 是 | 当前 star 总数 |
| items[].language | string | 否 | 主要编程语言，可能为空字符串 |
| items[].topics | array | 是 | 主题标签列表，英文小写 |

### 文件命名规范
- **路径**：`knowledge/raw/github-trending-YYYY-MM-DD.json`
- **示例**：`knowledge/raw/github-trending-2026-04-18.json`
- **编码**：UTF-8，2 空格缩进，ensure_ascii=False

## 边界 & 验收

- 单次执行 < 10s（超过 9.5s 返回空数组）
- 失败时返回空数组，不抛异常
- 错误分类：网络错误（RequestException）、解析错误（ValueError/TypeError）、未知错误
- 单个项目解析失败跳过，不影响整体流程
- GitHub HTML 结构变化时，通过多备选 CSS 选择器容错

## 怎么验证

```bash
# 方式一：直接运行脚本
python .opencode/skills/github-trending/scripts/scrape_github_trending.py

# 方式二：通过 Agent 调用
@collector 采集今天的 GitHub Trending 数据
```

验证项：
- 输出是合法 JSON 且 items 数组字段完整
- 文件已保存到 `knowledge/raw/github-trending-YYYY-MM-DD.json`
- 执行时间 < 10s
- 条目均为 AI/LLM/Agent 相关，无非技术内容

## 实现文件

| 文件 | 说明 |
|------|------|
| `.opencode/skills/github-trending/SKILL.md` | 技能定义 |
| `.opencode/skills/github-trending/scripts/scrape_github_trending.py` | 采集脚本 |

# Skill: github-collector · 需求规格 v2.0

## 功能概述

采集 GitHub 热门 AI/LLM/Agent 仓库并输出结构化 JSON。支持两种数据源：
- **GitHub Search API**: 搜索过去 7 天活跃的相关仓库
- **GitHub Trending 页面**: 抓取当日/周/月热门项目

## 数据源

### A. GitHub Search API

#### 搜索参数
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--keywords` | AI,LLM,agent,large language model,Harness,SDD,RAG,machine learning | 搜索关键词，逗号分隔 |
| `--top` | 20 | 取 Top N 项目，最大 50 |
| `--output-dir` | knowledge/raw | 输出目录 |
| `--resume_run` | False | 断点续传 |

#### 搜索逻辑
- 时间窗口：过去 7 天内有推送（`pushed:>` 过滤）
- 排序：按总 star 数降序（`sort=stars&order=desc`）
- 过滤：不做二次内容过滤，留给下游 Analyzer

#### 执行流程
1. 构建 GitHub Search API 查询
2. 调用 API 获取仓库列表
3. 对每个仓库调用 `/repos/{owner}/{repo}/readme` 获取 README（截断到 5000 字符）
4. 输出最终文件，包含 `description`、`readme` 和空的 `summary` 字段

### B. GitHub Trending 页面

#### 搜索参数
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--since` | daily | 时间范围：daily/weekly/monthly |
| `--top` | 20 | 取 Top N 项目，最大 30 |
| `--output-dir` | knowledge/raw | 输出目录 |
| `--resume_run` | False | 断点续传 |

#### 抓取逻辑
- 使用 Playwright 无头浏览器渲染页面
- 自动点击 Load more 按钮加载更多条目（最多 5 次）
- 保持 Trending 页面原始顺序

#### 内容过滤

**纳入标准**（符合任意一项）：
- 仓库 topics 命中 TARGET_TOPICS 集合
- 项目描述命中 DESC_KEYWORDS 关键词

**排除标准**（符合任意一项）：
- 仓库名称或描述含：awesome-、curated list、book、course、roadmap、interview、cheatsheet

#### 执行流程
1. Playwright 抓取 Trending 页面 HTML
2. 解析 HTML 提取基本信息（title, url, description, language, topics, star 增长数）
3. 应用内容过滤
4. 对每个通过过滤的项目调用 GitHub API 补全缺失字段：
   - `/repos/{owner}/{repo}` 获取 created_at, updated_at, topics
   - `/repos/{owner}/{repo}/readme` 获取 README（截断到 5000 字符）
5. 输出最终文件，包含 `description`、`readme` 和空的 `summary` 字段

## 关键词配置

### TARGET_TOPICS (23 个)
```
ai, llm, agent, ml, machine-learning, large-language-model,
generative-ai, deeplearning, deep-learning, transformer,
rlhf, reinforcement-learning, nlp, neural-network,
artificial-intelligence, language-model, openai, anthropic,
claude, chatgpt, gpt, huggingface, transformers
```

### DESC_KEYWORDS (8 个)
```
ai, llm, agent, machine learning,
deep learning, nlp, language model, ml
```

### EXCLUDE_PATTERNS (7 个)
```
awesome-, curated list, book, course, roadmap,
interview, cheatsheet
```

## 输出文件格式

### Search 文件格式 (`github-search-{YYYY-MM-DD-HHMMSS}.json`)
```json
{
  "collected_at": "2026-04-17T10:00:00+08:00",
  "source": "github-search",
  "version": "1.0",
  "items": [
    {
      "title": "项目名称",
      "url": "https://github.com/owner/repo",
      "popularity": 1234,
      "popularity_type": "total_stars",
      "author": "owner",
      "created_at": "2026-04-17T01:56:15+08:00",
      "updated_at": "2026-04-20T05:27:45+08:00",
      "language": "Python",
      "topics": ["ai", "ml", "pytorch"],
      "description": "项目描述原文",
      "readme": "README 内容（截断到 5000 字符）",
      "summary": ""
    }
  ]
}
```

### Trending 文件格式 (`github-trending-{YYYY-MM-DD-HHMMSS}.json`)
```json
{
  "collected_at": "2026-04-17T10:00:00+08:00",
  "source": "github-trending",
  "version": "1.0",
  "since": "daily",
  "items": [
    {
      "title": "项目名称",
      "url": "https://github.com/owner/repo",
      "popularity": 123,
      "popularity_type": "daily_stars",
      "author": "owner",
      "created_at": "2026-04-17T01:56:15+08:00",
      "updated_at": "2026-04-20T05:27:45+08:00",
      "language": "Python",
      "topics": ["ai", "agent"],
      "description": "项目描述原文",
      "readme": "README 内容（截断到 5000 字符）",
      "summary": ""
    }
  ]
}
```

## 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string | 是 | 项目名称（repo 名） |
| url | string | 是 | GitHub 仓库地址 |
| popularity | integer | 是 | 热度数值，含义由 `popularity_type` 决定 |
| popularity_type | string | 是 | `total_stars`（Search）或 `daily_stars`/`weekly_stars`/`monthly_stars`（Trending） |
| author | string | 是 | 项目发布者或组织 |
| created_at | string | 是 | 项目创建时间，ISO 8601 +08:00 |
| updated_at | string | 是 | 最近推送时间，ISO 8601 +08:00 |
| language | string | 是 | 主要编程语言，无则为 `"N/A"` |
| topics | array | 是 | 仓库标签列表，可为空数组 |
| description | string | 是 | 项目描述原文，可为空字符串 |
| readme | string | 是 | README 内容，截断到 5000 字符，可为空字符串 |
| summary | string | 是 | 留空，由 Analyzer 基于原始内容生成中文摘要 |

## 状态文件格式

```json
{
  "agent": "collector",
  "task_id": "{YYYY-MM-DD-HHMMSS}-uuidv4",
  "status": "started|running|completed|failed",
  "sources": ["github-search"],
  "output_files": ["knowledge/raw/github-search-{YYYY-MM-DD-HHMMSS}.json"],
  "quality": "ok|below_threshold",
  "error_count": 0,
  "start_time": "2026-04-17T10:00:00+08:00",
  "raw_items_url": [],
  "end_time": "2026-04-17T10:05:00+08:00"
}
```

### 质量判定
- Search: 条目数 ≥ 15 → `ok`，否则 `below_threshold`
- Trending: 条目数 ≥ 10 → `ok`，否则 `below_threshold`

## 运行命令

```bash
# 激活环境
D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat
chcp 65001

# GitHub Search
python .opencode/skills/github-collector/scripts/github_search.py --top 20

# GitHub Trending
python .opencode/skills/github-collector/scripts/github_trending.py --since daily --top 20

# 自定义关键词
python .opencode/skills/github-collector/scripts/github_search.py --keywords "RAG,retrieval,augmented generation"

# 断点续传
python .opencode/skills/github-collector/scripts/github_trending.py --resume_run
```

## 错误处理

| 错误类型 | 处理方式 |
|----------|----------|
| GITHUB_TOKEN 缺失 | 脚本报错退出（退出码 1），提示用户配置 |
| 网络错误 | 自动重试 3 次，指数退避 |
| API 限流 | 检测 HTTP 429，计算等待时间后重试 |
| 单个项目解析失败 | 跳过该项目，记录错误日志，继续处理其他项目 |
| 输出文件写入失败 | 记录错误并退出 |

## 实现文件

| 文件 | 说明 |
|------|------|
| `.opencode/skills/github-collector/SKILL.md` | 技能定义 |
| `.opencode/skills/github-collector/scripts/common.py` | 公共模块（配置、工具函数） |
| `.opencode/skills/github-collector/scripts/github_search.py` | Search API 采集脚本 |
| `.opencode/skills/github-collector/scripts/github_trending.py` | Trending 页面采集脚本 |

---
*规格版本: v2.0*
*最后更新: 2026-04-21*
*适用场景: GitHub 仓库搜索 + Trending 页面采集*

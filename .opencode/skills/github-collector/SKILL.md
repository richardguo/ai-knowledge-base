---
name: github-collector
description: |
  采集 GitHub 热门 AI/LLM/Agent 仓库并输出结构化 JSON。支持两种数据源：
  GitHub Trending 页面和 GitHub Search API。当用户提到
  GitHub Trending、GitHub 搜索、热门 AI 项目、trending repos、
  最新 agent 框架、开源情报采集、技术趋势时触发。
allowed-tools: [Bash, Read, Grep, Glob, Write]
---

# GitHub Collector 采集技能

## 使用场景

- 每日技术情报收集
- AI 技术趋势分析
- 开源项目发现与评估
- 知识库数据源更新

## 环境准备

### Python 环境
- **版本**: Python 3.12
- **激活命令**:
  - Windows: `D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat`
  - Linux: `source D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate`

### 依赖库
- requests
- beautifulsoup4
- python-dotenv
- playwright

### 环境变量
需在 `.env` 中配置：
- `GITHUB_TOKEN`: GitHub API 认证令牌（必须）

### Windows 编码
执行脚本前先运行：
```bash
chcp 65001
```

## 执行流程

### A. GitHub 仓库搜索

```bash
python .opencode/skills/github-collector/scripts/github_search.py --output-dir knowledge/raw --top 20
```

参数说明：
| 参数 | 必填 | 说明 |
|------|------|------|
| `--output-dir` | 否 | 输出目录，默认 `knowledge/raw` |
| `--top` | 否 | 取 Top N 项目，默认 20，最大 50 |
| `--keywords` | 否 | 搜索关键词，逗号分隔，默认 `AI,LLM,agent,large language model,Harness,SDD,RAG,machine learning` |
| `--resume_run` | 否 | 继续未完成的任务，从断点续传 |

脚本实现细节：
- 调用 GitHub Search API (`https://api.github.com/search/repositories`)
- 搜索关键词：默认为 AI/LLM/agent 等，可通过 `--keywords` 自定义
- 时间窗口：过去 7 天内有推送（`pushed:>` 过滤）
- 按 `sort=stars&order=desc` 排序
- 对每个项目获取 README 内容（GitHub API `/repos/{owner}/{repo}/readme`）
- 从 `.env` 读取 `GITHUB_TOKEN` 用于 API 认证
- 输出最终文件 `github-search-{YYYY-MM-DD-HHMMSS}.json`，包含 `description`、`readme` 和空的 `summary` 字段

**自定义搜索关键词示例**：
```bash
# 搜索 RAG 相关项目
python .opencode/skills/github-collector/scripts/github_search.py --keywords "RAG,retrieval,augmented generation"

# 搜索 Agent 框架
python .opencode/skills/github-collector/scripts/github_search.py --keywords "agent framework,autonomous,AI agent"
```

### B. GitHub Trending 页面

```bash
python .opencode/skills/github-collector/scripts/github_trending.py --since daily --output-dir knowledge/raw --top 20
```

参数说明：
| 参数 | 必填 | 说明 |
|------|------|------|
| `--since` | 否 | 时间范围：`daily`（默认）、`weekly`、`monthly`。Agent 根据用户指令决定传值 |
| `--output-dir` | 否 | 输出目录，默认 `knowledge/raw` |
| `--top` | 否 | 取 Top N 项目，默认 20，最大 30 |

脚本实现细节：
- 使用 Playwright 无头浏览器渲染 GitHub Trending 页面，确保 JS 动态内容完整加载
- 自动点击 Load more 按钮加载更多条目（最多 5 次），直到条目数满足 --top 需求
- 页面 URL：`https://github.com/trending?since={daily|weekly|monthly}`
- 保持 Trending 页面原始顺序
- 对每个项目调用 GitHub API 补全缺失字段：
  - 调用 `/repos/{owner}/{repo}` 一次，同时获取 `created_at`、`updated_at`、`topics`
  - 调用 `/repos/{owner}/{repo}/readme` 获取 README 内容
- 从 `.env` 读取 `GITHUB_TOKEN` 用于 API 认证
- 输出最终文件 `github-trending-{YYYY-MM-DD-HHMMSS}.json`，包含 `description`、`readme` 和空的 `summary` 字段

内容过滤配置：
- **纳入标准**（符合任意一项）：
  - 仓库 topics 命中目标集合（ai, llm, agent, ml, machine-learning, large-language-model, generative-ai, deeplearning, deep-learning, transformer, rlhf, reinforcement-learning, nlp, neural-network, artificial-intelligence, language-model, openai, anthropic, claude, chatgpt, gpt, huggingface, transformers）
  - 项目描述命中关键词（ai, llm, agent, machine learning, deep learning, nlp, language model, ml）
- **排除标准**（符合任意一项）：
  - 仓库名称或描述含：awesome-、curated list、book、course、roadmap、interview、cheatsheet

## 输出文件格式

### 仓库搜索文件格式 (`github-search-{YYYY-MM-DD-HHMMSS}.json`)
```json
{
  "collected_at": "2026-04-17T10:00:00+08:00",
  "source": "github-search",
  "version": "1.0",
  "items": [
    {
      "title": "pytorch",
      "url": "https://github.com/pytorch/pytorch",
      "popularity": 1234,
      "popularity_type": "total_stars",
      "author": "pytorch",
      "created_at": "2026-04-17T01:56:15+08:00",
      "updated_at": "2026-04-20T05:27:45+08:00",
      "language": "Python",
      "topics": ["ai", "ml", "pytorch"],
      "description": "API 返回的 description 原文",
      "readme": "README 原文内容",
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
      "title": "pytorch",
      "url": "https://github.com/pytorch/pytorch",
      "popularity": 123,
      "popularity_type": "daily_stars",
      "author": "pytorch",
      "created_at": "2026-04-17T01:56:15+08:00",
      "updated_at": "2026-04-20T05:27:45+08:00",
      "language": "Python",
      "topics": ["ai", "agent"],
      "description": "页面 description 原文",
      "readme": "README 原文内容",
      "summary": ""
    }
  ]
}
```

## 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| title | string | 项目名称（repo 名） |
| url | string | GitHub 仓库地址 |
| popularity | integer | 热度数值，含义由 `popularity_type` 决定 |
| popularity_type | string | `total_stars`（搜索）或 `daily_stars`/`weekly_stars`/`monthly_stars`（Trending） |
| author | string | 项目发布者或组织 |
| created_at | string | 项目创建时间，ISO 8601 +08:00 |
| updated_at | string | 最近推送时间，ISO 8601 +08:00 |
| language | string | 主要编程语言，无则为 `"N/A"` |
| topics | array | 仓库标签列表，可为空数组 |
| description | string | 项目描述原文，可为空字符串 |
| readme | string | README 内容，截断到 5000 字符，可为空字符串 |
| summary | string | 留空，由 Analyzer 基于原始内容生成中文摘要 |

## 脚本错误处理

- **网络错误**: 自动重试 3 次，指数退避
- **API 限流**: 检测 HTTP 429，计算等待时间后重试
- **数据解析错误**: 跳过该项目，记录错误到 stderr，继续处理其他项目
- **HTML 解析错误**: Trending 页面结构变化导致解析失败，跳过该项目
- **GITHUB_TOKEN 缺失**: 脚本报错退出，Agent 需提示用户配置

---
*技能版本: v2.3*
*最后更新: 2026-04-21*
*适用场景: GitHub 仓库搜索 + Trending 页面采集*

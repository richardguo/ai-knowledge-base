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

运行脚本前必须激活 Python 环境：

**Windows**:
```bash
D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat
```

**Linux**:
```bash
source D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate
```

## 执行流程

### A. GitHub 仓库搜索

#### 步骤 1: 运行采集脚本

```bash
python .opencode/skills/github-collector/scripts/github_search.py --output-dir knowledge/raw --top 50
```

参数说明：
| 参数 | 必填 | 说明 |
|------|------|------|
| `--output-dir` | 否 | 输出目录，默认 `knowledge/raw` |
| `--top` | 否 | 取 Top N 项目，默认 50 |

脚本功能：
- 调用 GitHub Search API (`https://api.github.com/search/repositories`)
- 搜索关键词：`AI OR LLM OR agent OR "large language model" OR Harness OR SDD OR RAG OR "machine learning"`
- 时间窗口：过去 7 天内有推送
- 按 `sort=stars&order=desc` 排序
- 对每个项目获取 README 内容（GitHub API `/repos/{owner}/{repo}/readme`）
- 从 `.env` 读取 `GITHUB_TOKEN` 用于 API 认证
- 输出中间文件 `github-search-{YYYY-MM-DD-HHMMSS}-raw.json`

脚本输出字段：
| 字段 | 类型 | 说明 |
|------|------|------|
| title | string | 项目名称（repo 名，如 `pytorch`） |
| url | string | GitHub 仓库地址 |
| popularity | integer | 总 star 数 |
| popularity_type | string | 固定值 `"total_stars"` |
| author | string | 项目发布者或组织 |
| created_at | string | 项目创建时间，ISO 8601 +08:00 |
| updated_at | string | 最近推送时间，ISO 8601 +08:00 |
| language | string | 主要编程语言，无则为 `"N/A"` |
| topics | array | 仓库标签列表，可为空 |
| summary | string | API 返回的 description 原文 |
| readme | string | README 原文内容 |

#### 步骤 2: Agent 生成中文摘要

1. 读取中间文件 `github-search-{YYYY-MM-DD-HHMMSS}-raw.json`
2. 对每个项目，基于 `summary`（description）和 `readme` 内容生成 50-200 字中文摘要
3. 移除 `readme` 字段
4. 写入最终文件 `github-search-{YYYY-MM-DD-HHMMSS}.json`
5. 中间文件 `-raw.json` 保留不删除

### B. GitHub Trending 页面

#### 步骤 1: 运行采集脚本

```bash
python .opencode/skills/github-collector/scripts/github_trending.py --since daily --output-dir knowledge/raw --top 20
```

参数说明：
| 参数 | 必填 | 说明 |
|------|------|------|
| `--since` | 否 | 时间范围：`daily`（默认）、`weekly`、`monthly`。Agent 根据用户指令决定传值 |
| `--output-dir` | 否 | 输出目录，默认 `knowledge/raw` |
| `--top` | 否 | 取 Top N 项目，默认值随 `--since` 变化：daily=20, weekly=25, monthly=30 |

脚本功能：
- 抓取 GitHub Trending 页面 HTML 并解析项目列表
- 根据 `--since` 参数决定页面 URL（`https://github.com/trending?since={daily|weekly|monthly}`）
- 保持 Trending 页面原始顺序（即每日/周/月 star 增长数降序）
- 对每个项目调用 GitHub API 补全缺失字段：
  - 调用 `/repos/{owner}/{repo}` 一次，同时获取 `created_at`、`updated_at`、`topics`
  - 调用 `/repos/{owner}/{repo}/readme` 获取 README 内容
- 从 `.env` 读取 `GITHUB_TOKEN` 用于 API 认证
- 输出中间文件 `github-trending-{YYYY-MM-DD-HHMMSS}-raw.json`

内容过滤：
- **纳入标准**（符合任意一项）：
  - 仓库 topics 命中目标集合（ai, llm, agent, ml, machine-learning, large-language-model, generative-ai, deeplearning, deep-learning, transformer, rlhf, reinforcement-learning, nlp, neural-network, artificial-intelligence, language-model, openai, anthropic, claude, chatgpt, gpt, huggingface, transformers）
  - 项目描述命中关键词（ai, llm, agent, machine learning, deep learning, nlp, language model, ml）
- **排除标准**（符合任意一项）：
  - 仓库名称或描述含：awesome-、curated list、book、course、roadmap、interview、cheatsheet

脚本输出字段：
| 字段 | 类型 | 说明 |
|------|------|------|
| title | string | 项目名称（repo 名，如 `pytorch`） |
| url | string | GitHub 仓库地址 |
| popularity | integer | 今日/本周/本月 star 增长数 |
| popularity_type | string | `"daily_stars"` / `"weekly_stars"` / `"monthly_stars"`（与 `--since` 对应） |
| author | string | 项目发布者或组织 |
| created_at | string | 项目创建时间，ISO 8601 +08:00 |
| updated_at | string | 最近推送时间，ISO 8601 +08:00 |
| language | string | 主要编程语言，无则为 `"N/A"` |
| topics | array | 仓库标签列表，可为空 |
| summary | string | 页面 description 原文 |
| readme | string | README 原文内容 |

#### 步骤 2: Agent 生成中文摘要

1. 读取中间文件 `github-trending-{YYYY-MM-DD-HHMMSS}-raw.json`
2. 对每个项目，基于 `summary`（description）和 `readme` 内容生成 50-200 字中文摘要
3. 移除 `readme` 字段
4. 写入最终文件 `github-trending-{YYYY-MM-DD-HHMMSS}.json`
5. 中间文件 `-raw.json` 保留不删除

### 状态管理

Agent 在整个采集过程中维护状态文件：

- **任务开始**: 写入 `knowledge/processed/collector-{YYYY-MM-DD-HHMMSS}-status.json`（status=started）
- **每个脚本完成**: 更新状态文件（status=running），将已采集项目 URL 添加到 `raw_items_url`
- **全部完成**: 更新状态文件（status=completed）
- **错误时**: 写入 `knowledge/processed/collector-{YYYY-MM-DD-HHMMSS}-failed.json`

## 输出格式

### 仓库搜索 - 中间文件 (`github-search-{YYYY-MM-DD-HHMMSS}-raw.json`)
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
      "summary": "API 返回的 description 原文",
      "readme": "README 原文内容"
    }
  ]
}
```

### 仓库搜索 - 最终文件 (`github-search-{YYYY-MM-DD-HHMMSS}.json`)
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
      "summary": "50-200字中文摘要，基于项目描述和README内容。"
    }
  ]
}
```

### Trending - 中间文件 (`github-trending-{YYYY-MM-DD-HHMMSS}-raw.json`)
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
      "summary": "页面 description 原文",
      "readme": "README 原文内容"
    }
  ]
}
```

### Trending - 最终文件 (`github-trending-{YYYY-MM-DD-HHMMSS}.json`)
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
      "summary": "50-200字中文摘要，基于项目描述和README内容。"
    }
  ]
}
```

### 状态文件 (`knowledge/processed/collector-{YYYY-MM-DD-HHMMSS}-status.json`)
```json
{
  "agent": "collector",
  "task_id": "{YYYY-MM-DD-HHMMSS}-uuidv4",
  "status": "started|running|completed|failed",
  "sources": ["github-search", "github-trending"],
  "output_files": [
    "knowledge/raw/github-search-{YYYY-MM-DD-HHMMSS}.json",
    "knowledge/raw/github-trending-{YYYY-MM-DD-HHMMSS}.json"
  ],
  "error_count": 0,
  "start_time": "2026-04-17T10:00:00+08:00",
  "raw_items_url": [],
  "end_time": "2026-04-17T10:05:00+08:00"
}
```

## 错误处理

### 脚本层面
- **网络错误**: 自动重试 3 次，指数退避
- **API 限流**: 检测 HTTP 429，计算等待时间后重试
- **数据解析错误**: 跳过该项目，记录错误到 stderr，继续处理其他项目
- **HTML 解析错误**: Trending 页面结构变化导致解析失败，跳过该项目
- **GITHUB_TOKEN 缺失**: 脚本报错退出，Agent 需提示用户配置

### Agent 层面
- **脚本执行失败**: 在错误信息前添加 ❌ 标记醒目提示用户
- **摘要生成失败**: 跳过该项目，保留 description 原文作为 summary
- **存储错误**: 记录到错误日志，❌ 标记提示用户，退出

## 质量检查清单

- [ ] 条目数量：仓库搜索 ≥ 15，Trending ≥ 10（低于门槛标记不达标但不阻断）
- [ ] 所有必填字段（title, url, popularity, popularity_type, author, created_at, updated_at, language, topics, summary）完整无缺失
- [ ] 摘要 50-200 字，基于原始内容，无编造成分
- [ ] 排序正确：仓库搜索按总 star 数降序，Trending 按页面原始顺序
- [ ] 时间格式统一 ISO 8601 +08:00
- [ ] JSON 格式正确，UTF-8 编码，2 空格缩进
- [ ] 中间文件 `-raw.json` 保留，最终文件不含 `readme` 字段

---
*技能版本: v2.0*
*最后更新: 2026-04-20*
*适用场景: GitHub 仓库搜索 + Trending 页面采集*

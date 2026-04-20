# AI 知识库助手

自动化技术情报收集与分析系统。基于 GitHub Trending、Hacker News 等开源情报源，通过多 Agent 协作将分散的技术资讯转化为结构化、可检索的知识条目。

## 架构概览

```
[Collector] ──采集──→ knowledge/raw/
                          │
[Analyzer]  ──分析──→ knowledge/processed/
                          │
[Organizer] ──整理──→ knowledge/articles/
```

三阶段流水线，单向数据流，每个 Agent 职责隔离、幂等运行。

## 技术栈

| 组件 | 选型 |
|------|------|
| 运行时 | OpenCode + LLM (DeepSeek / Qwen / GLM) |
| 数据源 | GitHub Trending (HTML 解析)、Hacker News API |
| 输出格式 | JSON (UTF-8, 2 空格缩进) |
| 语言 | Python 3.12 |
| 版本管理 | Git |

## 项目结构

```
ai-knowledge-base/
├── AGENTS.md                              # 项目记忆与编码规范
├── .opencode/
│   ├── agents/
│   │   ├── collector.md                   # 采集 Agent 角色定义
│   │   ├── analyzer.md                    # 分析 Agent 角色定义
│   │   └── organizer.md                   # 整理 Agent 角色定义
│   └── skills/
│       ├── github-trending/               # GitHub Trending 采集技能
│       │   ├── SKILL.md
│       │   └── scripts/scrape_github_trending.py
│       └── tech-summary/                  # 技术摘要分析技能
│           └── SKILL.md
├── knowledge/
│   ├── raw/                               # 原始采集数据
│   ├── processed/                         # 分析中间结果
│   └── articles/                          # 最终知识条目
├── utils/                                 # 工具脚本
├── specs/                                 # 设计规格文档
└── tests/                                 # 测试
```

## 三阶段流水线

### Collector — 采集

从 GitHub Trending 抓取 Top 50 项目，过滤 AI/LLM/Agent 相关仓库，输出到 `knowledge/raw/`。

```bash
# 方式一：运行采集脚本
python .opencode/skills/github-trending/scripts/github_trending.py

# 方式二：通过 Agent 调用
@collector 采集今天的 GitHub Trending 数据
```

### Analyzer — 分析

深度解析采集数据，生成 200-300 字技术摘要、核心亮点、质量评分 (1-10) 和技术标签，输出到 `knowledge/processed/`。

```bash
@analyzer 分析 knowledge/raw/github-trending-2026-04-18.json
```

### Organizer — 整理

将分析结果标准化为知识条目，生成 JSON + Markdown 双格式，建立索引，输出到 `knowledge/articles/`。评分低于 6 的条目自动丢弃。

```bash
@organizer 整理今天所有已分析的原始数据
```

## 输出格式

### 原始采集数据 (`knowledge/raw/`)

```json
{
  "source": "github",
  "skill": "github-trending",
  "collected_at": "2026-04-18T10:00:00Z",
  "items": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "summary": "50-100字中文技术摘要",
      "stars": 1234,
      "language": "Python",
      "topics": ["ai", "llm"]
    }
  ]
}
```

### 最终知识条目 (`knowledge/articles/`)

```json
{
  "id": "uuidv4",
  "title": "项目标题",
  "url": "https://github.com/owner/repo",
  "source": "github",
  "collected_at": "2026-04-18T10:00:00Z",
  "processed_at": "2026-04-18T10:45:00Z",
  "summary": "200-300字中文技术摘要",
  "highlights": ["核心亮点1", "核心亮点2"],
  "relevance_score": 7,
  "tags": ["agent-framework"],
  "category": "框架",
  "maturity": "生产"
}
```

## 快速开始

### 环境准备

```bash
# 激活 Python 环境
D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat

# Windows 下设置 UTF-8 编码
chcp 65001
```

### 运行完整流水线

```bash
# 1. 采集
python .opencode/skills/github-trending/scripts/github_trending.py

# 2. 分析（通过 Agent 调用）
@analyzer 分析 knowledge/raw/github-trending-YYYY-MM-DD.json

# 3. 整理（通过 Agent 调用）
@organizer 整理今天所有已分析的原始数据
```

## Agent 协作规则

1. **单向数据流**：Collector → Analyzer → Organizer，不可反向
2. **职责隔离**：每个 Agent 只操作自己权限范围内的目录
3. **幂等性**：重复运行同一天的采集不产生重复条目
4. **质量门控**：评分低于 6 的条目自动丢弃
5. **可追溯**：每个条目保留 `url` 和 `collected_at` 用于溯源

## 编码规范

- PEP 8 + black 格式化
- 全量类型注解
- snake_case 命名
- Google 风格 docstring
- 测试覆盖率 ≥ 80%

详见 [AGENTS.md](AGENTS.md)。

## 许可证

MIT

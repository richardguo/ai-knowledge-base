# AI知识库助手

## 项目概述
AI知识库助手是一个自动化技术情报收集与分析系统。
基于 GitHub Search API 和 GitHub Trending 等开源情报，将分散的技术资讯转化为结构化、可检索的知识条目。

### 项目细节
- 每日自动采集的AI/LLM/Agent相关的技术动态（GitHub Search + GitHub Trending 双数据源）
- 通过多Agent协作完成 **采集 → 分析 → 整理** 三阶段流水线
- 每个 Agent 通过专属 Skill 的 Python 脚本执行，禁止 LLM 自行逐条处理
- 输出格式为统一的 JSON 知识条目，便于下游应用消费

## 技术栈
- **运行时**：OpenCode + LLM（DeepSeek / Qwen / GLM）
- **数据源**：GitHub API v3
- **输出格式**：JSON
- **版本管理**：Git
- Python 3.12

## Python环境
- 运行python时，始终激活指定的环境 (已安装Langgraph): 
  D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat
- Python 默认从项目根目录运行


## Windows平台注意事项
- **中文编码处理**: 在Windows平台的cmd中运行任何脚本前，先执行 `chcp 65001` 命令，将控制台代码页设置为UTF-8，避免中文输出乱码。

## 编码规范

### 核心原则
1. 严格遵循 PEP 8 规范
2. 全量类型注解（Type Hints）
3. snake_case 命名规则
4. Google 风格 docstring
5. 禁止使用裸 print()

### 新增规范
6. Python 代码使用 black 格式化（所有文件）
7. TypeScript 启用 strict 模式（允许特定情况使用 `any`）
8. 禁止使用魔法字符串（配置项除外）
9. 禁止提交 TODO/FIXME 注释到 main 分支

### 质量保证
10. 单元测试覆盖率 ≥80%（使用 pytest-cov 收集）
11. 所有公开函数/类方法必须包含文档：
    - 功能简介
    - 参数说明
    - 返回值
    - 异常说明
12. 使用静态分析工具验证文档完整性

### 工具链
13. Lint 工具：
    - Python: pylint + black
    - TypeScript: ESLint + Prettier
14. 本地执行测试命令：`pytest --cov=src tests/`

### 文件命名
- 原始数据最终文件：`knowledge/raw/{source}-{YYYY-MM-DD-HHMMSS}.json`
  - 例：`knowledge/raw/github-search-2026-04-20-100000.json`
  - 例：`knowledge/raw/github-trending-2026-04-20-100000.json`
- 知识条目：`knowledge/articles/{YYYY-MM-DD}-{slug}.json`
  - 例：`knowledge/articles/2026-03-17-openai-agents-sdk.json`
  - 设计决策：知识条目仅保留摘要级字段（id, title, url, source, collected_at, processed_at, summary, highlights, relevance_score, tags, category, maturity），不保留采集级元数据（popularity, author, language, topics, description, readme）。如需获取完整元数据，请回溯 Analyzer 输出文件。
- 索引文件：`knowledge/articles/index.json`
- 状态文件：
  - 仓库搜索：`knowledge/processed/collector-search-{YYYY-MM-DD-HHMMSS}-status.json`
  - Trending：`knowledge/processed/collector-trending-{YYYY-MM-DD-HHMMSS}-status.json`
  - 分析器：`knowledge/processed/analyzer-{YYYY-MM-DD-HHMMSS}-status.json`
  - 整理器：`knowledge/processed/organizer-{YYYY-MM-DD-HHMMSS}-status.json`
- 分析结果：`knowledge/processed/analyzer-{YYYY-MM-DD-HHMMSS}.json`

### JSON 格式
- 使用 2 空格缩进
- 日期格式：ISO 8601（`YYYY-MM-DDTHH:mm:ss+08:00`）
- 字符编码：UTF-8
- 每个知识条目必须包含：`id`, `title`, `source`, `url`, `collected_at`, `summary`, `tags`, `relevance_score`
- 原始采集条目必须包含：`title`, `url`, `popularity`, `popularity_type`, `author`, `created_at`, `updated_at`, `language`, `topics`, `description`, `readme`, `summary`

### 语言约定
- 代码、JSON 键名、文件名：英文
- 摘要、分析、注释：中文
- 标签（tags）：英文小写，用连字符分隔（如 `large-language-model`）

## 项目结构
```
ai-knowledge-base_v2/
├── AGENTS.md                          # 项目记忆文件（本文件）
├── .env                              # 环境变量
├── README.md                          # 使用说明
├── .opencode/
│   ├── agents/
│   │   ├── collector.md               # 采集 Agent 角色定义
│   │   ├── analyzer.md                # 分析 Agent 角色定义
│   │   └── organizer.md               # 整理 Agent 角色定义
│   └── skills/
│       ├── github-collector/          # GitHub 采集技能
│       │   ├── SKILL.md               # 技能定义
│       │   └── scripts/
│       │       ├── common.py          # 公共模块
│       │       ├── github_search.py   # Search API 采集脚本
│       │       └── github_trending.py # Trending 页面采集脚本
│       ├── tech-summary/              # 技术摘要分析技能
│       │   ├── SKILL.md               # 技能定义
│       │   └── scripts/
│       │       └── analyze.py         # LLM 分析脚本
│       └── github-organizer/          # 知识条目整理技能
│           ├── SKILL.md               # 技能定义
│           └── scripts/
│               ├── common.py          # 公共模块
│               └── organize.py        # 整理脚本
├── workflows/                         # LangGraph 工作流实现
│   ├── state.py                      # TypedDict 状态定义
│   ├── state_pydantic.py             # Pydantic 状态定义（推荐）
│   ├── state_with_annotated.py       # Pydantic + Annotated
│   ├── model_client.py               # LLM 客户端封装
│   ├── nodes.py                      # 节点函数
│   └── graph.py                      # 工作流构建
├── knowledge/
│   ├── raw/                           # 原始采集数据（JSON）
│   ├── processed/                     # 状态文件与分析结果（JSON）
│   └── articles/                      # 整理后的知识条目（JSON + MD）
├── logs/                              # 运行时日志记录
├── docs/                              # 项目文档
│   ├── WORKLOG_2025-04-27.md         # 工作日志
│   ├── state_comparison.md           # 状态定义对比
│   ├── annotated_guide.md            # Annotated 使用指南
│   └── annotated_troubleshooting.md  # 故障排除
├── tests/                             # 测试套件
│   └── unit/                         # 单元测试
├── specs/                             # 规格文档
└── plans/                             # 实现计划
```

## 工作流规则

### 三阶段流水线

```
[Collector] ──采集──→ knowledge/raw/ (description, readme, summary="")
                          │
[Analyzer]  ──分析──→ knowledge/processed/ (生成 summary，深度分析)
                          │
[Organizer] ──整理──→ knowledge/articles/
```

### Agent 协作规则

1. **单向数据流**：Collector → Analyzer → Organizer，不可反向
2. **职责隔离**：每个 Agent 只操作自己权限范围内的文件
3. **幂等性**：Collector 通过 `--resume_run` 支持断点续传，重新获取数据源并跳过已处理项目；重复运行同一天的采集不应产生重复条目
4. **质量门控**：Analyzer 评分低于 6 的条目，Organizer 应丢弃
5. **可追溯**：每个条目保留 `url` 和 `collected_at` 用于溯源
6. **摘要生成**：Collector 保留 `description` 和 `readme` 字段，`summary` 置空；由 Analyzer 基于原始内容生成中文摘要

### Agent 调用方式

在 OpenCode 中使用 `@` 语法调用特定 Agent：

```
@collector 采集今天的 GitHub Trending 数据
@analyzer 分析 knowledge/raw/github-trending-2026-03-17.json
@organizer 整理今天所有已分析的原始数据
```

也可以在对话中要求主 Agent 依次委派子 Agent，实现流水线作业。


### 错误处理
- GITHUB_TOKEN 缺失时，脚本报错退出（退出码 1），Agent 需提示用户配置
- 网络请求失败时，记录错误并跳过该条目，不中断整体流程
- API 限流时，等待后重试，最多 3 次
- 数据格式异常时，记录错误并标记 status=failed，供人工排查

## 红线条款
1. 禁止LLM编造非来源内容


# Guideline
Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. lesson and learn
- Windows PowerShell 不支持 && 语法
- 创建目录/文件前，必须先验证该路径是否被框架支持。不确定时问用户，不要假设"其他项目可能有这个模式"
- **【工具调用纪律——防死循环】**
  1. 调用前：检查 schema，确认工具支持所需参数/能力
  2. 调用后：结果不符预期时，先区分"参数错"还是"能力不支持"
  3. 重试前：必须改变参数或策略；相同参数已调用过且结果未变 → 禁止再调
  4. 死锁判定：同一工具+同参数连续 2 次输出相同 → 停止，向用户说明限制
- **【LLM JSON 批量输出与解析】**
  1. **格式选择**：要求返回 `{"results": [...]}` 而非裸数组 `[...]`，因为 `json_object` 模式下部分模型不支持顶层数组
  2. **解析策略**：严格匹配约定格式，不符则报错暴露问题，不要猜测键名降级处理
     ```python
     if isinstance(result, dict) and "results" in result:
         return result["results"]
     elif isinstance(result, list):  # 兼容旧版
         return result
     else:
         raise ValueError(f"期望 {{'results': [...]}} 或 [...]，实际: {type(result)}")
     ```
  3. **重试 Prompt**：必须附带原始数据，不能只说"格式错误"
  4. **Prompt 结构**：先展示输出格式示例，再列输入数据
  5. **校验点**：数组长度必须等于输入数量，失败时明确告知期望 vs 实际
---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

*文档版本：v0.3.0 · 新增 LangGraph 工作流实现*
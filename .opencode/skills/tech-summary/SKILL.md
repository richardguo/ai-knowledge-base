---
name: tech-summary
description: |
  读取 Collector 采集的数据，调用 LLM 生成中文摘要和深度分析。
  当 Collector 采集完成、需要生成中文摘要、或流水线进入分析阶段时触发。
allowed-tools: [Bash, Read, Grep, Glob]
---

# 技术摘要分析技能

## 使用场景

- 读取 Collector 输出的最终文件
- 基于 `description` 和 `readme` 生成中文摘要
- 调用 LLM 进行深度分析，输出结构化结果

## 环境准备

### Python 环境
- **版本**: Python 3.12
- **激活命令**:
  - Windows: `D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat`
  - Linux: `source D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate`

### 依赖库
- requests
- python-dotenv

### 环境变量
需在 `.env` 中配置：
- `LLM_API_BASE`: LLM API 地址（必须）
- `LLM_API_KEY`: API 密钥（必须）
- `LLM_MODEL_ID`: 模型 ID（可选）

### Windows 编码
执行脚本前先运行：
```bash
chcp 65001
```

## 执行流程

**通过脚本执行，不要自行逐条分析。** 脚本已内置：输入发现、LLM 并发调用（5 并发）、去重合并、状态管理、检查点续传、进度回显。

### 运行分析脚本

```bash
python .opencode/skills/tech-summary/scripts/analyze.py [选项]
```

### 选项

| 选项 | 说明 |
|------|------|
| （无参数） | 自动发现：从 `knowledge/processed/` 查找最新 `status=completed` 的 Collector 数据 |
| `--input FILE [FILE ...]` | 指定 1-2 个输入文件路径（流水线模式下由主 Agent 传递） |
| `--source search\|trending` | 仅处理指定数据源（自动发现模式下） |
| `--resume_run` | 从断点续传 |

### 运行模式

**模式一：流水线模式**（推荐）
- 主 Agent 调用 Collector 后，传递输出文件路径给 Analyzer
- Analyzer 通过 `--input` 接收文件路径

**模式二：独立运行**
- 无上游传递文件路径时，Analyzer 自动发现已完成的 Collector 数据
- 通过状态文件 `collector-*-status.json` 定位输入文件

### 典型用法

```bash
# 自动发现最新采集数据（推荐）
python .opencode/skills/tech-summary/scripts/analyze.py

# 仅分析 search 数据源
python .opencode/skills/tech-summary/scripts/analyze.py --source search

# 指定输入文件
python .opencode/skills/tech-summary/scripts/analyze.py --input knowledge/raw/github-search-2026-04-21-100000.json knowledge/raw/github-trending-2026-04-21-100000.json

# 任务中断后续传
python .opencode/skills/tech-summary/scripts/analyze.py --resume_run
```

### 脚本未找到数据时

输出 `❌ 找不到已完成的 Collector 数据` → 提示用户先运行 Collector。

## 输入文件格式

输入文件由 Collector 生成，包含以下字段：
- `description`: 项目描述原文
- `readme`: README 内容
- `summary`: 空字符串（由本脚本填充）

## 输出文件

### 分析结果文件
`knowledge/processed/analyzer-{YYYY-MM-DD-HHMMSS}.json`

```json
{
  "analyzed_at": "2026-04-17T10:30:00+08:00",
  "version": "1.0",
  "input_files": ["knowledge/raw/github-search-2026-04-17-100000.json"],
  "collected_ats": {
    "github-search": "2026-04-17T10:00:00+08:00"
  },
  "items": [
    {
      "title": "项目标题",
      "url": "https://github.com/owner/repo",
      "source": "github-search",
      "popularity": 1234,
      "popularity_type": "total_stars",
      "author": "项目发布者",
      "created_at": "2026-04-17T01:56:15+08:00",
      "updated_at": "2026-04-20T05:27:45+08:00",
      "language": "Python",
      "topics": ["ai", "ml"],
      "description": "项目描述原文",
      "readme": "README 内容",
      "summary": "200-300字中文深度技术摘要，基于 description 和 readme 生成",
      "analysis": {
        "summary": "200-300字中文深度技术摘要",
        "highlights": ["核心亮点1", "核心亮点2", "核心亮点3"],
        "relevance_score": 7,
        "tags": ["large-language-model", "agent-framework"],
        "category": "框架",
        "maturity": "生产"
      }
    }
  ]
}
```

**说明**：
- 输出保留输入文件的所有字段（description, readme 等）
- `summary` 字段填充为中文摘要（从 analysis.summary 复制）
- `analysis` 对象包含完整的分析结果

### 状态文件
`knowledge/processed/analyzer-{YYYY-MM-DD-HHMMSS}-status.json`

脚本自动管理状态文件（started → running → completed/failed），agent 无需手动操作。

## 分析维度

### summary（中文摘要）
- 200-300字深度技术摘要
- 基于 `description` 和 `readme` 生成
- 突出技术本质，避免营销语言

### highlights（技术亮点）
- 2-3个基于事实的技术优势或创新点

### relevance_score（相关性评分）
- **9-10分**：改变技术格局，重大创新
- **7-8分**：对当前工作有直接帮助
- **5-6分**：值得了解的技术动态
- **1-4分**：可略过的内容

### tags（标签）
- 1-3个英文小写标签，连字符分隔
- 示例：`large-language-model`, `agent-framework`, `code-generation`

### category（分类）
- 框架 / 工具 / 论文 / 实践

### maturity（成熟度）
- 实验 / 测试 / 生产

## 质量门控

- ✅ relevance_score < 6 的条目，Organizer 应丢弃
- ✅ 输出保留输入的所有元数据字段，不丢失 Collector 采集的信息

## 环境变量

需在 `.env` 中配置：
- `LLM_API_BASE`: LLM API 地址
- `LLM_API_KEY`: API 密钥
- `LLM_MODEL_ID`: 模型 ID

---
*技能版本: v2.0*
*最后更新: 2026-04-21*
*适用场景: AI 知识库技术内容深度分析与摘要生成*

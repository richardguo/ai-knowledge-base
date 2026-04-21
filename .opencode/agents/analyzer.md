# 分析 Agent (Analyzer)

## 角色
AI 知识库助手的分析 Agent，负责深度解析 Collector 采集的 AI 技术项目，生成结构化分析结果

## 执行方式

**通过脚本执行，不要自行逐条分析。** 脚本已内置：输入发现、LLM 并发调用（5并发）、去重合并、状态管理、检查点续传、进度回显。

### 运行命令

先激活 Python 环境，再执行脚本：

```
D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat
chcp 65001
python scripts/analyze.py [选项]
```

### 选项

| 选项 | 说明 |
|------|------|
| （无参数） | 自动发现：从 `knowledge/processed/` 查找最新 `status=completed` 的 Collector 数据 |
| `--input FILE [FILE ...]` | 指定 1-2 个 raw 文件路径 |
| `--source search\|trending` | 仅处理指定数据源（自动发现模式下） |
| `--resume_run` | 从断点续传 |

### 典型用法

```bash
# 自动发现最新采集数据（推荐）
python scripts/analyze.py

# 仅分析 search 数据源
python scripts/analyze.py --source search

# 指定输入文件
python scripts/analyze.py --input knowledge/raw/github-search-2026-04-21-100000-raw.json knowledge/raw/github-trending-2026-04-21-100000-raw.json

# 任务中断后续传
python scripts/analyze.py --resume_run
```

### 脚本未找到数据时

输出 `❌ 找不到已完成的 Collector 数据` → 提示用户先运行 Collector。

## 权限
### 允许
- Bash：执行 `scripts/analyze.py`
- Read：读取 `knowledge/processed/` 下的输出结果

### 禁止
- 读取或写入 `knowledge/articles/` 目录
- 写入 `knowledge/raw/` 目录
- 自行逐条调用 LLM 分析（必须通过脚本执行）

## 输出

### 输出文件
`knowledge/processed/analyzer-{YYYY-MM-DD-HHMMSS}.json`

```json
{
  "analyzed_at": "2026-04-17T10:30:00+08:00",
  "version": "1.0",
  "input_files": ["knowledge/raw/github-search-2026-04-17-100000-raw.json"],
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

### 状态文件
`knowledge/processed/analyzer-{YYYY-MM-DD-HHMMSS}-status.json`

脚本自动管理状态文件（started → running → completed/failed），agent 无需手动操作。

## 质量门控
- ✅ relevance_score < 6 的条目，Organizer 应丢弃
- ✅ 输出保留输入的所有元数据字段，不丢失 Collector 采集的信息

> 分析维度（摘要、亮点、评分、标签、分类、成熟度）的具体定义详见 `scripts/analyze.py` 中的 ANALYSIS_PROMPT。

---
*基于 AI 知识库三 Agent 协作规格 v1.0 (specs/agents-collaboration.md)*

---
name: github-organizer
description: |
  将 Analyzer 输出的分析结果整理为标准化的知识条目（JSON + Markdown），
  并更新全局索引文件。当 Analyzer 分析完成、需要整理知识条目、
  或流水线进入最后一步时触发。
allowed-tools: [Bash, Read, Grep, Glob, Write]
---

# GitHub Organizer 整理技能

## 使用场景

- 将 Analyzer 输出转换为标准化知识条目
- 生成 JSON 和 Markdown 两种格式
- 更新全局索引文件
- 生成 Organizer 状态文件

## 环境准备

### Python 环境
- **版本**: Python 3.12
- **激活命令**:
  - Windows: `D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat`
  - Linux: `source D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate`

### 依赖库
无额外依赖，使用 Python 标准库。

### 环境变量
无需配置环境变量。

### Windows 编码
执行脚本前先运行：
```bash
chcp 65001
```

## 上游依赖

执行本技能前，必须确保 Analyzer 已完成分析：
- 状态文件 `knowledge/processed/analyzer-*-status.json` 的 `status` 字段为 `"completed"`
- 分析结果文件 `knowledge/processed/analyzer-*.json` 存在且有效

## 执行流程

### 运行整理脚本

```bash
python .opencode/skills/github-organizer/scripts/organize.py --input knowledge/processed/analyzer-{YYYY-MM-DD-HHMMSS}.json
```

参数说明：
| 参数 | 必填 | 说明 |
|------|------|------|
| `--input` | 是 | Analyzer 输出文件路径 |
| `--output-dir` | 否 | 输出目录，默认 `knowledge/articles` |
| `--processed-dir` | 否 | processed 目录，默认 `knowledge/processed` |
| `--resume_run` | 否 | 从断点续传，跳过已处理的条目 |

## 脚本功能

1. **数据加载**: 读取 Analyzer 输出的 JSON 文件
2. **质量过滤**: 过滤 relevance_score < 6 的条目
3. **ID 生成**: 为每个条目生成 UUIDv4
4. **双格式输出**:
   - JSON: 完整结构化数据
   - Markdown: 可读版本，包含摘要和亮点
5. **索引更新**: 更新或创建全局索引文件 `index.json`
6. **状态追踪**: 生成 Organizer 状态文件

## 性能说明

- **不调用大模型**: 脚本仅做数据转换和文件写入，不涉及 LLM API 调用
- **执行速度**: 快，纯 I/O 操作
- **进度输出**: 每处理一个条目输出 `[N/M]` 格式进度到 stderr

## 输出文件

### 知识条目 JSON 格式
```json
{
  "id": "uuidv4",
  "title": "项目标题",
  "url": "https://github.com/owner/repo",
  "source": "github-search",
  "collected_at": "2026-04-21T10:00:00+08:00",
  "processed_at": "2026-04-21T10:45:00+08:00",
  "summary": "200-300字中文深度技术摘要",
  "highlights": ["核心亮点1", "核心亮点2", "核心亮点3"],
  "relevance_score": 7,
  "tags": ["large-language-model", "agent-framework"],
  "category": "框架",
  "maturity": "生产"
}
```

### 知识条目 Markdown 格式
```markdown
---
id: uuidv4
source: github
relevance_score: 7
---

# 项目标题

**来源**: github | **评分**: 7
**分类**: 框架 | **成熟度**: 生产
**标签**: tag1, tag2

**采集时间**: 2026-04-21T10:00:00Z
**处理时间**: 2026-04-21T10:45:00Z

## 摘要
技术摘要

## 核心亮点
- 核心亮点1
- 核心亮点2

[原始链接](https://github.com/owner/repo)
```

### 索引文件格式
```json
{
  "last_updated": "2026-04-21T10:45:00Z",
  "total_entries": 25,
  "entries": [
    {
      "id": "uuidv4",
      "title": "项目标题",
      "source": "github",
      "category": "框架",
      "relevance_score": 7,
      "json_path": "knowledge/articles/2026-04-21-github-slug.json",
      "md_path": "knowledge/articles/2026-04-21-github-slug.md",
      "url": "https://github.com/owner/repo"
    }
  ]
}
```

### 状态文件格式
```json
{
  "agent": "organizer",
  "task_id": "uuidv4",
  "status": "completed",
  "input_file": "knowledge/processed/analyzer-2026-04-21-211509.json",
  "output_file": "knowledge/articles/index.json",
  "entries_created": 25,
  "processed_urls": ["https://github.com/owner/repo1", "https://github.com/owner/repo2"],
  "start_time": "2026-04-21T10:35:00+08:00",
  "end_time": "2026-04-21T10:45:00+08:00"
}
```

## 质量门控

- ✅ relevance_score < 6 的条目会被跳过
- ✅ 所有必填字段完整无缺失
- ✅ 时间戳符合 ISO 8601 格式
- ✅ UUIDv4 全局唯一
- ✅ JSON 使用 2 空格缩进，UTF-8 编码

---
*技能版本: v1.0*
*最后更新: 2026-04-21*
*适用场景: Analyzer 结果整理与知识条目生成*

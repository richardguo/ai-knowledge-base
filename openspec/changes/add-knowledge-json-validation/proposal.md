## Why

当前流水线四个步骤（Collector → Analyzer → Organizer → Saver）通过 JSON 文件传递数据，但缺少正式的 schema 定义和校验机制。
`openspec/specs/project.md` 引用了相关 schema 文件路径，但这些文件尚未创建。
没有 schema 校验，上游产出异常数据（缺字段、类型错误）会静默传递到下游，导致最终知识条目或索引不完整，问题难以溯源。

流水线数据流：
```
Step1Collector → knowledge/raw/pipeline-{timestamp}.json
       ↓
Step2Analyzer → 批量 LLM 分析，添加 analysis 字段
       ↓
Step3Organizer → 去重、过滤（评分>=6）、标准化
       ↓
Step4Saver → knowledge/articles/{date}-{slug}.json + index.json
```

## What Changes

- 新增 `openspec/specs/schemas/collector-output.json`：定义 Step1Collector 产出（`knowledge/raw/pipeline-*.json`）的 JSON Schema
- 新增 `openspec/specs/schemas/analyzer-output.json`：定义 Step2Analyzer 产出（添加 analysis 字段后的数据）的 JSON Schema
- 新增 `openspec/specs/schemas/knowledge-article.json`：定义 Step4Saver 产出的最终知识条目（`knowledge/articles/{date}-{slug}.json`）的 JSON Schema
- 新增 `openspec/specs/schemas/index.json`：定义索引文件（`knowledge/articles/index.json`）的 JSON Schema
- 新增 `hooks/pre-commit-validate.py`：统一校验入口，提供 CLI 和函数式两种调用方式，校验失败输出具体错误位置和原因
- 只在 git commit 前调用校验，拒绝提交不合规数据
- git hook 放 .git/hooks/ · 不用 husky
- pre-commit 失败必须 block · 不用 warn-only

## 流水线步骤说明

1. **Step1Collector**: 从 GitHub Search API 和 RSS 源采集 AI 相关内容
   - 输出: `knowledge/raw/pipeline-{YYYY-MM-DD-HHMMSS}.json`
   - 包含字段: collected_at, source, version, items[]

2. **Step2Analyzer**: 批量调用 LLM 进行摘要/评分/标签分析
   - 批量大小: 10 条
   - 并发数: 5
   - 为每个 item 添加 analysis 字段: summary, highlights, relevance_score, tags, category, maturity

3. **Step3Organizer**: 整理数据
   - 按 URL 去重
   - 过滤评分低于 6 的条目
   - 标准化格式

4. **Step4Saver**: 保存最终知识条目
   - 输出: `knowledge/articles/{YYYY-MM-DD}-{slug}.json`
   - 更新: `knowledge/articles/index.json`


## Capabilities

### New Capabilities
- `json-schema-definitions`: 为流水线四种 JSON 数据契约定义正式的 JSON Schema（collector-output、analyzer-output、knowledge-article、index）
- `json-validation`: 统一的 JSON 校验能力，包含 CLI 工具和 Python API，支持精确的错误报告（字段路径 + 错误原因）

### Modified Capabilities
（无已有 spec 需要修改）

## Impact

- **新增文件**：4 个 JSON Schema 文件（`openspec/specs/schemas/`）、1 个校验模块（`hooks/pre-commit-validate.py`）
- **依赖**：新增 `jsonschema` 第三方库（Python 标准库无 JSON Schema 校验能力）
- **向后兼容**：纯增量变更，不改变现有 JSON 结构，仅增加校验层

## 运行环境
- 先激活 Python 环境，再执行脚本：

```
D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat
chcp 65001
```
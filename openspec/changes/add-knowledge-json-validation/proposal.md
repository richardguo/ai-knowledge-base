## Why

当前流水线各阶段（Collector → Analyzer → Organizer）通过 JSON 文件传递数据，但缺少正式的 schema 定义和校验机制。
`openspec/specs/project.md` 引用了 `specs/schemas/collector-output.json` 和 `specs/schemas/analyzer-output.json`，但这两个文件尚未创建。
没有 schema 校验，上游产出异常数据（缺字段、类型错误）会静默传递到下游，导致 Organizer 生成不完整的知识条目或索引，问题难以溯源。

## What Changes

- 新增 `openspec/specs/schemas/collector-output.json`：定义 Collector 产出（`knowledge/raw/*.json`）的 JSON Schema
- 新增 `openspec/specs/schemas/analyzer-output.json`：定义 Analyzer 产出（`knowledge/processed/analyzer-*.json`）的 JSON Schema
- 新增 `openspec/specs/schemas/knowledge-article.json`：定义最终知识条目（`knowledge/articles/*.json`）的 JSON Schema
- 新增 `openspec/specs/schemas/index.json`：定义索引文件（`knowledge/articles/index.json`）的 JSON Schema
- 新增 `hooks/pre-commit-validate.py`：统一校验入口，提供 CLI 和函数式两种调用方式，校验失败输出具体错误位置和原因
- 只在 git commit前 调用校验，拒绝提交不合规数据
- git hook 放 .git/hooks/ · 不用 husky
- pre-commit 失败必须 block · 不用 warn-only


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
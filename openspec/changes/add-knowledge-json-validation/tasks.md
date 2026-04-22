## 1. Schema 定义

- [x] 1.1 创建 `openspec/specs/schemas/collector-output.json`，定义 Collector 产出数据的 JSON Schema（Draft 2020-12），包含顶层字段和 items 数组的完整约束
- [x] 1.2 创建 `openspec/specs/schemas/analyzer-output.json`，定义 Analyzer 产出数据的 JSON Schema（Draft 2020-12），包含 analysis 对象的完整约束
- [x] 1.3 创建 `openspec/specs/schemas/knowledge-article.json`，定义知识条目的 JSON Schema（Draft 2020-12），包含 metadata 对象的完整约束
- [x] 1.4 创建 `openspec/specs/schemas/index.json`，定义索引文件的 JSON Schema（Draft 2020-12）

## 2. 校验脚本

- [x] 2.1 创建 `hooks/pre-commit-validate.py`，实现 schema 文件按路径模式匹配的逻辑（collector-output / analyzer-output / knowledge-article / index / 跳过状态文件）
- [x] 2.2 实现基于 `jsonschema` 库的校验逻辑，输出格式为 `FAIL: <file_path>` + `<json_path>: <error_message>`
- [x] 2.3 实现 `jsonschema` 依赖缺失时的降级处理（警告 + 退出码 0）
- [x] 2.4 实现 CLI 模式：默认读取 `git diff --cached`、`--all` 全量校验、指定文件路径校验
- [x] 2.5 实现错误汇总输出：按文件排序，末尾输出 `Validation failed: N error(s) in M file(s)`

## 3. Git Hook 配置

- [x] 3.1 创建 `.git/hooks/pre-commit` 薄壳脚本，调用 `python hooks/pre-commit-validate.py`

## 4. 依赖安装

- [x] 4.1 在当前 Python 环境安装 `jsonschema` 库

## 5. 验证

- [x] 5.1 用 `--all` 模式对 `knowledge/` 下现有 JSON 文件做全量校验，确认 schema 与实际数据一致
- [x] 5.2 构造一个不合规 JSON 文件，验证 pre-commit hook 能正确阻止提交
- [x] 5.3 移除不合规文件，验证正常提交流程不受影响

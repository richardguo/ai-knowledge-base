## ADDED Requirements

### Requirement: Pre-commit validation hook
系统 SHALL 提供 `.git/hooks/pre-commit` 脚本，在 `git commit` 前自动调用 `python hooks/pre-commit-validate.py`。hook 脚本 SHALL 仅包含调用该校验脚本的命令。

#### Scenario: Pre-commit hook triggers validation
- **WHEN** 用户执行 `git commit`
- **THEN** `.git/hooks/pre-commit` 被触发，调用 `python hooks/pre-commit-validate.py`

#### Scenario: Pre-commit hook is minimal
- **WHEN** 读取 `.git/hooks/pre-commit` 文件内容
- **THEN** 文件仅包含调用 `python hooks/pre-commit-validate.py` 的命令（薄壳设计）

### Requirement: Validation script entry point
系统 SHALL 提供 `hooks/pre-commit-validate.py` 作为校验入口。该脚本 SHALL：
1. 获取 `git diff --cached --name-only` 中匹配 `knowledge/**/*.json` 的文件列表
2. 根据文件路径模式匹配对应的 schema
3. 对每个文件执行 schema 校验
4. 汇总所有错误并输出
5. 存在任何错误时，脚本以退出码 1 退出；全部通过时以退出码 0 退出

#### Scenario: No JSON files in commit
- **WHEN** 本次 commit 的 staged 文件中不包含 `knowledge/**/*.json` 文件
- **THEN** 脚本直接退出码 0，不做任何校验

#### Scenario: All files pass validation
- **WHEN** 本次 commit 中所有 `knowledge/**/*.json` 文件均符合对应 schema
- **THEN** 脚本退出码 0

#### Scenario: One or more files fail validation
- **WHEN** 本次 commit 中任一 `knowledge/**/*.json` 文件不符合对应 schema
- **THEN** 脚本输出所有校验错误（文件路径 + JSON 路径 + 错误原因），退出码 1，阻止提交

### Requirement: Schema file matching by path pattern
校验脚本 SHALL 按以下路径模式匹配 schema：
- `knowledge/raw/pipeline-*.json` → `openspec/specs/schemas/collector-output.json`（Step1Collector 产出）
- `knowledge/articles/index.json` → `openspec/specs/schemas/index.json`（Step4Saver 索引）
- `knowledge/articles/????-??-??-*.json` → `openspec/specs/schemas/knowledge-article.json`（Step4Saver 知识条目）
- `knowledge/processed/collector-*-status.json` → 不校验（状态文件）
- `knowledge/processed/organizer-*-status.json` → 不校验（状态文件）
- `knowledge/processed/analyzer-*-status.json` → 不校验（状态文件）

无法匹配的 JSON 文件 SHALL 跳过校验，不报错。

#### Scenario: Collector output file matched to correct schema
- **WHEN** staged 文件为 `knowledge/raw/pipeline-2026-04-22-100000.json`
- **THEN** 使用 `openspec/specs/schemas/collector-output.json` 校验

#### Scenario: Knowledge article file matched to correct schema
- **WHEN** staged 文件为 `knowledge/articles/2026-04-22-openai-agents-sdk.json`
- **THEN** 使用 `openspec/specs/schemas/knowledge-article.json` 校验

#### Scenario: Status file skipped
- **WHEN** staged 文件为 `knowledge/processed/collector-search-2026-04-22-status.json`
- **THEN** 跳过校验

#### Scenario: Unmatched JSON file skipped
- **WHEN** staged 文件为 `knowledge/raw/unknown-file.json`
- **THEN** 跳过校验，不报错

### Requirement: Error output format
校验错误 SHALL 按以下格式输出到 stderr：
```
FAIL: <file_path>
  <json_path>: <error_message>
```
其中 `<json_path>` 为 JSON Schema 校验产生的路径（如 `items.0.url`），`<error_message>` 为具体错误原因。

多个文件的错误 SHALL 按文件路径排序输出，最后输出汇总行：
```
Validation failed: <N> error(s) in <M> file(s)
```

#### Scenario: Single file with multiple errors
- **WHEN** 一个文件有 3 个校验错误
- **THEN** 输出该文件路径，后跟 3 行错误详情，每行包含 JSON 路径和错误原因

#### Scenario: Multiple files with errors
- **WHEN** 两个文件分别有校验错误
- **THEN** 按文件路径排序，先输出第一个文件的所有错误，再输出第二个文件的所有错误，最后输出汇总行

### Requirement: jsonschema dependency handling
校验脚本 SHALL 在 `jsonschema` 库不可用时，输出警告信息到 stderr 但以退出码 0 退出（不阻塞提交）。警告格式：`WARNING: jsonschema not installed, skipping validation. Install with: pip install jsonschema`

#### Scenario: jsonschema not installed
- **WHEN** `import jsonschema` 失败
- **THEN** 输出警告信息到 stderr，退出码 0

#### Scenario: jsonschema installed
- **WHEN** `import jsonschema` 成功
- **THEN** 正常执行校验流程

### Requirement: CLI mode for manual validation
`hooks/pre-commit-validate.py` SHALL 支持 CLI 手动调用模式，可通过命令行参数指定要校验的文件或目录：
- `python hooks/pre-commit-validate.py`：校验 `git diff --cached` 中的文件（pre-commit 模式）
- `python hooks/pre-commit-validate.py --all`：全量校验 `knowledge/` 下所有 JSON 文件
- `python hooks/pre-commit-validate.py <file1> <file2>`：校验指定文件

#### Scenario: Manual validation of specific files
- **WHEN** 执行 `python hooks/pre-commit-validate.py knowledge/raw/github-search-2026-04-22-100000.json`
- **THEN** 仅校验指定文件，退出码反映校验结果

#### Scenario: Full validation of all knowledge files
- **WHEN** 执行 `python hooks/pre-commit-validate.py --all`
- **THEN** 校验 `knowledge/` 目录下所有匹配的 JSON 文件

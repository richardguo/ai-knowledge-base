## Context

当前流水线有四个步骤（Collector → Analyzer → Organizer → Saver），通过 JSON 文件传递数据：
- `knowledge/raw/pipeline-{timestamp}.json`：Step1Collector 产出，包含 GitHub 和 RSS 采集的原始数据
- 分析后数据：Step2Analyzer 为每个 item 添加 analysis 字段（summary, highlights, relevance_score, tags, category, maturity）
- 整理后数据：Step3Organizer 执行去重、格式标准化、按评分过滤（>=6）
- `knowledge/articles/{YYYY-MM-DD}-{slug}.json`：Step4Saver 产出的最终知识条目
- `knowledge/articles/index.json`：Step4Saver 更新的索引文件

`openspec/specs/project.md` 已声明了相关 schema 文件路径，但文件未创建。项目约定 git hook 放 `.git/hooks/`、不用 husky、pre-commit 失败必须 block。

## 流水线数据流

```
[Step1Collector] 采集 GitHub + RSS → knowledge/raw/pipeline-{timestamp}.json
        ↓
[Step2Analyzer] 批量 LLM 分析（批量大小: 10, 并发: 5）→ 添加 analysis 字段
        ↓
[Step3Organizer] 去重 + 过滤（评分>=6）+ 标准化
        ↓
[Step4Saver] 保存为独立文件 → knowledge/articles/{date}-{slug}.json + index.json
```

### 批量分析特性
- BATCH_SIZE = 10：每批处理 10 条内容
- MAX_CONCURRENT = 5：最多 5 个并发请求
- 支持失败重试机制
- 使用 ThreadPoolExecutor 实现并发

## Goals / Non-Goals

**Goals:**
- 为四种 JSON 数据契约定义正式的 JSON Schema（Draft 2020-12）
- 提供 git pre-commit hook，在 commit 前自动校验 knowledge/ 下的 JSON 文件
- 校验失败时输出精确错误信息（文件路径 + JSON 路径 + 错误原因），并阻止提交

**Non-Goals:**
- 不在 Agent 脚本内部嵌入校验逻辑（职责分离，Agent 脚本只负责产出数据）
- 不做数据内容语义校验（如 summary 质量判断），仅做结构合规校验
- 不做历史数据回填校验，只校验本次 commit 中变更的 JSON 文件
- 不引入 schema 版本演进机制（当前所有 schema 版本为 1.0）

## Decisions

### 1. Schema 格式：JSON Schema Draft 2020-12

**选择**：使用 JSON Schema Draft 2020-12 标准编写 schema。

**替代方案**：Pydantic model → 拒绝，因为 schema 文件需要可被非 Python 工具消费（如 IDE 校验、在线 validator），JSON Schema 是通用标准。

**理由**：`jsonschema` 库（Python 生态最成熟的校验库）已支持 Draft 2020-12，且 JSON Schema 文件本身可被其他工具直接使用。

### 2. 校验触发时机：仅 git pre-commit

**选择**：只在 `git commit` 前通过 pre-commit hook 触发校验。

**替代方案**：在 Agent 脚本内写入前校验 → 用户已在 proposal 中明确拒绝此方案。

**理由**：Agent 脚本通过 OpenCode Skill 的 Python 脚本执行，LLM 不应自行逐条处理。校验作为独立的防线放在 git hook 层，不侵入 Agent 脚本逻辑。

### 3. 校验脚本位置：hooks/pre-commit-validate.py

**选择**：校验逻辑放在项目根目录 `hooks/` 下，`.git/hooks/pre-commit` 仅作为薄壳调用该脚本。

**替代方案**：全部逻辑写在 `.git/hooks/pre-commit` → 拒绝，`.git/hooks/` 不受版本控制。

**理由**：`hooks/` 受版本控制，可审查；`.git/hooks/pre-commit` 仅 `python hooks/pre-commit-validate.py` 一行调用。

### 4. 校验范围：仅本次 commit 变更的 JSON

**选择**：只校验 `git diff --cached --name-only` 中匹配 `knowledge/**/*.json` 的文件。

**替代方案**：每次 commit 全量校验 → 拒绝，随着数据增长会拖慢提交。

**理由**：只校验变更文件，提交速度快，且不影响已有数据的稳定性。

### 5. 依赖：jsonschema

**选择**：使用 `jsonschema` 库进行校验。

**替代方案**：手写校验逻辑 → 拒绝，JSON Schema 标准复杂，手写易遗漏。

**理由**：`jsonschema` 是 Python 生态事实标准，维护活跃，支持详细错误信息。

## Risks / Trade-offs

- **[Risk] `jsonschema` 未安装在当前 Python 环境中** → pre-commit hook 检测到 `jsonschema` 不可用时，打印警告但不阻塞提交（避免因依赖缺失阻断正常工作流）
- **[Risk] Schema 定义与实际数据不一致** → 首次定义 schema 时基于现有脚本代码逆向推导，需对照 `common.py`、`analyze.py`、`organize_knowledge.py` 中的数据结构，并做一轮全量校验确认
- **[Trade-off] 不在 Agent 脚本内校验** → Agent 可能产出不合规数据但不会立即感知，需等到 commit 时才发现 → 可接受，因为 hook 是最后防线，且 LLM Agent 产出的数据结构相对稳定

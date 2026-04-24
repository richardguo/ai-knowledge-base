## ADDED Requirements

### Requirement: Collector output schema
系统 SHALL 在 `openspec/specs/schemas/collector-output.json` 定义 Step1Collector 产出数据的 JSON Schema，覆盖 `knowledge/raw/pipeline-*.json` 的结构。Schema SHALL 要求以下顶层字段：
- `collected_at`：字符串，ISO 8601 格式，必填
- `source`：字符串，描述数据源类型（多个源用逗号分隔，如 `github,rss`），必填
- `version`：字符串，必填
- `items`：数组，必填

每个 item SHALL 要求以下字段：
- `title`：字符串，必填
- `url`：字符串，URI 格式，必填
- `source`：字符串，条目来源（如 `github-search`, `rss`），必填
- `popularity`：整数，必填，最小值 0
- `popularity_type`：字符串，必填（如 `total_stars`, `none`）
- `author`：字符串，必填（可为空字符串）
- `created_at`：字符串，ISO 8601 格式，必填
- `updated_at`：字符串，ISO 8601 格式，必填
- `language`：字符串，必填（如 `Python`, `N/A`）
- `topics`：字符串数组，必填
- `description`：字符串，必填（可为空字符串）
- `readme`：字符串，必填（可为空字符串，README 内容前 5000 字符）
- `summary`：字符串，必填（可为空字符串，Collector 阶段置空，由 Analyzer 填充）
- `collected_at`：字符串，ISO 8601 格式，必填

#### Scenario: Valid collector output with github-search source
- **WHEN** 校验一个包含 `source: "github-search"` 的 collector output JSON
- **THEN** schema 校验通过，不报告错误

#### Scenario: Valid collector output with rss source
- **WHEN** 校验一个 items 中包含 `source: "rss"` 的 collector output JSON
- **THEN** schema 校验通过，不报告错误

#### Scenario: Missing required top-level field
- **WHEN** 校验一个缺少 `collected_at` 字段的 collector output JSON
- **THEN** schema 校验失败，报告错误路径指向 `collected_at`

#### Scenario: Missing required item field
- **WHEN** 校验一个 items 中某条目缺少 `url` 字段的 collector output JSON
- **THEN** schema 校验失败，报告错误路径指向对应 item 的 `url`

### Requirement: Analyzer output schema
系统 SHALL 在 `openspec/specs/schemas/analyzer-output.json` 定义 Analyzer 产出数据的 JSON Schema，覆盖 `knowledge/processed/analyzer-*.json` 的结构。Schema SHALL 要求以下顶层字段：
- `analyzed_at`：字符串，ISO 8601 格式，必填
- `version`：字符串，必填
- `input_files`：字符串数组，必填
- `items`：数组，必填

每个 item SHALL 包含 collector output item 的所有字段，且额外要求 `analysis` 对象，`analysis` SHALL 包含：
- `summary`：字符串，必填
- `highlights`：字符串数组，必填
- `relevance_score`：整数，必填，范围 1-10
- `tags`：字符串数组，必填
- `category`：字符串，枚举值为 `框架`、`工具`、`论文`、`实践`，必填
- `maturity`：字符串，枚举值为 `实验`、`测试`、`生产`，必填

#### Scenario: Valid analyzer output
- **WHEN** 校验一个结构完整、字段类型正确的 analyzer output JSON
- **THEN** schema 校验通过

#### Scenario: Missing analysis object
- **WHEN** 校验一个 items 中某条目缺少 `analysis` 字段的 analyzer output JSON
- **THEN** schema 校验失败，报告错误路径指向对应 item 的 `analysis`

#### Scenario: Relevance score out of range
- **WHEN** 校验一个 `analysis.relevance_score` 值为 0 的 analyzer output JSON
- **THEN** schema 校验失败，报告 relevance_score 不在 1-10 范围内

#### Scenario: Invalid category value
- **WHEN** 校验一个 `analysis.category` 值为 `"其他"` 的 analyzer output JSON
- **THEN** schema 校验失败，报告 category 不在枚举范围内

### Requirement: Knowledge article schema
系统 SHALL 在 `openspec/specs/schemas/knowledge-article.json` 定义知识条目的 JSON Schema，覆盖 `knowledge/articles/{YYYY-MM-DD}-{slug}.json` 的结构（Step4Saver 产出）。Schema SHALL 要求以下字段：
- `id`：字符串，UUID 格式，必填
- `title`：字符串，必填
- `source`：字符串，必填
- `url`：字符串，URI 格式，必填
- `collected_at`：字符串，ISO 8601 格式，必填
- `processed_at`：字符串，ISO 8601 格式，必填
- `summary`：字符串，必填
- `highlights`：字符串数组，必填
- `tags`：字符串数组，必填
- `relevance_score`：整数，必填，范围 1-10
- `category`：字符串，枚举值为 `框架`、`工具`、`论文`、`实践`，必填
- `maturity`：字符串，枚举值为 `实验`、`测试`、`生产`，必填

#### Scenario: Valid knowledge article
- **WHEN** 校验一个结构完整的知识条目 JSON
- **THEN** schema 校验通过

#### Scenario: Missing id field
- **WHEN** 校验一个缺少 `id` 字段的知识条目 JSON
- **THEN** schema 校验失败，报告错误路径指向 `id`

#### Scenario: Missing processed_at field
- **WHEN** 校验一个缺少 `processed_at` 字段的知识条目 JSON
- **THEN** schema 校验失败，报告错误路径指向 `processed_at`

#### Scenario: Relevance score out of range in article
- **WHEN** 校验一个 `relevance_score` 值为 11 的知识条目 JSON
- **THEN** schema 校验失败，报告 relevance_score 不在 1-10 范围内

### Requirement: Index schema
系统 SHALL 在 `openspec/specs/schemas/index.json` 定义索引文件的 JSON Schema，覆盖 `knowledge/articles/index.json` 的结构（Step4Saver 产出）。Schema SHALL 要求以下顶层字段：
- `version`：字符串，必填
- `last_updated`：字符串，ISO 8601 格式
- `total_entries`：整数，最小值 0
- `entries`：数组，必填

每个 entry SHALL 要求以下字段：
- `id`：字符串，必填
- `title`：字符串，必填
- `source`：字符串，必填
- `category`：字符串，必填
- `relevance_score`：整数，必填，范围 1-10
- `url`：字符串，URI 格式，必填
- `file_path`：字符串，必填
- `tags`：字符串数组，必填
- `collected_at`：字符串，必填

#### Scenario: Valid index file
- **WHEN** 校验一个结构完整的索引 JSON 文件
- **THEN** schema 校验通过

#### Scenario: Index entry with missing field
- **WHEN** 校验一个索引条目缺少 `url` 字段的索引 JSON 文件
- **THEN** schema 校验失败，报告错误路径指向对应条目的 `url`

### Requirement: Schema files use JSON Schema Draft 2020-12
所有 schema 文件 SHALL 声明 `"$schema": "https://json-schema.org/draft/2020-12/schema"`。

#### Scenario: Schema declares correct draft
- **WHEN** 读取任意一个 schema 文件
- **THEN** 其 `$schema` 字段值为 `https://json-schema.org/draft/2020-12/schema`

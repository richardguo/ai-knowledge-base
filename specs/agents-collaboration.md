# AI 知识库 · 三 Agent 协作规格 v1.0

## 总流程
- **触发时间**: 每天 GMT+8 10:00 AM 自动触发
- **执行顺序**: collector → analyzer → organizer · 严格串行
- **数据流向**: 单向流动，不可逆流

## Agent 职责与权限边界

### collector (采集 Agent)
- **输入**: GitHub Trending API / 页面
- **处理**: 抓取 Top 50 项目 · 筛选 AI/LLM/Agent 相关主题
- **输出**: 保存到 `knowledge/raw/github-trending-{YYYY-MM-DD}.json`
- **权限**: 仅可写入 `knowledge/raw/` 目录

### analyzer (分析 Agent)
- **输入**: `knowledge/raw/github-trending-{YYYY-MM-DD}.json`
- **处理**: 每条打 3 维度标签（技术分类/成熟度/相关性评分）
- **输出**: 保存到 `knowledge/processed/{YYYY-MM-DD}-analyzer-completed.json`
- **权限**: 可读 `knowledge/raw/`，可写 `knowledge/processed/`

### organizer (整理 Agent)
- **输入**: `knowledge/processed/{YYYY-MM-DD}-analyzer-completed.json`
- **处理**: 整理为结构化知识条目
- **输出**: 
  - JSON: `knowledge/articles/{YYYY-MM-DD}-{source}-{slug}.json`
  - Markdown: `knowledge/articles/{YYYY-MM-DD}-{source}-{slug}.md`
  - 索引: `knowledge/articles/index.json` (自动更新)
- **权限**: 可读 `knowledge/processed/`，可写 `knowledge/articles/`

## 协作契约

### 数据交换方式
- **介质**: 文件系统（非内存消息）
- **格式**: UTF-8 编码的 JSON
- **时间戳**: ISO 8601 格式 (`YYYY-MM-DDTHH:mm:ssZ`)
- **ID 生成**: UUIDv4，确保全局唯一性

#### 数据文件规范
1. **原始数据** (`knowledge/raw/`)
   ```
   github-trending-{YYYY-MM-DD}.json
   ├── collected_at: "2026-04-17T10:00:00Z"
   ├── source: "github"
   ├── version: "1.0"
   └── items: [ { title, url, popularity, summary } ]
   ```

2. **处理状态** (`knowledge/processed/`)
   ```
   {YYYY-MM-DD}-{agent}-{status}.json
   ├── agent: "collector|analyzer|organizer"
   ├── task_id: "uuidv4"
   ├── status: "started|completed|failed"
   ├── input_file: "path/to/input.json"
   ├── output_file: "path/to/output.json"
   └── error_count: 0
   ```

3. **知识条目** (`knowledge/articles/`)
   ```
   {YYYY-MM-DD}-{source}-{slug}.json
   ├── id: "uuidv4"
   ├── title: "项目标题"
   ├── url: "https://github.com/..."
   ├── source: "github"
   ├── collected_at: "2026-04-17T10:00:00Z"
   ├── processed_at: "2026-04-17T10:30:00Z"
   ├── summary: "技术摘要"
   ├── highlights: ["核心亮点1", "核心亮点2"]
   ├── relevance_score: 7.5
   ├── tags: ["tag1", "tag2"]
   ├── category: "框架|工具|论文|实践"
   └── maturity: "实验|测试|生产"
   ```

### 错误处理策略
#### 上游失败下游怎么办？
- **检测机制**: 下游 Agent 通过状态文件检查上游完成状态
- **处理策略**:
  1. **网络错误**: 自动重试 3 次，每次间隔指数退避
  2. **API 限流**: 等待后重试（GitHub API 60次/小时限制）
  3. **数据解析错误**: 跳过该条目，记录到错误日志，继续处理其他
  4. **存储错误**: 检查磁盘空间，尝试备用存储位置
- **错误日志**: `knowledge/errors/{YYYY-MM-DD}-{agent}.json`
- **继续运行**: 单个条目失败不中断整体流程

#### 错误分类与恢复
| 错误类型 | 检测方式 | 恢复动作 | 重试次数 |
|----------|----------|----------|----------|
| 网络错误 | HTTP 状态码 ≠ 2xx | 等待重试 | 3次 |
| API 限流 | HTTP 429 / X-RateLimit | 计算等待时间 | 1次 |
| 数据格式 | JSON 解析失败 | 跳过条目 | 0次 |
| 磁盘空间 | IOError / OSError | 清理旧文件 | 1次 |

### 重跑策略
#### 手动重跑
- **命令格式**: `python run_pipeline.py --date 2026-04-17 --agent analyzer`
- **依赖检查**: 自动检查上游 Agent 是否已完成
- **幂等性**: 通过状态文件判断，避免重复处理

#### 自动重试
- **调度器重试**: 失败任务加入重试队列，最多重试 3 次
- **时间窗口**: 当天任务失败，在 24 小时内可自动重试
- **人工干预**: 超过重试次数或时间窗口，需要人工介入

### 进度追踪
#### 状态文件系统
每个 Agent 在执行关键节点时写入状态文件：
1. **开始**: `{date}-{agent}-started.json`
2. **成功**: `{date}-{agent}-completed.json`
3. **失败**: `{date}-{agent}-failed.json`

#### 状态聚合与查询
- **聚合服务**: 扫描 `knowledge/processed/` 生成全局状态视图
- **CLI 工具**: `python status.py --date 2026-04-17 --agent collector`
- **可视化**: 控制台状态报告或 HTML 状态页面

#### 监控指标
- **成功率**: 任务成功完成比例
- **处理延迟**: 从采集到入库的时间差
- **错误率**: 各类错误的发生频率
- **人工干预**: 每周需要人工处理的次数

### 调度与触发
#### 自动调度
- **触发时间**: 每天 GMT+8 10:00 AM
- **依赖检查**: 检查前一日任务是否完成
- **并发控制**: 串行执行，避免资源竞争

#### 手动触发
- **重跑特定日期**: `python scheduler.py --rerun --date 2026-04-17`
- **重跑特定 Agent**: `python scheduler.py --rerun --date 2026-04-17 --agent analyzer`
- **紧急任务**: 支持插队执行，暂停常规调度

## 质量门控
### 数据质量检查
1. **完整性**: 所有必填字段必须存在
2. **准确性**: 摘要基于原始内容，无编造成分
3. **一致性**: 相同来源数据格式统一
4. **时效性**: 数据采集后 24 小时内完成处理

### Agent 质量检查
1. **权限合规**: 严格遵循权限边界，无越权操作
2. **错误处理**: 所有错误都被捕获和记录
3. **状态追踪**: 关键节点都有状态文件
4. **资源清理**: 正确处理临时文件和资源

## 版本历史
- **v1.0** (2026-04-17): 基于 prd-to-plan 细化协作契约，明确数据交换、错误处理、重跑策略、进度追踪
- **v0.1** (初始版本): 基础流程和职责定义
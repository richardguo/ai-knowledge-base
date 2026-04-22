# Plan: AI知识库三Agent协作契约实现

> Source PRD: specs/agents-collaboration.md (v2.0)

## 实现状态概览

| 阶段 | 状态 | 说明 |
|------|------|------|
| Phase 1: 数据契约层 | ✅ 已完成 | Collector、Analyzer、Organizer 均已实现 |
| Phase 2: 错误恢复层 | ✅ 已完成 | 断点续传、错误处理已实现 |
| Phase 3: 状态追踪层 | ✅ 已完成 | 状态文件、日志系统已实现 |
| Phase 4: 调度触发层 | ⏳ 待实现 | 自动调度未实现，支持手动触发 |

## Architectural decisions

Durable decisions that apply across all phases:

- **数据存储结构**:
  - `knowledge/raw/{source}-{YYYY-MM-DD-HHMMSS}.json` - 原始采集数据
  - `knowledge/processed/{agent}-{YYYY-MM-DD-HHMMSS}-status.json` - 状态文件
  - `knowledge/processed/analyzer-{YYYY-MM-DD-HHMMSS}.json` - 分析结果
  - `knowledge/articles/{YYYY-MM-DD}-{slug}.json` - 最终知识条目
  - `knowledge/articles/index.json` - 全局索引文件
  - `logs/{agent}-{YYYY-MM-DD-HHMMSS}.log` - 运行时日志

- **数据交换格式**:
  - 统一使用UTF-8编码的JSON格式
  - 时间戳遵循ISO 8601 +08:00格式 (`YYYY-MM-DDTHH:mm:ss+08:00`)
  - ID使用UUIDv4生成，确保全局唯一性
  - Agent间通过文件系统传递数据，不直接内存通信

- **Agent权限边界**:
  - Collector: 仅可写入`knowledge/raw/`，可读取配置文件
  - Analyzer: 可读取`knowledge/raw/`，可写入`knowledge/processed/`
  - Organizer: 可读取`knowledge/processed/`，可写入`knowledge/articles/`
  - 严格遵循单向数据流: Collector → Analyzer → Organizer

- **错误处理原则**:
  - 每个Agent独立记录错误，不中断下游流程
  - 错误日志结构化存储，便于诊断和重试
  - 支持幂等操作：重复运行同一天任务不应产生重复数据

- **状态追踪机制**:
  - 每个处理步骤在`knowledge/processed/`目录留下状态标记
  - 状态文件包含: agent名称、处理时间、输入文件、输出文件、成功/失败状态
  - 支持断点续跑：可根据状态文件判断从何处恢复

---

## Phase 1: 数据契约层 ✅ 已完成

**User stories**: 
- 作为系统架构师，我需要明确的Agent间数据交换格式
- 作为Agent开发者，我需要知道数据应该存储在何处
- 作为维护者，我需要统一的数据命名规范

### Acceptance criteria

- [x] 定义`knowledge/raw/github-search-*.json`和`github-trending-*.json`的文件格式规范
- [x] 实现Collector按新规范写入数据（包含完整元数据：`collected_at`, `source`, `version`）
- [x] 创建`knowledge/processed/`目录结构，定义状态文件格式
- [x] 实现Analyzer读取raw数据并验证格式，生成状态文件
- [x] 实现Organizer输出知识条目和索引文件
- [x] 更新AGENTS.md文档，记录数据契约细节

### 实现文件
- `.opencode/skills/github-collector/scripts/common.py`
- `.opencode/skills/github-collector/scripts/github_search.py`
- `.opencode/skills/github-collector/scripts/github_trending.py`
- `.opencode/skills/tech-summary/scripts/analyze.py`
- `.opencode/skills/github-organizer/scripts/organize.py`
- `.opencode/skills/github-organizer/scripts/common.py`

---

## Phase 2: 错误恢复层 ✅ 已完成

**User stories**:
- 作为系统运维，我需要处理上游Agent失败的情况
- 作为开发者，我需要实现重试策略避免数据丢失
- 作为用户，我需要系统在部分失败时仍能继续运行

### Acceptance criteria

- [x] 实现Collector错误捕获，记录到日志文件
- [x] 定义错误分类：网络错误、API限流、数据解析错误、存储错误
- [x] 实现Analyzer的上游依赖检查：检查raw数据是否存在、格式是否有效
- [x] 制定重试策略：网络错误重试3次，API限流等待后重试，数据错误跳过并记录
- [x] 实现幂等性保证：通过状态文件判断任务是否已执行，避免重复处理
- [x] 支持 `--resume_run` 断点续传

### 实现特性
- **Collector**: `--resume_run` 参数跳过已处理 URL
- **Analyzer**: 检查点机制，每处理 5 条保存进度
- **Organizer**: `--resume_run` 参数跳过已生成条目

---

## Phase 3: 状态追踪层 ✅ 已完成

**User stories**:
- 作为系统管理员，我需要追踪每个Agent的执行进度
- 作为监控系统，我需要获取实时运行状态
- 作为用户，我需要了解数据处理的历史记录

### Acceptance criteria

- [x] 定义统一的状态文件格式：包含agent、task_id、status、start_time、end_time、input、output、error_count
- [x] 实现Agent状态写入：每个Agent在处理开始、成功、失败时更新状态文件
- [x] 实现日志系统：同时输出到 stderr 和日志文件
- [x] 状态文件包含 `raw_items_url` 列表用于断点续传

### 状态文件格式
```json
{
  "agent": "collector|analyzer|organizer",
  "task_id": "{YYYY-MM-DD-HHMMSS}-uuidv4",
  "status": "started|running|completed|failed",
  "sources": ["github-search"],
  "output_files": [],
  "quality": "ok|below_threshold",
  "error_count": 0,
  "start_time": "2026-04-17T10:00:00+08:00",
  "raw_items_url": [],
  "end_time": ""
}
```

---

## Phase 4: 调度触发层 ⏳ 待实现

**User stories**:
- 作为系统调度器，我需要每天自动触发采集任务
- 作为运维人员，我需要手动重跑特定日期的任务
- 作为开发者，我需要检查任务依赖关系

### Acceptance criteria

- [ ] 实现基础调度器：支持每日固定时间触发（GMT+8 10:00 AM）
- [x] 创建手动触发接口：通过命令行参数指定输入文件
- [x] 实现依赖检查：Analyzer自动发现已完成的Collector数据
- [ ] 添加任务优先级管理：支持紧急任务插队、批量任务排队
- [ ] 实现任务通知机制：任务完成/失败时发送通知
- [ ] 创建调度配置文件：支持配置触发时间、重试策略等

### 当前运行方式
```bash
# 手动执行完整流水线

# 1. Collector
python .opencode/skills/github-collector/scripts/github_search.py --top 20
python .opencode/skills/github-collector/scripts/github_trending.py --since daily

# 2. Analyzer（自动发现最新采集数据）
python .opencode/skills/tech-summary/scripts/analyze.py

# 3. Organizer
python .opencode/skills/github-organizer/scripts/organize.py --input knowledge/processed/analyzer-*.json
```

---

## 实施优先级建议

1. **Phase 1 (数据契约层)** - ✅ 已完成
2. **Phase 2 (错误恢复层)** - ✅ 已完成
3. **Phase 3 (状态追踪层)** - ✅ 已完成
4. **Phase 4 (调度触发层)** - ⏳ 下一步实施

## 风险与缓解

| 风险 | 影响 | 缓解措施 | 状态 |
|------|------|----------|------|
| Agent权限越界 | 数据污染、安全风险 | 严格的文件系统权限控制，Agent角色定义审查 | ✅ 已实现 |
| 数据格式不一致 | 解析失败、数据丢失 | 强Schema验证，版本化数据格式 | ✅ 已实现 |
| 调度器单点故障 | 任务无法触发 | 调度器健康检查，备份触发机制 | ⏳ 待实现 |
| 存储空间不足 | 数据无法保存 | 存储监控，自动清理策略 | ⏳ 待实现 |
| API服务限流 | 采集失败 | 请求频率控制，重试机制 | ✅ 已实现 |

## 成功度量

| 指标 | 目标 | 当前状态 |
|------|------|----------|
| 数据完整性 | 99%的采集任务成功完成 | ✅ 已实现 |
| 错误恢复 | 80%的可恢复错误能自动处理 | ✅ 已实现 |
| 处理延迟 | 从采集到知识入库平均延迟 < 2小时 | ✅ 已实现（手动触发） |
| 系统可用性 | 95%的时间调度器正常工作 | ⏳ 待实现 |

---
*计划版本: v2.0*
*更新时间: 2026-04-21*
*实现状态: Phase 1-3 已完成，Phase 4 待实现*

# Plan: AI知识库三Agent协作契约实现

> Source PRD: specs/agents-collaboration.md (v0.1)

## Architectural decisions

Durable decisions that apply across all phases:

- **数据存储结构**:
  - `knowledge/raw/{source}-{YYYY-MM-DD}.json` - 原始采集数据
  - `knowledge/processed/{YYYY-MM-DD}-{agent}-{status}.json` - 处理中间状态
  - `knowledge/articles/{YYYY-MM-DD}-{source}-{slug}.json` - 最终知识条目
  - `knowledge/articles/index.json` - 全局索引文件
  - `knowledge/errors/{YYYY-MM-DD}-{agent}.json` - 错误日志

- **数据交换格式**:
  - 统一使用UTF-8编码的JSON格式
  - 时间戳遵循ISO 8601格式 (`YYYY-MM-DDTHH:mm:ssZ`)
  - ID使用UUIDv4生成，确保全局唯一性
  - Agent间通过文件系统传递数据，不直接内存通信

- **Agent权限边界**:
  - Collector: 仅可写入`knowledge/raw/`，可读取配置文件
  - Analyzer: 仅可读取`knowledge/raw/`，可写入`knowledge/processed/`
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

## Phase 1: 数据契约层

**User stories**: 
- 作为系统架构师，我需要明确的Agent间数据交换格式
- 作为Agent开发者，我需要知道数据应该存储在何处
- 作为维护者，我需要统一的数据命名规范

### What to build

建立完整的数据契约层，定义Agent间数据交换的所有格式、位置和命名规范。实现从Collector到Analyzer的第一个完整数据流验证，确保数据能正确传递并被解析。

端到端流程：Collector采集GitHub Trending数据 → 按规范存入raw目录 → Analyzer读取raw数据 → 验证格式正确性 → 生成处理状态标记。

### Acceptance criteria

- [ ] 定义`knowledge/raw/github-trending-{YYYY-MM-DD}.json`的文件格式规范
- [ ] 实现Collector按新规范写入数据（包含完整元数据：`collected_at`, `source`, `version`）
- [ ] 创建`knowledge/processed/`目录结构，定义状态文件格式
- [ ] 实现Analyzer读取raw数据并验证格式，生成`knowledge/processed/{date}-analyzer-started.json`状态文件
- [ ] 编写数据格式验证脚本，确保JSON Schema符合规范
- [ ] 更新AGENTS.md文档，记录数据契约细节

---

## Phase 2: 错误恢复层

**User stories**:
- 作为系统运维，我需要处理上游Agent失败的情况
- 作为开发者，我需要实现重试策略避免数据丢失
- 作为用户，我需要系统在部分失败时仍能继续运行

### What to build

实现健壮的错误处理和恢复机制。构建从Collector失败到Analyzer重试的完整恢复流程，确保系统在部分组件失败时仍能保持可用性。

端到端流程：模拟Collector失败场景 → 错误被捕获并记录 → Analyzer检测到上游失败 → 根据策略决定等待/跳过/告警 → 系统继续处理其他数据。

### Acceptance criteria

- [ ] 实现Collector错误捕获，写入`knowledge/errors/{date}-collector.json`
- [ ] 定义错误分类：网络错误、API限流、数据解析错误、存储错误
- [ ] 实现Analyzer的上游依赖检查：检查raw数据是否存在、格式是否有效
- [ ] 制定重试策略：网络错误重试3次，API限流等待后重试，数据错误跳过并记录
- [ ] 实现幂等性保证：通过状态文件判断任务是否已执行，避免重复处理
- [ ] 创建错误恢复测试场景，验证系统在部分失败时的行为

---

## Phase 3: 状态追踪层

**User stories**:
- 作为系统管理员，我需要追踪每个Agent的执行进度
- 作为监控系统，我需要获取实时运行状态
- 作为用户，我需要了解数据处理的历史记录

### What to build

建立完整的进度追踪和状态管理系统。实现从任务触发到最终完成的全程状态追踪，支持状态查询、历史回溯和运行监控。

端到端流程：任务触发 → 各Agent更新状态文件 → 状态聚合服务收集信息 → 提供状态查询接口 → 可视化展示运行状态。

### Acceptance criteria

- [ ] 定义统一的状态文件格式：包含agent、task_id、status、start_time、end_time、input、output、error_count
- [ ] 实现Agent状态写入：每个Agent在处理开始、成功、失败时更新状态文件
- [ ] 创建状态聚合服务：扫描`knowledge/processed/`目录，生成全局状态视图
- [ ] 实现状态查询CLI工具：支持查询特定日期、特定Agent、特定任务的状态
- [ ] 添加状态可视化：生成简单的控制台状态报告或HTML状态页面
- [ ] 实现状态清理策略：自动归档或清理老旧状态文件

---

## Phase 4: 调度触发层

**User stories**:
- 作为系统调度器，我需要每天自动触发采集任务
- 作为运维人员，我需要手动重跑特定日期的任务
- 作为开发者，我需要检查任务依赖关系

### What to build

实现灵活的调度和触发系统。支持定时自动触发、手动触发、依赖检查等场景，构建完整的任务调度生命周期管理。

端到端流程：调度器每天10:00触发 → 检查依赖条件 → 按顺序执行Agent → 监控执行状态 → 任务完成通知 → 支持手动重跑界面。

### Acceptance criteria

- [ ] 实现基础调度器：支持每日固定时间触发（GMT+8 10:00 AM）
- [ ] 创建手动触发接口：支持重跑特定日期、特定Agent的任务
- [ ] 实现依赖检查：Analyzer检查Collector是否完成，Organizer检查Analyzer是否完成
- [ ] 添加任务优先级管理：支持紧急任务插队、批量任务排队
- [ ] 实现任务通知机制：任务完成/失败时发送通知（控制台日志/文件记录）
- [ ] 创建调度配置文件：支持配置触发时间、重试策略、通知方式等
- [ ] 编写调度器监控脚本：确保调度器自身高可用

---

## 实施优先级建议

1. **Phase 1 (数据契约层)** - 最高优先级，为后续所有工作奠定基础
2. **Phase 2 (错误恢复层)** - 高优先级，确保系统健壮性
3. **Phase 4 (调度触发层)** - 中优先级，实现自动化
4. **Phase 3 (状态追踪层)** - 中优先级，提升可观测性

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Agent权限越界 | 数据污染、安全风险 | 严格的文件系统权限控制，Agent角色定义审查 |
| 数据格式不一致 | 解析失败、数据丢失 | 强Schema验证，版本化数据格式 |
| 调度器单点故障 | 任务无法触发 | 调度器健康检查，备份触发机制 |
| 存储空间不足 | 数据无法保存 | 存储监控，自动清理策略 |
| API服务限流 | 采集失败 | 请求频率控制，缓存机制 |

## 成功度量

- **数据完整性**: 99%的采集任务成功完成
- **系统可用性**: 95%的时间调度器正常工作
- **错误恢复**: 80%的可恢复错误能自动处理
- **处理延迟**: 从采集到知识入库平均延迟 < 2小时
- **人工干预**: 每周人工干预次数 < 5次

---
*计划版本: v1.0*
*创建时间: 2026-04-17*
*预计总工时: 3-4周（按2人团队估算）*
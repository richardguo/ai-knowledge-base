# AI 知识库 · 三 Agent 协作规格 v2.0

## 总流程
- **触发时间**: 每天 GMT+8 10:00 AM 自动触发
- **执行顺序**: collector → analyzer → organizer · 严格串行
- **数据流向**: 单向流动，不可逆流
- **执行方式**: 每个 Agent 通过专属 Skill 的 Python 脚本执行，禁止 LLM 自行逐条处理

## Agent 职责与权限边界

### collector (采集 Agent)
- **数据源**: 
  - GitHub Search API（过去7天活跃项目，按stars排序）
  - GitHub Trending 页面（daily/weekly/monthly）
- **处理**: 
  - Search: 搜索 AI/LLM/Agent/Harness/SDD/RAG 相关仓库，获取 README
  - Trending: 使用 Playwright 渲染页面，解析热门项目，API 补全缺失字段
- **输出**: 
  - `knowledge/raw/github-search-{YYYY-MM-DD-HHMMSS}.json`
  - `knowledge/raw/github-trending-{YYYY-MM-DD-HHMMSS}.json`
- **权限**: 仅可写入 `knowledge/raw/` 目录
- **脚本**: `.opencode/skills/github-collector/scripts/github_search.py` 和 `github_trending.py`

### analyzer (分析 Agent)
- **输入**: `knowledge/raw/github-search-*.json` 和 `knowledge/raw/github-trending-*.json`
- **处理**: 调用 LLM 对每个项目进行深度分析（摘要、亮点、评分、标签、分类、成熟度）
- **输出**: `knowledge/processed/analyzer-{YYYY-MM-DD-HHMMSS}.json`
- **权限**: 可读 `knowledge/raw/`，可写 `knowledge/processed/`
- **脚本**: `.opencode/skills/tech-summary/scripts/analyze.py`
- **并发**: 最大 5 并发 LLM 调用

### organizer (整理 Agent)
- **输入**: `knowledge/processed/analyzer-{YYYY-MM-DD-HHMMSS}.json`
- **处理**: 过滤低评分条目（relevance_score < 6），生成 JSON + Markdown 双格式
- **输出**: 
  - JSON: `knowledge/articles/{YYYY-MM-DD}-{slug}.json`
  - Markdown: `knowledge/articles/{YYYY-MM-DD}-{slug}.md`
  - 索引: `knowledge/articles/index.json` (自动更新)
- **权限**: 可读 `knowledge/processed/`，可写 `knowledge/articles/`
- **脚本**: `.opencode/skills/github-organizer/scripts/organize.py`

## 协作契约

### 数据交换方式
- **介质**: 文件系统（非内存消息）
- **格式**: UTF-8 编码的 JSON
- **时间戳**: ISO 8601 +08:00 格式 (`YYYY-MM-DDTHH:mm:ss+08:00`)
- **ID 生成**: UUIDv4，确保全局唯一性

#### 数据文件规范

1. **原始采集数据** (`knowledge/raw/`)
   ```json
   {
     "collected_at": "2026-04-17T10:00:00+08:00",
     "source": "github-search",
     "version": "1.0",
     "items": [
       {
         "title": "项目名称",
         "url": "https://github.com/owner/repo",
         "popularity": 1234,
         "popularity_type": "total_stars",
         "author": "owner",
         "created_at": "2026-04-17T01:56:15+08:00",
         "updated_at": "2026-04-20T05:27:45+08:00",
         "language": "Python",
         "topics": ["ai", "ml"],
         "description": "项目描述原文",
         "readme": "README 内容（截断到 5000 字符）",
         "summary": ""
       }
     ]
   }
   ```

2. **Collector 状态文件** (`knowledge/processed/`)
    ```json
    {
      "agent": "collector",
      "task_id": "{YYYY-MM-DD-HHMMSS}-uuidv4",
      "status": "started|running|completed|failed",
      "sources": ["github-search"],
      "output_files": ["knowledge/raw/github-search-*.json"],
      "quality": "ok|below_threshold",
      "error_count": 0,
      "start_time": "2026-04-17T10:00:00+08:00",
      "raw_items_url": [],
      "end_time": "2026-04-17T10:05:00+08:00"
    }
    ```

3. **Analyzer 状态文件** (`knowledge/processed/`)
    ```json
    {
      "agent": "analyzer",
      "task_id": "{YYYY-MM-DD-HHMMSS}-uuidv4",
      "status": "started|running|completed|failed",
      "input_files": ["knowledge/raw/github-search-*.json"],
      "output_file": "knowledge/processed/analyzer-*.json",
      "items_total": 30,
      "items_processed": 30,
      "items_failed": 0,
      "items_deduplicated": 0,
      "error_count": 0,
      "start_time": "2026-04-17T10:20:00+08:00",
      "processed_urls": [],
      "end_time": "2026-04-17T10:30:00+08:00"
    }
    ```

4. **Organizer 状态文件** (`knowledge/processed/`)
    ```json
    {
      "agent": "organizer",
      "task_id": "uuidv4",
      "status": "started|running|completed|failed",
      "input_file": "knowledge/processed/analyzer-*.json",
      "output_file": "knowledge/articles/index.json",
      "entries_created": 15,
      "entries_skipped": 0,
      "processed_urls": [],
      "start_time": "2026-04-17T10:35:00+08:00",
      "end_time": "2026-04-17T10:45:00+08:00"
    }
    ```

5. **分析结果** (`knowledge/processed/`)
    ```json
    {
      "analyzed_at": "2026-04-17T10:30:00+08:00",
      "version": "1.0",
      "input_files": ["knowledge/raw/github-search-*.json"],
      "collected_ats": {
        "github-search": "2026-04-17T10:00:00+08:00"
      },
      "items": [
       {
         "title": "项目标题",
         "url": "https://github.com/owner/repo",
         "source": "github-search",
         "popularity": 1234,
         "popularity_type": "total_stars",
         "author": "项目发布者",
         "created_at": "2026-04-17T01:56:15+08:00",
         "updated_at": "2026-04-20T05:27:45+08:00",
         "language": "Python",
         "topics": ["ai", "ml"],
         "description": "项目描述原文",
         "readme": "README 内容",
         "summary": "200-300字中文深度技术摘要",
         "analysis": {
           "summary": "200-300字中文深度技术摘要",
           "highlights": ["核心亮点1", "核心亮点2", "核心亮点3"],
           "relevance_score": 7,
           "tags": ["large-language-model", "agent-framework"],
           "category": "框架",
           "maturity": "生产"
         }
       }
     ]
   }
   ```

6. **知识条目** (`knowledge/articles/`)
   ```json
   {
     "id": "uuidv4",
     "title": "项目标题",
     "url": "https://github.com/owner/repo",
     "source": "github-search",
     "collected_at": "2026-04-17T10:00:00+08:00",
     "processed_at": "2026-04-17T10:45:00+08:00",
     "summary": "200-300字中文深度技术摘要",
     "highlights": ["核心亮点1", "核心亮点2", "核心亮点3"],
     "relevance_score": 7,
     "tags": ["large-language-model", "agent-framework"],
     "category": "框架",
     "maturity": "生产"
   }
   ```

### 文件命名规范
| 类型 | 格式 | 示例 |
|------|------|------|
| 原始采集数据 | `{source}-{YYYY-MM-DD-HHMMSS}.json` | `github-search-2026-04-20-100000.json` |
| 状态文件 | `{agent}-{YYYY-MM-DD-HHMMSS}-status.json` | `collector-search-2026-04-20-100000-status.json` |
| 分析结果 | `analyzer-{YYYY-MM-DD-HHMMSS}.json` | `analyzer-2026-04-20-103000.json` |
| 知识条目 | `{YYYY-MM-DD}-{slug}.json` | `2026-04-20-openai-agents-sdk.json` |
| 日志文件 | `{agent}-{YYYY-MM-DD-HHMMSS}.log` | `collector-2026-04-20-100000.log` |

### 错误处理策略

#### 错误分类与恢复
| 错误类型 | 检测方式 | 恢复动作 | 重试次数 |
|----------|----------|----------|----------|
| GITHUB_TOKEN 缺失 | 环境变量检查 | 脚本报错退出，提示用户配置 | 0次 |
| 网络错误 | HTTP 状态码 ≠ 2xx | 指数退避重试 | 3次 |
| API 限流 | HTTP 429 / X-RateLimit | 计算等待时间后重试 | 1次 |
| 数据解析错误 | JSON/HTML 解析失败 | 跳过条目，记录错误日志 | 0次 |
| LLM API 错误 | HTTP 非 200 | 重试 | 3次 |

#### 错误状态处理
- 失败时状态文件的 `status` 字段标记为 `"failed"`，`error_count` 递增
- 状态文件本身包含足够信息供排查，不额外生成 failed.json

### 断点续传
- **Collector**: `--resume_run` 参数从状态文件读取已处理 URL，跳过已处理项目
- **Analyzer**: 检查点机制，每处理 5 条保存进度，支持中断后恢复
- **Organizer**: `--resume_run` 参数跳过已生成的知识条目

### 质量门控
1. **Collector 质量检查**:
   - Search 条目数 ≥ 15 → quality: ok
   - Trending 条目数 ≥ 10 → quality: ok
   - 低于阈值不阻断流水线，仅标记

2. **Analyzer 质量检查**:
   - relevance_score < 6 的条目，Organizer 应丢弃
   - 所有条目保留原始元数据字段

3. **Organizer 质量检查**:
   - 所有必填字段完整
   - UUIDv4 全局唯一
   - 索引与实际文件一致

## 运行命令

### Collector
```bash
# 激活环境
D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat
chcp 65001

# GitHub Search
python .opencode/skills/github-collector/scripts/github_search.py --top 20

# GitHub Trending
python .opencode/skills/github-collector/scripts/github_trending.py --since daily --top 20
```

### Analyzer
```bash
# 自动发现最新采集数据
python .opencode/skills/tech-summary/scripts/analyze.py

# 指定输入文件
python .opencode/skills/tech-summary/scripts/analyze.py --input knowledge/raw/github-search-*.json

# 断点续传
python .opencode/skills/tech-summary/scripts/analyze.py --resume_run
```

### Organizer
```bash
python .opencode/skills/github-organizer/scripts/organize.py --input knowledge/processed/analyzer-*.json
```

## 版本历史
- **v2.0** (2026-04-21): 完整同步实际 Agent/Skill 实现，更新数据格式和协作契约
- **v1.0** (2026-04-17): 基于 prd-to-plan 细化协作契约
- **v0.1** (初始版本): 基础流程和职责定义

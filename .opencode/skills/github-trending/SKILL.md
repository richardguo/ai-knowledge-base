---
name: github-trending
description: 当需要采集 GitHub Trending 热门开源项目时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

# GitHub Trending 采集技能

## 使用场景

当需要采集 GitHub Trending 上的热门开源项目，特别是 AI/LLM/Agent 相关技术项目时，使用此技能。适用于：

- 每日技术情报收集
- AI 技术趋势分析  
- 开源项目发现与评估
- 知识库数据源更新

## 执行步骤（7步流程）

### 步骤 1: 搜索热门仓库（GitHub API）
- 访问 GitHub Trending 页面或使用 GitHub Search API
- 搜索条件：今日/本周热门项目，按 star 增长排序
- 获取 Top 50 候选项目列表

### 步骤 2: 提取项目信息
为每个项目提取以下核心信息：
- **仓库名称** (name): 完整的 owner/repo 格式
- **仓库URL** (url): GitHub 仓库完整链接
- **项目描述** (description): 原始英文描述
- **Star 数量** (stars): 当前 star 总数
- **主要语言** (language): 项目主要编程语言
- **主题标签** (topics): GitHub 仓库标签列表

### 步骤 3: 内容过滤
**纳入标准**（符合任意一项）：
- 项目描述包含 AI、LLM、Agent、Machine Learning、Deep Learning 等关键词
- 项目名称或主题标签表明与 AI/LLM/Agent 相关
- 项目 README 显示为 AI 工具、框架或应用

**排除标准**（符合任意一项）：
- Awesome 列表项目（名称包含 "awesome-" 或描述为 "curated list"）
- 非技术内容（教程、课程、书籍、博客）
- 已归档或不再维护的项目
- 非开源或商业项目

### 步骤 4: 去重处理
- 基于仓库 URL 进行去重
- 检查是否已在现有知识库中存在相同项目
- 保留最新版本，避免重复采集

### 步骤 5: 撰写中文摘要
使用以下公式为每个项目生成 50-100 字中文摘要：

```
{项目名称} + {做什么} + {为什么值得关注}
```

**示例公式**：
```
[项目名称] 是一个 [技术类型/框架]，用于 [解决什么问题/提供什么功能]。它值得关注的原因是 [核心创新点/技术优势/应用价值]。
```

**摘要要求**：
- 基于项目描述和 README 内容，无编造成分
- 语言简洁准确，突出技术特点
- 长度控制在 50-100 字之间

### 步骤 6: 排序与筛选
- 按 GitHub 原始热度（star 增长数）降序排列
- 取 Top 15 个最高质量项目
- 确保所有项目符合 AI/LLM/Agent 主题范围

### 步骤 7: 输出 JSON 文件
- 保存到 `knowledge/raw/github-trending-YYYY-MM-DD.json`
- 使用 UTF-8 编码，2 空格缩进
- 包含完整的时间戳和元数据

## 注意事项

### 数据质量
1. **准确性优先**: 所有信息必须基于 GitHub 官方数据，不得编造
2. **中文摘要**: 必须基于项目实际内容，避免主观评价
3. **主题过滤**: 严格限制 AI/LLM/Agent 相关项目，避免主题漂移

### 技术限制
1. **API 限流**: GitHub API 有每小时 60 次请求限制，需合理控制频率
2. **网络稳定性**: 处理网络超时和重试机制
3. **数据验证**: 确保 JSON 格式正确，字段完整无缺失

### 性能优化
1. **批量处理**: 合理组织请求，减少 API 调用次数
2. **缓存利用**: 可缓存已获取的项目信息，避免重复查询
3. **错误恢复**: 单个项目失败不影响整体流程

### 合规要求
1. **尊重版权**: 仅采集公开信息，不侵犯项目知识产权
2. **注明来源**: 所有数据必须保留原始来源链接
3. **合理使用**: 遵守 GitHub 服务条款和 robots.txt 规定

## 输出格式

### JSON 文件结构
```json
{
  "source": "github",
  "skill": "github-trending",
  "collected_at": "2026-04-17T10:00:00Z",
  "items": [
    {
      "name": "owner/repository-name",
      "url": "https://github.com/owner/repository-name",
      "summary": "50-100字中文摘要，描述项目功能、技术特点和价值",
      "stars": 1234,
      "language": "Python",
      "topics": ["ai", "llm", "machine-learning", "framework"]
    }
  ]
}
```

### 字段说明
| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `source` | string | 是 | 数据来源，固定为 "github" |
| `skill` | string | 是 | 技能名称，固定为 "github-trending" |
| `collected_at` | string | 是 | 采集时间，ISO 8601 格式 |
| `items` | array | 是 | 项目数组，最多 15 个条目 |

#### items 数组字段
| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `name` | string | 是 | 仓库名称，格式为 "owner/repo" |
| `url` | string | 是 | 完整的 GitHub 仓库 URL |
| `summary` | string | 是 | 50-100 字中文技术摘要 |
| `stars` | number | 是 | 当前 star 总数 |
| `language` | string | 否 | 主要编程语言（如 Python, JavaScript） |
| `topics` | array | 否 | GitHub 仓库标签列表 |

### 文件命名规范
- **路径**: `knowledge/raw/github-trending-YYYY-MM-DD.json`
- **示例**: `knowledge/raw/github-trending-2026-04-17.json`
- **日期**: 使用采集当天的日期（UTC+8）

### 质量检查清单
✅ **条目数量**: 15 个有效项目（不多不少）  
✅ **字段完整**: 所有必填字段无缺失  
✅ **摘要质量**: 50-100字中文，基于实际内容  
✅ **主题相关**: 所有项目均为 AI/LLM/Agent 相关  
✅ **排序正确**: 按热度降序排列  
✅ **格式规范**: JSON 格式正确，编码 UTF-8  
✅ **时间戳有效**: collected_at 为有效的 ISO 8601 时间戳  

---
*技能版本: v1.0*  
*最后更新: 2026-04-17*  
*适用场景: AI 知识库 GitHub Trending 数据采集*
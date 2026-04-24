
## 技术栈
Python 3.12 · 无框架 · 本地开发 · git 托管

## 运行环境
- 先激活 Python 环境，再执行脚本：

```
D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat
chcp 65001
```

## 流水线架构

四步流水线：采集 → 分析 → 整理 → 保存

- **Step1Collector**: 从 GitHub Search API 和 RSS 源采集 AI 相关内容
- **Step2Analyzer**: 批量调用 LLM 进行摘要/评分/标签分析（批量大小: 10, 并发: 5）
- **Step3Organizer**: 去重 + 格式标准化 + 按评分过滤（>=6）
- **Step4Saver**: 将文章保存为独立 JSON 文件并更新索引

## 关键数据契约

### 原始数据（Step1Collector 产出）
- knowledge/raw/pipeline-{YYYY-MM-DD-HHMMSS}.json · 包含 GitHub 和 RSS 采集的原始数据
  - schema: openspec/specs/schemas/collector-output.json
  - 数据结构: {collected_at, source, version, items[]}

### 分析后数据（Step2Analyzer 产出）
- 分析结果通过 Step2Analyzer 内部处理，添加 analysis 字段到每个 item
  - analysis 字段包含: summary, highlights, relevance_score, tags, category, maturity
  - schema: openspec/specs/schemas/analyzer-output.json

### 整理后数据（Step3Organizer 产出）
- 标准化格式后传递给 Step4Saver
  - 输出字段: id, title, url, source, collected_at, processed_at, summary, highlights, relevance_score, tags, category, maturity

### 最终知识条目（Step4Saver 产出）
- knowledge/articles/{YYYY-MM-DD}-{slug}.json · 最终知识条目
  - schema: openspec/specs/schemas/knowledge-article.json
  - slug 从 title 生成，小写，特殊字符转为连字符
- knowledge/articles/index.json · 索引文件
  - schema: openspec/specs/schemas/index.json
  - 结构: {version, last_updated, total_entries, entries[]}

## 数据源
- GitHub Search API: 搜索 AI/LLM/agent 相关仓库，按 stars 排序
- RSS: Hacker News AI 相关条目 (hnrss.org)

## LLM 配置
环境变量:
- LLM_API_BASE: API 基础地址
- LLM_API_KEY: API 密钥  
- LLM_MODEL_ID: 模型标识符
- LLM_ENABLE_TOKEN_COUNT: 是否启用 Token 估算

支持模型定价: deepseek, qwen, gpt-4o-mini, minimax, glm-4.7

## 项目约定
- git hook 放 .git/hooks/ · 不用 husky
- pre-commit 失败必须 block · 不用 warn-only

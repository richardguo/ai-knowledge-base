# GitHub Collector 实现计划

> ⚠️ 本文档为实现计划，部分内容可能与最终实现有偏差，以 SKILL.md 和实际脚本为准。

## 概述

基于 collector.md (Agent) 和 github-collector SKILL.md，实现 GitHub 采集技能的两个 Python 脚本和相关基础设施。

## 现状分析

### 已有文件
- .opencode/skills/github-collector/scripts/github_trending.py：旧版 Trending 脚本，需完全重写
- .opencode/skills/github-collector/SKILL.md：已定稿
- .opencode/agents/collector.md：已定稿

### 旧版脚本与新规范的差距
| 项目 | 旧版 | 新版 |
|---|---|---|
| 字段名 | name, stars | title, popularity, popularity_type, author |
| 时间格式 | UTC + Z | GMT+8 + +08:00 |
| 文件名 | github-trending-YYYY-MM-DD.json | github-trending-YYYY-MM-DD-HHMMSS.json |
| 字段补全 | 无 | GitHub API 补全 created_at, updated_at, topics, readme |
| 认证 | 无 | GITHUB_TOKEN |
| description | 留空 | 填 description 原文，最终文件保留 description/readme，summary 置空 |
| 排序 | 按 stars 降序 | 保持页面原始顺序 |
| 超时 | 9.5s 退出 | Trending 页面抓取 15s 超时，API 请求由重试机制管理 |
| 命令行参数 | 无 | --since, --output-dir, --top, --resume_run |
| EXCLUDE_PATTERNS | 含 tutorial | 不含 tutorial |
| DESC_KEYWORDS | 含 neural | 不含 neural |
| 日志 | 仅 stderr | stderr + 日志文件 |
| 断点续传 | 无 | 支持 --resume_run |

### 缺失文件
- .opencode/skills/github-collector/scripts/github_search.py：需新建
- .opencode/skills/github-collector/scripts/common.py：需新建（公共模块）
- .env：需新建（含 GITHUB_TOKEN）
- knowledge/raw/ 目录：需确保存在
- knowledge/processed/ 目录：需确保存在
- logs/ 目录：需确保存在

---

## Python 环境

**所有脚本运行前必须执行以下步骤**：

1. 激活 Python 环境：
   - Windows：D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat
   - Linux：source D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate
2. Windows 下设置 UTF-8 代码页：chcp 65001

**环境信息**：
- Python 3.12
- 环境路径：D:\Development\PythonProject\Shared_Env\python312_opencode
- 如需安装依赖，必须在此环境下执行 pip install

---

## 日志规范

### 日志通道
- **stderr**：运行时日志（进度、警告、错误），Agent 通过 Bash 工具捕获
- **stdout**：脚本正式输出（输出文件路径），Agent 读取后知道去哪里找 .json
- **日志文件**：持久化日志，供事后排查

### 日志文件路径
logs/collector-{YYYY-MM-DD-HHMMSS}.log

### 日志格式
`
{ISO8601时间} [{级别}] {消息}
`
示例：
`
2026-04-20T10:00:01+08:00 [INFO] 开始采集 GitHub Search 数据
2026-04-20T10:00:03+08:00 [INFO] 匹配: pytorch/pytorch | stars=85000 | topics=[ai, ml]
2026-04-20T10:00:05+08:00 [WARNING] README 获取失败: owner/repo - 404
2026-04-20T10:00:10+08:00 [ERROR] Search API 请求失败: HTTP 403
`

---

## 状态管理

### 状态文件完全由脚本管理

脚本负责状态文件的完整生命周期，Agent 不读写状态文件。

### 状态文件路径
- 仓库搜索：`knowledge/processed/collector-search-{YYYY-MM-DD-HHMMSS}-status.json`
- Trending：`knowledge/processed/collector-trending-{YYYY-MM-DD-HHMMSS}-status.json`

### 状态文件格式
`json
{
  "agent": "collector",
  "task_id": "{YYYY-MM-DD-HHMMSS}-uuidv4",
  "status": "started|running|completed|failed",
  "sources": ["github-search"],
  "output_files": [
    "knowledge/raw/github-search-{YYYY-MM-DD-HHMMSS}.json"
  ],
  "quality": "ok|below_threshold",
  "error_count": 0,
  "start_time": "2026-04-17T10:00:00+08:00",
  "raw_items_url": [],
  "end_time": "2026-04-17T10:05:00+08:00"
}
``

每个脚本独立运行，各有自己的状态文件。Search 脚本 sources 为 `["github-search"]`，Trending 脚本 sources 为 `["github-trending"]`。

质量判定规则（每个脚本独立判定）：
- Search 脚本：条目数 ≥ 15 → `"ok"`，否则 `"below_threshold"`
- Trending 脚本：条目数 ≥ 10 → `"ok"`，否则 `"below_threshold"`
`

### 脚本的状态管理职责
1. **新 run**：创建状态文件，status=started -> running -> completed/failed
2. **Resume run（--resume_run）**：读取已有状态文件，重新获取数据源，跳过已处理项目
3. **每处理完一个项目**：追加 URL 到 raw_items_url
4. **开始/结束**：写入 start_time / end_time
5. **失败时**：写入 knowledge/processed/collector-search-{YYYY-MM-DD-HHMMSS}-failed.json 或 collector-trending-{YYYY-MM-DD-HHMMSS}-failed.json

### Continue run 机制
1. 传入 --resume_run 参数
2. 脚本在 knowledge/processed/ 下查找状态文件：
   - 文件名匹配 collector-search-*-status.json 或 collector-trending-*-status.json
   - sources 包含当前脚本对应的 source（如 github-search 或 github-trending）
   - status 不是 completed
   - 取最新（按文件修改时间排序）的一个
3. 从状态文件名解析 HHMMSS（保持文件名一致）
4. 读取 raw_items_url，跳过已处理项目（仅跳过 README 获取+写入，仍需重新获取数据源）
5. 从状态文件的 output_files 字段读取已有 .json 文件，先读旧内容再合并新结果后写入
6. 继续处理剩余项目，更新 raw_items_url

### 输出文件写入策略
- 每处理完一个项目，先读已有 .json 文件，按 URL 去重合并新条目（新数据覆盖旧数据），再写入完整文件
- 保证文件始终是合法 JSON，支持中断后继续

---

## 退出码约定

| 场景 | 退出码 |
|---|---|
| 正常完成（包括部分项目失败） | 0 |
| GITHUB_TOKEN 缺失 | 1 |
| 主 API 请求失败（Search API / Trending 页面） | 1 |
| 输出文件写入失败 | 1 |
| --top 超过 100 | 1 |
| --resume_run 找不到未完成的状态文件 | 1 |
| Trending star 增长数解析失败 | 1 |

---

## 阶段一：基础设施

### 任务 1.1：创建 .env 文件
- 路径：项目根目录 .env
- 内容：GITHUB_TOKEN=your_github_token_here
- 注意：.gitignore 中应已包含 .env

### 任务 1.2：确保目录结构
- 创建 knowledge/raw/（如不存在）
- 创建 knowledge/processed/（如不存在）
- 创建 logs/（如不存在）

### 任务 1.3：确认 Python 依赖
需确保 python312_opencode 环境中已安装：
- requests
- beautifulsoup4
- python-dotenv

**验证**：在激活环境下执行 pip list | findstr "requests beautifulsoup4 dotenv" 输出三个包

### 验证
- .env 文件存在且包含 GITHUB_TOKEN 键
- 三个目录存在
- 依赖包已安装

---

## 阶段二：公共模块

两个脚本共享以下逻辑，提取为公共模块 common.py：
common.py 是无状态的纯函数模块，所有函数都是"输入参数 -> 返回结果"，不共享全局可变状态，多任务运行时不会互相干扰。

### 任务 2.1：创建 .opencode/skills/github-collector/scripts/common.py

包含：

1. **setup_logger(name: str, log_dir: str, timestamp: str) -> logging.Logger**：创建同时输出到 stderr 和日志文件的 logger
   - stderr handler：简单格式，供 Agent 实时查看
   - file handler：写入 logs/collector-{timestamp}.log，完整格式
   - 日志格式：{ISO8601时间} [{级别}] {消息}

2. **load_env() -> str**：从项目根目录 .env 读取 GITHUB_TOKEN
   - 使用 python-dotenv（rom dotenv import load_dotenv）解析 .env
   - .env 路径定位：基于脚本文件位置（__file__）向上推导，找到包含 .git 或 AGENTS.md 的目录作为项目根目录
   - 找不到 .env 或缺少 GITHUB_TOKEN 时，输出错误信息到 stderr 并 sys.exit(1)

3. **github_api_get(url: str, token: str, params: dict | None = None, max_retries: int = 3) -> requests.Response | None**：带认证和重试的 GitHub API GET 请求
   - Header：Authorization: token {token}, Accept: application/vnd.github.v3+json
   - 重试 3 次，指数退避（1s, 2s, 4s）
   - 检测 HTTP 429，从 X-RateLimit-Reset header 计算等待时间
   - 每次成功请求后检查 X-RateLimit-Remaining，剩余 < 5 则 sleep 到 reset 时间
   - 日志记录：每次请求记录 URL、HTTP 状态码、重试次数；限流时记录等待时间

4. **etch_readme(owner: str, repo: str, token: str) -> str**：获取 README 内容
   - 调用 GET https://api.github.com/repos/{owner}/{repo}/readme
   - 响应为 Base64 编码，解码前需去掉 content 中的换行符（\n）
   - 返回解码后的字符串，截断到 5000 字符，失败返回空字符串

5. **etch_repo_details(owner: str, repo: str, token: str) -> dict**：获取仓库详情
   - 调用 GET https://api.github.com/repos/{owner}/{repo}
   - 提取 created_at, updated_at, 	opics
   - 时间从 UTC 转为 GMT+8 +08:00 格式
   - 返回 dict，失败返回各字段默认值

6. **	o_gmt8(utc_str: str) -> str**：UTC ISO 8601 时间字符串转 GMT+8 +08:00 格式
   - 输入：2026-04-16T17:56:15Z 或 2026-04-16T17:56:15+00:00
   - 输出：2026-04-17T01:56:15+08:00

7. **内容过滤配置常量**
   - TARGET_TOPICS：不含 
eural
   - EXCLUDE_PATTERNS：不含 	utorial
   - DESC_KEYWORDS：不含 
eural
   - is_excluded(name: str, description: str) -> bool：排除判断
   - matches_ai(topics: list[str], description: str) -> bool：纳入判断

8. **generate_timestamp() -> str**：生成当前 GMT+8 的 YYYY-MM-DD-HHMMSS 字符串

9. **generate_collected_at() -> str**：生成当前 GMT+8 的 ISO 8601 +08:00 时间字符串

### 任务 2.2：创建测试 .opencode/skills/github-collector/scripts/tests/test_common.py

测试用例：
- 	est_to_gmt8：UTC 转 GMT+8，含 Z 后缀和 +00:00 两种输入
- 	est_is_excluded：排除模式匹配
- 	est_matches_ai：纳入标准匹配
- 	est_generate_timestamp：时间戳格式校验
- 	est_generate_collected_at：ISO 8601 +08:00 格式校验
- 	est_load_env_missing：.env 缺失时退出
- 	est_load_env_no_token：GITHUB_TOKEN 缺失时退出
- 	est_fetch_readme_truncation：README 截断到 5000 字符

### 验证
- common.py 可被 import 无报错
- 各函数有类型注解和 docstring
- pytest tests/test_common.py 全部通过

---

## 阶段三：github_search.py 脚本

### 任务 3.1：创建 .opencode/skills/github-collector/scripts/github_search.py

#### 命令行参数（argparse）
| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| --output-dir | str | knowledge/raw | 输出目录 |
| --top | int | 50 | 取 Top N 项目，最大 100，超过报错 |
| --resume_run | bool | False | 继续未完成的任务 |

#### 执行流程

1. **初始化**：调用 common.load_env() 获取 token，创建 logger
2. **Continue 模式判断**
   - 若 --resume_run：在 knowledge/processed/ 下查找未完成的状态文件（source 含 github-search）
   - 找到：解析 HHMMSS，读取 raw_items_url（跳过已处理项目的 README 获取+写入），从状态文件的 output_files 读取已有 .json
   - 未找到：sys.exit(1) 并提示无未完成任务
   - 若非 resume_run：生成新的 HHMMSS，创建状态文件（status=started）
3. **构建搜索请求**（无论是否 resume_run 都重新调用 API，因为搜索结果可能已变化）
   - 计算 pushed:> 日期：当前日期 - 7 天
   - 查询字符串：AI OR LLM OR agent OR "large language model" OR Harness OR SDD OR RAG OR "machine learning" pushed:>2026-04-13
   - 参数：sort=stars&order=desc&per_page={top}
4. **调用 Search API**
   - GET https://api.github.com/search/repositories?q=...&sort=stars&order=desc&per_page={top}
   - 使用 common.github_api_get()
5. **解析响应**
   - 从 items[] 数组提取每个仓库：
     - title：item["name"]（repo 名，如 pytorch）
     - url：item["html_url"]
     - popularity：item["stargazers_count"]
     - popularity_type：固定 "total_stars"
     - author：item["owner"]["login"]
     - created_at：common.to_gmt8(item["created_at"])
     - updated_at：common.to_gmt8(item["updated_at"])
     - language：item["language"] 或 "N/A"
     - topics：item.get("topics", [])
      - description：item.get("description", "") 或 ""
   - 不做二次内容过滤，留给下游 Analyzer
6. **获取 README**：对每个项目，若 URL 在 raw_items_url 中（resume_run 模式）则跳过，否则调用 common.fetch_readme()（截断到 5000 字符）
7. **逐条写入输出文件**：每处理完一个项目，先读已有 .json，按 URL 去重合并新条目（新数据覆盖旧数据），再写入完整文件
8. **更新状态文件**：每处理完一个项目，追加 URL 到 raw_items_url
9. **完成**：状态文件 status=completed，写入 end_time，根据条目数量判定 quality（Search ≥ 15 为 ok，否则 below_threshold），stdout 输出文件路径

#### 错误处理
- Search API 调用失败：logger.error + stderr，status=failed，sys.exit(1)
- 单个项目 README 获取失败：readme 字段填空字符串，logger.warning，继续处理
- 输出文件写入失败：logger.error + stderr，status=failed，sys.exit(1)
- 输出目录不存在：自动创建
- --top > 100：报错退出

### 任务 3.2：创建测试 .opencode/skills/github-collector/scripts/tests/test_github_search.py

测试用例（mock GitHub API）：
- 	est_search_api_basic：正常搜索返回正确结构
- 	est_search_readme_failure：README 获取失败时不阻断
- 	est_search_readme_truncation：README 截断到 5000 字符
- 	est_search_output_format：输出文件 JSON 格式符合规范
- 	est_search_cli_args：命令行参数解析
- 	est_search_top_limit：--top > 100 报错
- 	est_search_status_file：状态文件创建和更新
- 	est_search_continue：--resume_run 跳过已处理项目
- 	est_search_incremental_write：逐条写入输出文件
- 	est_search_stdout_output：stdout 输出文件路径

### 验证
`bash
chcp 65001
D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat
python .opencode/skills/github-collector/scripts/github_search.py --output-dir knowledge/raw --top 10
`
- 确认 knowledge/raw/ 下生成 github-search-*.json
- 确认 knowledge/processed/ 下生成状态文件
- 确认 logs/ 下生成日志文件
- 确认 JSON 格式正确，字段完整
- 确认 readme 字段有内容且不超过 5000 字符
- 确认 description 字段为 description 原文
- 确认时间格式为 +08:00
- 确认 stdout 输出文件路径
- pytest tests/test_github_search.py 全部通过

---

## 阶段四：github_trending.py 脚本（重写）

### 任务 4.1：重写 .opencode/skills/github-collector/scripts/github_trending.py

#### 命令行参数（argparse）
| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| --since | str | daily | 时间范围：daily/weekly/monthly |
| --output-dir | str | knowledge/raw | 输出目录 |
| --top | int | None | 取 Top N 项目，None 表示按 since 默认值：daily=20, weekly=25, monthly=30。不设上限，实际取值受页面项目数限制 |
| --resume_run | bool | False | 继续未完成的任务 |

#### 执行流程

1. **初始化**：调用 common.load_env() 获取 token，创建 logger
2. **Continue 模式判断**
   - 若 --resume_run：在 knowledge/processed/ 下查找未完成的状态文件（source 含 github-trending）
   - 找到：解析 HHMMSS，读取 raw_items_url（跳过已处理项目的 API 补全+写入），从状态文件的 output_files 读取已有 .json
   - 未找到：sys.exit(1) 并提示无未完成任务
   - 若非 resume_run：生成新的 HHMMSS，创建状态文件（status=started）
3. **计算 --top 默认值**：若为 None，按 --since 设定：daily=20, weekly=25, monthly=30（无论是否 resume_run 都重新抓取页面，因为 Trending 列表可能已变化）
4. **抓取 Trending 页面**
   - URL：https://github.com/trending?since={since}
   - User-Agent 伪装浏览器
   - 超时 15s
5. **解析 HTML**
   - 选择器：article.Box-row
   - 提取：
     - title：从 h2 a 的 href 中取 repo 名部分（如 /pytorch/pytorch -> pytorch）
     - author：从 href 中取 owner 部分（如 /pytorch/pytorch -> pytorch）
     - url：https://github.com/{owner}/{repo}
     - description：article.select_one("p") 的文本
      - language：从 HTML 中提取编程语言（优先 `[itemprop='programmingLanguage']` 选择器，降级尝试 `span.d-inline-block.ml-0.mr-3`，再降级扫描 `div.d-inline-flex` 下的 span）
      - topics：降级策略——依次尝试选择器 `a.topic-tag`、`a[data-ga-click*='topic']`、`a[href*='topics']`、`div.tags a`、`span.Label--topic`，取首个命中结果；若 HTML 无 topics 且有 description，则从 description 中匹配 TARGET_TOPICS 关键词（最多 5 个）
      - star 增长数：解析页面上的 "xxx stars today/this week/this month"（解析失败则报错退出，需调试选择器直到正确）
    - 应用内容过滤：is_excluded() 排除，matches_ai() 纳入
    - **防误杀**：若 HTML topics 为空且 matches_ai() 未命中，先调用 `/repos/{owner}/{repo}` 获取 API topics 再重新判断 matches_ai()，避免因 HTML topics 不完整导致误杀
    - **保持页面原始顺序**（不按 stars 重新排序）
    - 过滤后截取 Top N 项目，不足额时不补取
 6. **补全缺失字段**：对每个通过过滤的项目，若 URL 在 raw_items_url 中（resume_run 模式）则跳过，否则调用 common.py 的函数：
    - common.fetch_repo_details() -> created_at, updated_at, topics（若防误杀步骤已调用过，复用结果）
    - common.fetch_readme() -> README 内容（截断到 5000 字符）
    - 注意：API 返回的 topics 优先使用，覆盖 HTML 解析值
 7. **逐条写入输出文件**：每处理完一个项目，先读已有 .json，按 URL 去重合并新条目（新数据覆盖旧数据），再写入完整文件
 8. **更新状态文件**：每处理完一个项目，追加 URL 到 raw_items_url
 9. **完成**：状态文件 status=completed，写入 end_time，根据条目数量判定 quality（Trending ≥ 10 为 ok，否则 below_threshold），stdout 输出文件路径

#### 错误处理
- Trending 页面抓取失败：logger.error + stderr，status=failed，sys.exit(1)
- 单个项目 API 补全失败：缺失字段填默认值（created_at/updated_at 填当前时间），logger.warning，继续处理
- HTML 解析失败（页面结构变化）：logger.warning，跳过该项目
- star 增长数解析失败：logger.error + stderr，sys.exit(1)（需调试选择器）
- 输出文件写入失败：logger.error + stderr，status=failed，sys.exit(1)
- 输出目录不存在：自动创建
- --resume_run 找不到未完成的状态文件：报错退出

### 任务 4.2：创建测试 .opencode/skills/github-collector/scripts/tests/test_github_trending.py

测试用例（mock Trending 页面 + GitHub API）：
- 	est_trending_parse_html：HTML 解析提取正确字段
- 	est_trending_filter_excluded：排除规则生效
- 	est_trending_filter_ai_match：纳入规则生效
- 	est_trending_api_supplement：API 补全字段正确
- 	est_trending_api_failure：API 补全失败时填默认值
- 	est_trending_preserve_order：保持页面原始顺序
- 	est_trending_since_param：--since 参数影响 popularity_type 和 URL
- 	est_trending_top_default：--top 默认值随 --since 变化
- 	est_trending_output_format：输出文件 JSON 格式符合规范
- 	est_trending_star_growth_parse：star 增长数解析（失败报错）
- 	est_trending_readme_truncation：README 截断到 5000 字符
- 	est_trending_status_file：状态文件创建和更新
- 	est_trending_continue：--resume_run 跳过已处理项目
- 	est_trending_incremental_write：逐条写入输出文件
- 	est_trending_stdout_output：stdout 输出文件路径

### 验证
`bash
chcp 65001
D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat
python .opencode/skills/github-collector/scripts/github_trending.py --since daily --output-dir knowledge/raw
`
- 确认 knowledge/raw/ 下生成 github-trending-*.json
- 确认 knowledge/processed/ 下生成状态文件
- 确认 logs/ 下生成日志文件
- 确认 JSON 格式正确，字段完整
- 确认 since 字段值为 "daily"
- 确认 popularity_type 为 "daily_stars"
- 确认 readme 字段有内容且不超过 5000 字符
- 确认 created_at/updated_at 有值（API 补全成功）
- 确认保持页面原始顺序（非按 stars 排序）
- 确认时间格式为 +08:00
- 确认 stdout 输出文件路径
- pytest tests/test_github_trending.py 全部通过

---

## 阶段五：端到端集成验证

### 任务 5.1：完整流程验证

1. 激活 Python 环境
2. 运行 github_search.py --top 10
3. 运行 github_trending.py --since daily
4. 检查两个输出文件的 JSON 格式和字段完整性
5. 检查状态文件的 raw_items_url 与实际条目一致
6. 检查 logs/ 下日志文件内容
7. 确认 description 和 readme 字段可供 Analyzer 使用

### 任务 5.2：Continue run 验证

1. 运行 github_trending.py --top 5，手动中断（Ctrl+C）
2. 运行 github_trending.py --resume_run
3. 确认跳过已处理的 5 个项目，继续处理剩余项目
4. 确认输出文件包含所有项目（已处理 + 新处理）
5. 确认状态文件 raw_items_url 包含所有 URL

### 任务 5.3：边界场景验证

1. **无 GITHUB_TOKEN**：确认脚本报错退出（退出码 1），提示配置 token
2. **网络异常**：确认重试机制生效
3. **空结果**：确认输出空 items 数组的 JSON（退出码 0），而非崩溃
4. **--since weekly**：确认 URL 参数正确，popularity_type 为 "weekly_stars"
5. **--since monthly**：同上
6. **--top 5**：确认只取 5 个项目
7. **--top 101**：确认报错退出
8. **--resume_run 无未完成任务**：确认报错退出并提示

### 任务 5.4：集成测试（真实 API）

使用真实 GITHUB_TOKEN 调用一次，验证 API 兼容性（不在 pytest 自动套件中）：
1. python github_search.py --top 5
2. python github_trending.py --since daily --top 5
3. 检查返回数据格式与 spec 一致

---

## 文件交付清单

| 文件 | 操作 | 阶段 |
|---|---|---|
| .env | 新建 | 1 |
| knowledge/raw/ | 确保存在 | 1 |
| knowledge/processed/ | 确保存在 | 1 |
| logs/ | 确保存在 | 1 |
| scripts/common.py | 新建 | 2 |
| scripts/tests/test_common.py | 新建 | 2 |
| scripts/github_search.py | 新建 | 3 |
| scripts/tests/test_github_search.py | 新建 | 3 |
| scripts/github_trending.py | 重写 | 4 |
| scripts/tests/test_github_trending.py | 新建 | 4 |

---

## 注意事项

1. **Python 环境**：所有脚本运行前必须激活 python312_opencode 环境，如需安装依赖也在此环境下
2. **编码**：Windows 下先执行 chcp 65001 设置 UTF-8 代码页
3. **依赖**：requests, beautifulsoup4, python-dotenv 需已安装在 python312_opencode 环境中
4. **摘要生成由 Analyzer 负责**：Collector 输出的最终文件保留 `description` 和 `readme` 字段，`summary` 置空，由下游 Analyzer 基于原始内容生成中文摘要
5. **common.py 无副作用**：纯函数和 I/O 最小化的工具函数，状态管理逻辑由各脚本自行实现
6. **Agent 与脚本通信**：stdout 输出文件路径，stderr 输出运行日志，日志文件持久化
7. **状态管理由脚本负责**：Agent 不读写状态文件
8. **README 截断**：超过 5000 字符截断
9. **--top 上限 100**：超过报错退出
10. **star 增长数解析必须成功**：失败则报错，需调试选择器
11. **Search API 不做二次内容过滤**：留给下游 Analyzer
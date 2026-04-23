# MCP Knowledge Server

基于 Model Context Protocol 的知识库搜索服务器，为 AI 工具（OpenCode、Claude Desktop、Cursor、Continue 等）提供本地知识库访问能力。

## 功能特性

- 按关键词搜索文章（标题、摘要、标签）
- 按来源、标签、评分过滤文章
- 按 ID 获取文章完整内容
- 知识库统计信息查询
- 支持 **stdio**（本地）和 **SSE**（远程）两种传输模式

## 快速启动

### SSE 模式（默认，支持远程连接）

```powershell
# 方式一：启动脚本
.\utils\start_mcp_server.bat

# 方式二：命令行
python utils/mcp_knowledge_server.py

# 方式三：显式指定
python utils/mcp_knowledge_server.py --transport sse
```

启动成功后显示：
```
知识库目录: D:\...\knowledge\articles
已加载文章数: 100
MCP Server 启动中 (SSE 模式)...
SSE 端点: http://localhost:8000/sse
```

### stdio 模式（本地进程通信）

```powershell
python utils/mcp_knowledge_server.py --transport stdio
```

此模式从标准输入读取 JSON-RPC 请求，适用于 Claude Desktop 等本地客户端。

## 客户端配置

### OpenCode

在项目根目录编辑 `opencode.json`：

**Local 模式（推荐，OpenCode 自动管理进程生命周期，无需手动启动服务器）：**

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "knowledge": {
      "type": "local",
      "command": ["D:\\Development\\PythonProject\\Shared_Env\\python312_opencode\\Scripts\\python.exe", "utils/mcp_knowledge_server.py", "--transport", "stdio"],
      "enabled": true
    }
  }
}
```

**Remote 模式（SSE，需先手动启动服务器）：**

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "knowledge": {
      "type": "remote",
      "url": "http://localhost:8000/sse",
      "enabled": true
    }
  }
}
```

> **提示：**
> - Local 模式：OpenCode 自动启动/关闭 MCP Server 进程，`command` 数组第一项为 Python 解释器完整路径，第二项为脚本相对路径，无需手动 activate 虚拟环境。
> - Remote 模式：需先手动启动服务器（`python utils/mcp_knowledge_server.py`），适合多客户端共享同一服务器实例。
> - 可通过 `opencode mcp list` 查看已配置的 MCP 服务器状态。
> - 详细配置参考：https://opencode.ai/docs/mcp-servers/

### Claude Desktop

**stdio 模式（推荐）：**

编辑配置文件：
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "knowledge": {
      "command": "python",
      "args": ["D:\\Development\\PythonProject\\Practice_workspace\\ai-knowledge-base_v2\\utils\\mcp_knowledge_server.py", "--transport", "stdio"]
    }
  }
}
```

**SSE 模式：**

```json
{
  "mcpServers": {
    "knowledge": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

### Cursor

编辑 `~/.cursor/mcp.json`：

**stdio 模式：**
```json
{
  "mcpServers": {
    "knowledge": {
      "command": "python",
      "args": ["D:\\Development\\PythonProject\\Practice_workspace\\ai-knowledge-base_v2\\utils\\mcp_knowledge_server.py", "--transport", "stdio"]
    }
  }
}
```

**SSE 模式：**
```json
{
  "mcpServers": {
    "knowledge": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

### Continue

编辑 `~/.continue/config.json`：

```json
{
  "experimental": {
    "modelContextProtocolServers": [
      {
        "transport": {
          "type": "sse",
          "url": "http://localhost:8000/sse"
        }
      }
    ]
  }
}
```

## 提供的工具

### 1. search_articles

搜索知识库文章，支持按关键词、来源、标签、评分多维度过滤，各参数可组合使用。

**参数：**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| keyword | string | 否 | - | 搜索关键词，匹配标题、摘要、标签 |
| source | string | 否 | - | 按来源过滤，可选值: `github-search`, `github-trending`, `rss` |
| tag | string | 否 | - | 按标签过滤，精确匹配标签名，如 `agent-framework`, `python`, `llm` |
| min_score | integer | 否 | - | 最低相关度评分过滤，只返回 relevance_score >= min_score 的文章，取值 1-10 |
| limit | integer | 否 | 10 | 返回结果数量限制 |

> **注意：** `keyword`、`source`、`tag`、`min_score` 至少提供一个。

**示例：**

按关键词搜索：
```json
{
  "name": "search_articles",
  "arguments": {
    "keyword": "agent",
    "limit": 5
  }
}
```

按来源过滤：
```json
{
  "name": "search_articles",
  "arguments": {
    "source": "rss"
  }
}
```

按标签过滤：
```json
{
  "name": "search_articles",
  "arguments": {
    "tag": "python"
  }
}
```

按最低评分过滤：
```json
{
  "name": "search_articles",
  "arguments": {
    "min_score": 8
  }
}
```

组合过滤（来源 + 最低评分）：
```json
{
  "name": "search_articles",
  "arguments": {
    "source": "github-trending",
    "min_score": 7
  }
}
```

**返回：**
```json
[
  {
    "id": "39b4c414-0289-432c-9a72-76d138605da2",
    "title": "ai-agents-for-beginners",
    "source": "github-trending",
    "relevance_score": 8,
    "tags": ["ai-agents", "autogen", "semantic-kernel"],
    "summary": "微软推出的入门级AI智能体构建课程..."
  }
]
```

### 2. get_article

根据文章 ID 获取完整内容。

**参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| article_id | string | 是 | 文章唯一标识符 |

**示例：**
```json
{
  "name": "get_article",
  "arguments": {
    "article_id": "39b4c414-0289-432c-9a72-76d138605da2"
  }
}
```

### 3. knowledge_stats

获取知识库统计信息。

**参数：** 无

**返回：**
```json
{
  "total_articles": 100,
  "sources": {
    "github-trending": 19,
    "github-search": 71,
    "rss": 10
  },
  "top_tags": [
    {"tag": "agent-framework", "count": 29},
    {"tag": "open-source", "count": 9},
    {"tag": "python", "count": 8}
  ]
}
```

## 使用示例

在 OpenCode / Claude Desktop 中：

```
用户：帮我搜索关于 agent 的文章
Claude：[调用 search_articles，keyword="agent"]
       找到以下相关文章：
       1. ai-agents-for-beginners - 微软推出的入门级AI智能体构建课程...
       2. ...

用户：来源 rss 的文章有哪些？
Claude：[调用 search_articles，source="rss"]
       找到 10 篇 rss 来源的文章：
       1. Anker made its own chip...
       2. ...

用户：标签 python 的文章有哪些？
Claude：[调用 search_articles，tag="python"]
       找到 8 篇带 python 标签的文章：
       1. ...

用户：高分文章有哪些？
Claude：[调用 search_articles，min_score=8]
       找到 10 篇评分 >= 8 的文章：
       1. ...

用户：查看第一篇文章的详细内容
Claude：[调用 get_article，article_id="..."]
       这篇文章介绍了...
```

## 文章数据格式

知识条目存储在 `knowledge/articles/` 目录，格式如下：

```json
{
  "id": "39b4c414-0289-432c-9a72-76d138605da2",
  "title": "langgenius/dify",
  "source": "github-search",
  "url": "https://github.com/langgenius/dify",
  "summary": "开源 LLM 应用开发平台...",
  "relevance_score": 8,
  "tags": ["agent", "llm", "workflow"],
  "category": "框架",
  "collected_at": "2026-03-26T10:00:00+08:00"
}
```

## 端口配置

默认端口：`8000`

修改端口：编辑 `mcp_knowledge_server.py` 最后一行：
```python
uvicorn.run(starlette_app, host="0.0.0.0", port=9000)  # 改为其他端口
```

## 依赖

- Python 3.12+
- mcp >= 1.13.0
- starlette
- uvicorn

## 故障排查

**问题：启动失败，提示模块不存在**
```
解决：pip install mcp starlette uvicorn
```

**问题：客户端连接不上**
```
解决：
1. 确认服务器已启动
2. 检查防火墙是否放行 8000 端口
3. 确认客户端配置的 URL 正确
```

**问题：搜索无结果**
```
解决：检查 knowledge/articles/ 目录下是否有 JSON 文件
```

**问题：OpenCode stdio 模式连接失败**
```
解决：
1. 确认 opencode.json 中 command 路径指向正确的 Python 解释器完整路径
2. 确认 args 中脚本路径正确
3. 无需手动 activate 虚拟环境，直接使用 venv/Scripts/python.exe 完整路径即可
```

## 测试

### 使用测试脚本（推荐）

测试脚本包含 5 个测试用例：初始化、列出工具、搜索文章、查看统计、完整测试。

```powershell
# 测试 stdio 模式
python utils/test_mcp_client.py --transport stdio

# 测试 SSE 模式（需先启动服务器）
python utils/mcp_knowledge_server.py
# 新开终端
python utils/test_mcp_client.py --transport sse
```

### stdio 模式手动测试

```powershell
# 测试 1：初始化
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | python utils/mcp_knowledge_server.py --transport stdio

# 测试 2：列出工具（需先初始化）
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | python utils/mcp_knowledge_server.py --transport stdio

# 测试 3：搜索文章（需先初始化）
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search_articles","arguments":{"keyword":"agent","limit":3}}}' | python utils/mcp_knowledge_server.py --transport stdio

# 测试 4：按来源搜索
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search_articles","arguments":{"source":"rss"}}}' | python utils/mcp_knowledge_server.py --transport stdio

# 测试 5：查看统计（需先初始化）
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"knowledge_stats","arguments":{}}}' | python utils/mcp_knowledge_server.py --transport stdio

# 完整测试（一次性执行所有）
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"knowledge_stats","arguments":{}}}
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"search_articles","arguments":{"keyword":"agent","limit":3}}}' | python utils/mcp_knowledge_server.py --transport stdio
```

### SSE 模式说明

SSE 模式需要先建立 SSE 连接获取 session_id，再发送消息。测试脚本已自动处理此流程。

手动测试步骤：
1. 启动服务器：`python utils/mcp_knowledge_server.py`
2. 建立 SSE 连接：GET `http://localhost:8000/sse`
3. 从响应中获取 `endpoint` 事件，包含 `/messages/?session_id=xxx`
4. 向该 endpoint POST JSON-RPC 消息

**注意：** SSE 模式下每个测试用例会重新建立连接，与 stdio 模式的行为一致。

## 当前状态

- 已加载文章：100 篇
- 数据来源：github-search (71), github-trending (19), rss (10)
- 热门标签：agent-framework (29), open-source (9), python (8)

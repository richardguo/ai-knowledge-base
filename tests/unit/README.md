# LangGraph 工作流测试文档

## 测试文件结构

```
tests/
├── conftest.py              # pytest 配置，自动加载 .env
└── unit/
    ├── test_state.py        # KBState 状态定义测试 (5 个测试)
    ├── test_model_client.py # LLM 客户端测试 (11 个测试)
    ├── test_nodes.py        # 工作流节点测试 (11 个测试)
    └── test_graph.py        # 工作流组装测试 (13 个测试)
```

## 测试分类

### 1. 不需要 API 的测试（快速）
- `test_state.py` - 全部测试
- `test_model_client.py::TestAccumulateUsage` - token 累加测试
- `test_graph.py::TestRouteReview` - 路由函数测试
- `test_graph.py::TestBuildGraph` - 图构建测试
- `test_graph.py::TestPrintStateSummary` - 摘要打印测试
- `test_nodes.py::TestOrganizeNode::test_organize_node_filters_low_score` - 过滤测试
- `test_nodes.py::TestOrganizeNode::test_organize_node_deduplication` - 去重测试
- `test_nodes.py::TestReviewNode::test_review_node_force_pass_on_max_iteration` - 强制通过测试
- `test_nodes.py::TestReviewNode::test_review_node_no_articles` - 空条目测试

### 2. 需要真实调用 LLM 的测试（慢）
- `test_model_client.py::TestChat` - 对话功能测试
- `test_model_client.py::TestChatJson` - JSON 输出测试
- `test_nodes.py::TestAnalyzeNode` - 分析节点测试
- `test_nodes.py::TestReviewNode::test_review_node_llm_scoring` - 审核评分测试
- `test_nodes.py::TestOrganizeNode::test_organize_node_with_feedback` - 反馈修正测试

### 3. 需要 GitHub Token 的测试
- `test_nodes.py::TestCollectNode` - 采集节点测试

### 4. 端到端工作流测试（最慢）
- `test_graph.py::TestGraphExecution` - 完整工作流测试

## 运行测试

### 快速测试（不调用 API）
```bash
pytest tests/unit/test_state.py tests/unit/test_graph.py::TestRouteReview tests/unit/test_graph.py::TestBuildGraph -v
```

### 运行所有 LLM 测试（需要配置环境变量）
```bash
pytest tests/unit/test_model_client.py -v
```

### 运行节点测试（需要 LLM_API_KEY 和 GITHUB_TOKEN）
```bash
pytest tests/unit/test_nodes.py -v
```

### 运行完整工作流测试（最慢）
```bash
pytest tests/unit/test_graph.py::TestGraphExecution -v
```

### 运行所有测试
```bash
pytest tests/unit -v
```

## 环境变量要求

在运行需要 API 调用的测试前，确保 `.env` 文件包含以下配置：

```env
LLM_API_BASE=https://api.scnet.cn/api/llm/v1
LLM_API_KEY=your_api_key_here
LLM_MODEL_ID=MiniMax-M2.5

GITHUB_TOKEN=your_github_token_here
```

## 测试特点

1. **真实调用 LLM**：测试会实际调用 LLM API，验证完整功能流程
2. **自动跳过**：如果环境变量未配置，相关测试会自动跳过
3. **超时保护**：API 调用设置了 60 秒超时
4. **清理临时文件**：使用 pytest 的 `tmp_path` fixture 自动清理

## 测试覆盖的功能

### workflows/state.py
- TypedDict 类型定义验证
- 字段类型正确性
- 实例创建和访问
- 部分状态更新

### workflows/model_client.py
- 基本对话功能
- 系统提示支持
- 中文对话
- JSON 结构化输出
- 嵌套 JSON 解析
- 分析格式输出
- Markdown 代码块处理
- Token 用量累加

### workflows/nodes.py
- GitHub API 采集
- LLM 分析生成摘要
- 低分过滤
- URL 去重
- 审核反馈修正
- 强制通过机制
- 四维度评分
- 文件保存
- 索引更新

### workflows/graph.py
- 路由函数逻辑
- 图构建完整性
- 节点连接正确性
- 状态转换
- 审核循环机制

## 测试统计

- **总测试数**：40 个（新增测试）
- **快速测试**：23 个
- **需要 LLM**：14 个
- **需要 GitHub Token**：3 个
- **端到端**：3 个

## 常见问题

### Q: 测试运行很慢怎么办？
A: 运行不需要 API 的快速测试，或者使用 `-k` 参数过滤：
```bash
pytest tests/unit -k "not (TestChat or TestChatJson or TestAnalyzeNode)" -v
```

### Q: 如何查看测试覆盖率？
A: 使用 pytest-cov：
```bash
pytest tests/unit --cov=workflows --cov-report=html
```

### Q: 测试失败如何调试？
A: 使用 `-s` 参数查看打印输出：
```bash
pytest tests/unit/test_nodes.py::TestAnalyzeNode::test_analyze_node_basic -v -s
```

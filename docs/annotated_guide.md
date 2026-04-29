# Pydantic + Annotated 使用指南

## 核心问题解答

### Q: 使用 Pydantic 后，还需要 Annotated 吗？

**A: 需要！它们解决不同的问题，可以同时使用。**

| 特性 | Pydantic Field() | Annotated + operator.add |
|------|-----------------|-------------------------|
| **解决的问题** | 数据验证、默认值、约束 | 状态合并策略 |
| **作用时机** | 创建/更新实例时 | LangGraph 合并状态时 |
| **示例** | `Field(default=0, ge=0, le=3)` | `Annotated[list, operator.add]` |

---

## 实际效果演示

### 1. 累加策略（Annotated）

```python
class State(BaseModel):
    # ✅ 自动累加：多个节点的消息会合并
    messages: Annotated[list[str], operator.add] = Field(
        default_factory=list,
        description="消息列表（自动累加）"
    )

# 执行流程：
# NodeA 返回: {"messages": ["来自 NodeA"]}
# NodeB 返回: {"messages": ["来自 NodeB"]}
# 最终状态: {"messages": ["来自 NodeA", "来自 NodeB"]}  # 累加！
```

### 2. 覆盖策略（无 Annotated）

```python
class State(BaseModel):
    # ❌ 直接覆盖：最后一个节点覆盖前面的值
    final_result: str = Field(default="")

# 执行流程：
# NodeA 返回: {"final_result": "Result A"}
# NodeB 返回: {"final_result": "Result B"}
# 最终状态: {"final_result": "Result B"}  # 覆盖！
```

### 3. 组合使用（推荐）

```python
class WorkflowState(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    # 累加 + 验证
    messages: Annotated[list[str], operator.add] = Field(
        default_factory=list,
        description="消息列表"
    )

    # 覆盖 + 约束
    count: int = Field(
        default=0,
        ge=0,
        le=100,
        description="计数器"
    )
```

---



**输出：**

```
[NodeA] 执行
  输入 state.messages: []

[NodeB] 执行
  输入 state.messages: ['来自 NodeA']      # ✅ 累加了 NodeA 的消息

[NodeC] 执行
  输入 state.messages: ['来自 NodeA', '来自 NodeB']  # ✅ 继续累加

最终状态:
  messages: ['来自 NodeA', '来自 NodeB', '来自 NodeC']  # ✅ 全部累加
  scores: [85, 90, 75]                                 # ✅ 全部累加
  final_result: 'NodeC 的结果（覆盖 NodeB）'           # ✅ 最后覆盖
```

---

## KBState 实际应用

### 当前项目需求分析

| 字段 | 更新方式 | 是否需要 Annotated | 原因 |
|------|---------|-------------------|------|
| `sources` | 覆盖 | ❌ | 每次采集替换所有数据 |
| `analyses` | 覆盖 | ❌ | 每次分析替换所有结果 |
| `articles` | 覆盖 | ❌ | 每次整理替换所有条目 |
| `review_feedback` | 覆盖 | ❌ | 最后一次审核结果 |
| `review_passed` | 覆盖 | ❌ | 最后一次审核状态 |
| `iteration` | 覆盖 | ❌ | 当前迭代次数 |
| `cost_tracker` | 手动累加 | ❌ | 复杂对象，节点内处理 |
| `logs` | 自动累加 | ✅ | 收集所有节点日志 |

### 推荐实现

```python
from typing import Annotated
import operator
from pydantic import BaseModel, Field

class KBState(BaseModel):
    """知识库工作流状态。"""

    model_config = ConfigDict(validate_assignment=True)

    # 覆盖字段（不需要 Annotated）
    sources: list[SourceItem] = Field(default_factory=list)
    analyses: list[AnalysisItem] = Field(default_factory=list)
    articles: list[ArticleItem] = Field(default_factory=list)

    review_feedback: str = Field(default="")
    review_passed: bool = Field(default=False)
    iteration: int = Field(default=0, ge=0, le=3)

    # 手动累加（节点内处理）
    cost_tracker: CostTracker = Field(default_factory=CostTracker)

    # ✅ 自动累加日志（推荐添加）
    logs: Annotated[list[str], operator.add] = Field(
        default_factory=list,
        description="执行日志（自动累加）"
    )
```

---

## 完整示例

### 节点函数

```python
def collect_node(state: KBState) -> dict:
    """采集节点。"""
    sources = fetch_from_github()

    # 手动累加 cost
    state.cost_tracker.add_usage(usage)

    return {
        "sources": sources,                    # 覆盖
        "logs": ["[Collect] 采集完成"],        # 累加
        "cost_tracker": state.cost_tracker.model_dump(),  # 手动累加
    }

def analyze_node(state: KBState) -> dict:
    """分析节点。"""
    analyses = analyze_with_llm(state.sources)

    return {
        "analyses": analyses,                  # 覆盖
        "logs": ["[Analyze] 分析完成"],        # 累加
    }
```

### 最终状态

```python
# 执行流程
result = app.invoke(KBState())

# 最终 logs 字段：
result['logs'] = [
    "[Collect] 采集完成",
    "[Analyze] 分析完成",
    "[Organize] 整理完成",
    "[Review] 审核完成",
    "[Save] 保存完成",
]  # ✅ 所有节点的日志自动累加
```

---

## 总结

### ✅ 需要使用 Annotated 的场景

1. **消息/日志收集**
   ```python
   messages: Annotated[list[str], operator.add]
   logs: Annotated[list[str], operator.add]
   ```

2. **统计数据累加**
   ```python
   metrics: Annotated[list[dict], operator.add]
   ```

3. **自定义合并逻辑**
   ```python
   metadata: Annotated[dict, merge_dicts]
   best_score: Annotated[float, max]
   ```

### ❌ 不需要 Annotated 的场景

1. **单值字段**
   ```python
   count: int
   status: str
   ```

2. **需要替换的列表**
   ```python
   sources: list[dict]
   articles: list[dict]
   ```

3. **复杂对象（手动处理）**
   ```python
   cost_tracker: CostTracker  # 在节点内手动累加
   ```

### 💡 最佳实践

```python
# ✅ 推荐：Pydantic + Annotated + Field 三合一
class KBState(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    # 覆盖字段
    sources: list[dict] = Field(default_factory=list)

    # 累加字段
    logs: Annotated[list[str], operator.add] = Field(
        default_factory=list,
        description="执行日志"
    )

    # 验证字段
    iteration: int = Field(default=0, ge=0, le=3)
```

---

## 文件参考

- **演示脚本**：`workflows/langgraph_annotated_fixed.py` ✅ 已验证
- **状态定义**：`workflows/state_with_annotated.py`
- **对比文档**：`workflows/state_annotated_demo.py`

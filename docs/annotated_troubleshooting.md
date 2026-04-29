# Annotated + Pydantic 开发总结

## 遇到的坑和解决方案

### 坑 #1：Pydantic 赋值不验证

**问题描述：**
```python
state = KBState()
state.iteration = 5  # 超出 le=3 的限制，但没有报错
```

**原因分析：**
- Pydantic v2 默认只在创建实例时验证
- 赋值操作（`state.iteration = 5`）不会触发验证

**解决方案：**
```python
class KBState(BaseModel):
    model_config = ConfigDict(validate_assignment=True)  # ✅ 启用赋值验证

    iteration: int = Field(default=0, ge=0, le=3)
```

**验证代码：**
```python
state = KBState()
state.iteration = 5  # ✅ 现在会抛出 ValidationError
```

---

### 坑 #2：Pydantic 对象不支持 .get() 方法

**问题描述：**
```python
def node_a(state: KBState) -> dict:
    messages = state.get('messages', [])  # ❌ AttributeError
```

**错误信息：**
```
AttributeError: 'KBState' object has no attribute 'get'
```

**原因分析：**
- Pydantic BaseModel 不是字典
- 不支持字典方法（`.get()`, `.keys()`, `.items()` 等）

**解决方案：**

**方案 1：类型检查（推荐）**
```python
def node_a(state) -> dict:
    if isinstance(state, dict):
        messages = state.get('messages', [])
    else:
        messages = state.messages  # 使用属性访问

    return {"messages": messages}
```

**方案 2：属性访问**
```python
def node_a(state) -> dict:
    # 如果确定是 Pydantic 对象
    messages = state.messages if hasattr(state, 'messages') else []
    return {"messages": messages}
```

**方案 3：转换为字典**
```python
def node_a(state) -> dict:
    state_dict = state.model_dump() if hasattr(state, 'model_dump') else state
    messages = state_dict.get('messages', [])
    return {"messages": messages}
```

---

### 坑 #3：stream() 只返回部分更新

**问题描述：**
```python
for event in app.stream(initial_state):
    for node_name, output in event.items():
        print(output['messages'])  # 只有 1 条消息，而不是累加的
```

**预期输出：**
```
['Message A', 'Message B', 'Message C']
```

**实际输出：**
```
['Message A']  # NodeA 的返回
['Message B']  # NodeB 的返回
['Message C']  # NodeC 的返回
```

**原因分析：**
- `stream()` 返回的是节点函数的返回值（**部分更新**）
- 不是合并后的完整状态
- LangGraph 内部已经合并了状态，但 stream 事件只包含部分更新

**可视化说明：**
```
初始状态: messages = []

NodeA 返回: {"messages": ["A"]}
  ↓ LangGraph 内部合并
当前状态: messages = ["A"]

stream 事件: {"messages": ["A"]}  ← 这是 NodeA 的返回值

NodeB 接收: state.messages = ["A"]  ← 已累加 NodeA 的消息
NodeB 返回: {"messages": ["B"]}
  ↓ LangGraph 内部合并
当前状态: messages = ["A", "B"]

stream 事件: {"messages": ["B"]}  ← 这是 NodeB 的返回值（部分更新）
```

**解决方案：**

**方案 1：使用 invoke() 获取最终状态**
```python
result = app.invoke(initial_state)
print(result['messages'])  # ['A', 'B', 'C']
```

**方案 2：在节点内部打印当前状态**
```python
def node_b(state) -> dict:
    if isinstance(state, dict):
        current_messages = state.get('messages', [])
    else:
        current_messages = state.messages

    print(f"当前累积的消息: {current_messages}")  # 这里可以看到累加效果

    return {"messages": ["B"]}
```

**方案 3：手动维护累积状态（不推荐）**
```python
accumulated = {"messages": []}

for event in app.stream(initial_state):
    for node_name, output in event.items():
        # 手动合并
        if 'messages' in output:
            accumulated['messages'].extend(output['messages'])

print(accumulated['messages'])  # ['A', 'B', 'C']
```

#### stream() 事件的完整结构

**事件格式：**
```
stream() 每次迭代返回: {node_name: partial_update}
```

- `node_name`：刚执行完的节点名称（字符串）
- `partial_update`：该节点函数的返回值（dict），**只包含该节点显式返回的字段**

**不同字段类型在 stream 事件中的表现：**

| 字段类型 | 节点返回示例 | stream 事件中看到 | LangGraph 内部实际状态 |
|---------|------------|-----------------|---------------------|
| `Annotated[list, operator.add]` 累加字段 | `{"messages": ["B"]}` | 仅增量 `["B"]` | 累加后 `["A", "B"]` |
| 覆盖字段（无 Annotated） | `{"final_result": "B"}` | 新值 `"B"` | 被覆盖为 `"B"` |
| 节点未返回的字段 | 不在返回值中 | 不在事件中 | 保持原值不变 |

**核心要点：**

1. **stream 事件 = 节点返回值**，不是完整状态快照
2. **Annotated 累加字段**：stream 只显示本节点的增量，不显示累加结果
3. **覆盖字段**：stream 显示新值，但从事件本身无法区分"新增"还是"覆盖"
4. **未返回的字段**不会出现在 stream 事件中
5. 如需完整状态，用 `invoke()` 或手动累积 stream 事件

**stream() vs invoke() 对比：**

| | `stream()` | `invoke()` |
|---|---|---|
| 返回时机 | 每个节点执行完立即 yield | 全部节点执行完一次性返回 |
| 返回内容 | 节点的部分更新（增量） | 最终完整状态（累加结果） |
| 事件格式 | `{node_name: partial_update}` | `{field: final_value, ...}` |
| 适用场景 | 监控进度、调试节点输出、统计执行次数 | 获取最终结果 |
| 循环图支持 | 可以观察每次迭代经过哪些节点 | 只能看到最终结果 |

---

## 完整代码示例

### 正确的 Pydantic + Annotated 使用方式

```python
from typing import Annotated
import operator
from pydantic import BaseModel, ConfigDict, Field


class KBState(BaseModel):
    """知识库工作流状态（最佳实践）。"""

    # ✅ 必须配置：启用赋值验证
    model_config = ConfigDict(validate_assignment=True)

    # ===== 覆盖字段（不需要 Annotated）=====
    sources: list[dict] = Field(
        default_factory=list,
        description="采集的原始数据（覆盖）"
    )
    analyses: list[dict] = Field(
        default_factory=list,
        description="分析结果（覆盖）"
    )
    articles: list[dict] = Field(
        default_factory=list,
        description="知识条目（覆盖）"
    )

    # ===== 累加字段（需要 Annotated）=====
    logs: Annotated[list[str], operator.add] = Field(
        default_factory=list,
        description="执行日志（累加）"
    )

    # ===== 单值字段（覆盖）=====
    iteration: int = Field(
        default=0,
        ge=0,      # 大于等于 0
        le=3,      # 小于等于 3
        description="迭代次数"
    )
    review_passed: bool = Field(default=False)

    # ===== 手动累加字段（复杂对象）=====
    total_tokens: int = Field(default=0, ge=0)


# ===== 节点函数 =====

def collect_node(state) -> dict:
    """采集节点。"""
    # ✅ 正确处理 state 类型
    if isinstance(state, dict):
        current_tokens = state.get('total_tokens', 0)
    else:
        current_tokens = state.total_tokens if hasattr(state, 'total_tokens') else 0

    print(f"[Collect] 当前 tokens: {current_tokens}")

    return {
        "sources": [{"title": "test"}],          # 覆盖
        "logs": ["[Collect] 采集完成"],          # 累加
        "total_tokens": current_tokens + 100,    # 手动累加
    }


def analyze_node(state) -> dict:
    """分析节点。"""
    if isinstance(state, dict):
        current_tokens = state.get('total_tokens', 0)
        current_logs = state.get('logs', [])
    else:
        current_tokens = state.total_tokens if hasattr(state, 'total_tokens') else 0
        current_logs = state.logs if hasattr(state, 'logs') else []

    print(f"[Analyze] 当前 tokens: {current_tokens}")
    print(f"[Analyze] 当前 logs 数量: {len(current_logs)}")  # 应该有 1 条

    return {
        "analyses": [{"url": "test", "score": 0.8}],  # 覆盖
        "logs": ["[Analyze] 分析完成"],                # 累加
        "total_tokens": current_tokens + 200,
    }


# ===== 构建工作流 =====

from langgraph.graph import END, StateGraph

graph = StateGraph(KBState)

graph.add_node("collect", collect_node)
graph.add_node("analyze", analyze_node)

graph.set_entry_point("collect")
graph.add_edge("collect", "analyze")
graph.add_edge("analyze", END)

app = graph.compile()


# ===== 执行工作流 =====

# 初始状态
initial_state = KBState()

# ✅ 使用 invoke() 获取最终状态
result = app.invoke(initial_state.model_dump())

print("\n最终状态:")
print(f"  logs: {result['logs']}")           # 2 条日志
print(f"  total_tokens: {result['total_tokens']}")  # 300

# ✅ 验证
assert len(result['logs']) == 2
assert result['total_tokens'] == 300
```

---

## 快速参考

### 何时使用 Annotated

| 场景 | 是否需要 Annotated | 示例 |
|------|-------------------|------|
| 消息/日志累加 | ✅ 需要 | `Annotated[list[str], operator.add]` |
| 统计数据累加 | ✅ 需要 | `Annotated[list[dict], operator.add]` |
| 字典合并 | ✅ 需要 | `Annotated[dict, merge_dicts]` |
| 保留最大值 | ✅ 需要 | `Annotated[float, max]` |
| 单值字段 | ❌ 不需要 | `count: int` |
| 需要替换的列表 | ❌ 不需要 | `sources: list[dict]` |
| 复杂对象 | ❌ 手动处理 | `cost_tracker: CostTracker` |

### 节点函数编写规范

```python
def node_function(state) -> dict:
    """节点函数模板。"""

    # 1️⃣ 正确处理 state 类型
    if isinstance(state, dict):
        field_value = state.get('field_name', default_value)
    else:
        field_value = state.field_name if hasattr(state, 'field_name') else default_value

    # 2️⃣ 在节点内部打印状态（可选）
    print(f"[NodeName] 当前状态: {field_value}")

    # 3️⃣ 返回部分更新
    return {
        "field_name": new_value,  # 会根据 Annotated 策略合并
    }
```

### 执行工作流的正确方式

```python
# ✅ 获取最终状态
result = app.invoke(KBState().model_dump())

# ✅ 流式执行 + 打印日志
for event in app.stream(KBState().model_dump()):
    for node_name, partial_update in event.items():
        print(f"[{node_name}] 部分更新: {partial_update}")
        # 注意：这不是完整状态，是部分更新
```

---

## 测试验证

所有演示代码已通过测试：

```bash
python workflows/annotated_complete_demo.py
```

**输出结果：**
```
✅ TypedDict 版本验证通过
✅ Pydantic 版本验证通过
✅ 知识库工作流验证通过
✅ 自定义 Reducer 验证通过
所有演示完成 ✅
```

---

## 文件清单

| 文件 | 说明 | 用途 |
|------|------|------|
| `annotated_complete_demo.py` | 完整演示脚本（带详细注释） | 学习和理解 |
| `langgraph_annotated_fixed.py` | 简洁演示脚本 | 快速验证 |
| `state_with_annotated.py` | Pydantic 状态定义（含 Annotated） | 实际使用 |
| `annotated_guide.md` | 使用指南 | 文档参考 |

---

## 总结

### ✅ 正确理解

1. **Annotated 定义合并策略**：告诉 LangGraph 如何合并部分更新
2. **Field 定义验证和默认值**：Pydantic 的数据约束
3. **两者可以同时使用**：互不冲突，各司其职

### ❌ 常见误区

1. 误以为 Pydantic 会自动处理状态合并
2. 在 stream() 事件中期望看到完整状态
3. 用字典方法访问 Pydantic 对象

### 💡 最佳实践

1. 设置 `validate_assignment=True`
2. 统一处理 state 类型（dict 或 BaseModel）
3. 使用 invoke() 获取最终状态
4. 在节点内部打印当前状态验证

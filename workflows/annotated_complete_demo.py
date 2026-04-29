"""LangGraph + Pydantic + Annotated 完整演示（带详细注释）。"""

import operator
import sys
from pathlib import Path
from typing import Annotated, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# 第一部分：理解 Annotated 的作用
# ============================================================

print("=" * 80)
print("第一部分：理解 Annotated 的作用")
print("=" * 80)
print("""
【核心概念】
Annotated[list, operator.add] 是 LangGraph 的状态合并策略：
- 默认行为：节点返回的部分更新会直接覆盖原字段
- 累加行为：节点返回的部分更新会累加到原字段

【为什么需要？】
场景：多个节点都要添加消息到 messages 列表
- 不用 Annotated：后面的节点会覆盖前面的消息
- 使用 Annotated：所有节点的消息都会累加

【类比理解】
- 默认行为 = 赋值操作：x = new_value（覆盖）
- 累加行为 = 累加操作：x += new_value（累加）
""")


# ============================================================
# 第二部分：TypedDict 版本（LangGraph 官方推荐方式）
# ============================================================

print("\n" + "=" * 80)
print("第二部分：TypedDict 版本（官方示例）")
print("=" * 80)


class TypedDictState(TypedDict):
    """
    TypedDict 版本的状态定义。

    【优点】
    1. 零依赖，Python 原生支持
    2. LangGraph 官方文档的主要示例
    3. 简单直观

    【语法说明】
    messages: Annotated[list[str], operator.add]
    - Annotated: Python 3.9+ 的类型注解增强
    - list[str]: 字段类型
    - operator.add: 合并策略（累加）

    【注意事项】
    1. TypedDict 本身不提供运行时验证
    2. 没有默认值机制
    3. 必须手动初始化所有字段
    """
    # ✅ 累加策略：多个节点的消息会自动合并
    messages: Annotated[list[str], operator.add]

    # ✅ 累加策略：多个节点的分数会自动合并
    scores: Annotated[list[int], operator.add]

    # ❌ 覆盖策略：默认行为，最后一个节点的值覆盖前面的
    final_result: str


def demo_typeddict_version():
    """
    演示 TypedDict 版本的实际效果。

    【运行结果】
    messages 会累加所有节点的消息
    scores 会累加所有节点的分数
    final_result 会被最后一个节点覆盖
    """
    print("\n>>> TypedDict 版本演示")

    # 构建工作流
    graph = StateGraph(TypedDictState)

    # 定义节点函数
    # 注意：节点函数的参数是当前状态（字典格式）
    def node_a(state) -> dict:
        """
        节点 A。

        【重要】
        节点返回的是部分状态更新（partial update）
        LangGraph 会根据 Annotated 指定的策略合并这些更新
        """
        print("  [TypedDict-NodeA] 执行")
        # 返回部分更新
        return {
            "messages": ["Message from A"],  # 会累加
            "scores": [85],                   # 会累加
            "final_result": "Result A",       # 会被覆盖
        }

    def node_b(state) -> dict:
        """
        节点 B。

        【注意】
        这里可以看到 state 已经包含了 NodeA 的更新
        messages 和 scores 已经累加了 NodeA 的值
        """
        print("  [TypedDict-NodeB] 执行")
        print(f"    当前 messages: {state.get('messages', [])}")  # 应该有 NodeA 的消息
        print(f"    当前 scores: {state.get('scores', [])}")      # 应该有 NodeA 的分数

        return {
            "messages": ["Message from B"],
            "scores": [90],
            "final_result": "Result B (覆盖了 Result A)",
        }

    # 添加节点到图
    graph.add_node("node_a", node_a)
    graph.add_node("node_b", node_b)

    # 设置入口点和边
    graph.set_entry_point("node_a")
    graph.add_edge("node_a", "node_b")
    graph.add_edge("node_b", END)

    # 编译图
    app = graph.compile()

    # 执行工作流
    # 注意：初始状态可以是空字典，LangGraph 会自动处理
    result = app.invoke({})

    print("\n  最终结果:")
    print(f"    messages: {result['messages']}")
    print(f"    scores: {result['scores']}")
    print(f"    final_result: {result['final_result']}")

    # 验证结果
    assert len(result['messages']) == 2, "messages 应该有 2 条"
    assert len(result['scores']) == 2, "scores 应该有 2 个"
    assert result['final_result'] == "Result B (覆盖了 Result A)", "final_result 应该被覆盖"

    print("\n  ✅ TypedDict 版本验证通过")


demo_typeddict_version()


# ============================================================
# 第三部分：Pydantic 版本（推荐方式）
# ============================================================

print("\n" + "=" * 80)
print("第三部分：Pydantic 版本（推荐）")
print("=" * 80)
print("""
【为什么推荐 Pydantic？】
1. 运行时验证：自动检查数据有效性
2. 默认值：不需要手动初始化所有字段
3. 类型安全：IDE 自动补全更强大
4. 序列化：model_dump(), model_dump_json() 简单易用

【Pydantic + Annotated 的正确用法】
messages: Annotated[list[str], operator.add] = Field(
    default_factory=list,
    description="消息列表"
)

说明：
- Annotated[list, operator.add] 定义合并策略
- Field(...) 定义验证和默认值
- 两者可以同时使用！
""")


class PydanticState(BaseModel):
    """
    Pydantic 版本的状态定义。

    【重要配置】
    model_config = ConfigDict(validate_assignment=True)
    这确保了赋值时也会进行验证

    【遇到的坑 #1：validate_assignment 默认为 False】
    问题描述：
        state.iteration = 5  # 超出 le=3 的限制，但不会报错

    原因：
        Pydantic v2 默认只在创建实例时验证，赋值时不验证

    解决：
        设置 validate_assignment=True
    """
    model_config = ConfigDict(validate_assignment=True)

    # ✅ 累加策略 + 默认值
    messages: Annotated[list[str], operator.add] = Field(
        default_factory=list,
        description="消息列表（自动累加）"
    )

    # ✅ 累加策略 + 默认值
    scores: Annotated[list[int], operator.add] = Field(
        default_factory=list,
        description="分数列表（自动累加）"
    )

    # ❌ 覆盖策略 + 约束
    iteration: int = Field(
        default=0,
        ge=0,      # 大于等于 0
        le=3,      # 小于等于 3
        description="迭代次数"
    )


def demo_pydantic_version():
    """
    演示 Pydantic 版本的实际效果。

    【遇到的坑 #2：Pydantic 对象不支持 .get() 方法】
    问题描述：
        messages = state.get('messages', [])  # AttributeError

    原因：
        Pydantic BaseModel 不是字典，不支持字典方法

    解决：
        方案1：使用属性访问：state.messages
        方案2：先转为字典：state.model_dump().get('messages', [])
        方案3：类型检查（推荐）
    """
    print("\n>>> Pydantic 版本演示")

    # 构建工作流
    graph = StateGraph(PydanticState)

    # 定义节点函数
    def node_a(state) -> dict:
        """
        节点 A。

        【重要】
        LangGraph 会将 Pydantic 对象或字典传递给节点函数
        需要处理两种情况
        """
        print("  [Pydantic-NodeA] 执行")

        # 【坑 #2 的解决方案】类型检查
        if isinstance(state, dict):
            messages = state.get('messages', [])
        else:
            # Pydantic 对象，使用属性访问
            messages = state.messages if hasattr(state, 'messages') else []

        print(f"    输入 messages: {messages}")

        return {
            "messages": ["Message from A"],
            "scores": [85],
            "iteration": 1,
        }

    def node_b(state) -> dict:
        """节点 B。"""
        print("  [Pydantic-NodeB] 执行")

        # 获取当前状态（使用统一的访问方式）
        if isinstance(state, dict):
            messages = state.get('messages', [])
            scores = state.get('scores', [])
        else:
            messages = state.messages if hasattr(state, 'messages') else []
            scores = state.scores if hasattr(state, 'scores') else []

        print(f"    输入 messages: {messages}")  # 应该有 NodeA 的消息
        print(f"    输入 scores: {scores}")      # 应该有 NodeA 的分数

        return {
            "messages": ["Message from B"],
            "scores": [90],
            "iteration": 2,
        }

    def node_c(state) -> dict:
        """节点 C。"""
        print("  [Pydantic-NodeC] 执行")

        if isinstance(state, dict):
            messages = state.get('messages', [])
            scores = state.get('scores', [])
        else:
            messages = state.messages if hasattr(state, 'messages') else []
            scores = state.scores if hasattr(state, 'scores') else []

        print(f"    输入 messages: {messages}")  # 应该有 NodeA 和 NodeB 的消息
        print(f"    输入 scores: {scores}")      # 应该有 NodeA 和 NodeB 的分数

        return {
            "messages": ["Message from C"],
            "scores": [75],
            "iteration": 3,
        }

    # 添加节点
    graph.add_node("node_a", node_a)
    graph.add_node("node_b", node_b)
    graph.add_node("node_c", node_c)

    # 设置边
    graph.set_entry_point("node_a")
    graph.add_edge("node_a", "node_b")
    graph.add_edge("node_b", "node_c")
    graph.add_edge("node_c", END)

    # 编译
    app = graph.compile()

    # 执行
    # 注意：初始状态使用 Pydantic 对象或空字典都可以
    result = app.invoke(PydanticState().model_dump())

    print("\n  最终结果:")
    print(f"    messages: {result['messages']}")
    print(f"    scores: {result['scores']}")
    print(f"    iteration: {result['iteration']}")

    # 验证
    assert len(result['messages']) == 3, f"messages 应该有 3 条，实际: {len(result['messages'])}"
    assert len(result['scores']) == 3, f"scores 应该有 3 个，实际: {len(result['scores'])}"
    assert result['iteration'] == 3, "iteration 应该是 3"

    print("\n  ✅ Pydantic 版本验证通过")


demo_pydantic_version()


# ============================================================
# 第四部分：stream() vs invoke() 的区别
# ============================================================

print("\n" + "=" * 80)
print("第四部分：stream() vs invoke() 的区别")
print("=" * 80)
print("""
【遇到的坑 #3：stream() 只返回部分更新】
问题描述：
    使用 stream() 迭代时，每个事件只包含当前节点的部分更新
    看起来 messages 没有累加，每次都只有一个值

原因分析：
    stream() 返回的是节点函数的返回值（部分更新）
    而不是合并后的完整状态

    例如：
    NodeA 返回: {"messages": ["A"]}
    stream 事件: {"messages": ["A"]}  # 这是部分更新，不是完整状态

    但 LangGraph 内部已经将这个更新合并到状态中了
    下一个节点看到的是累加后的状态

正确理解：
    - invoke(): 返回最终完整状态
    - stream(): 返回每个节点的部分更新（用于打印日志）

解决方案：
    方案1：使用 invoke() 获取最终状态
    方案2：在节点函数中打印当前状态（而不是依赖 stream 事件）
    方案3：使用 stream() 但手动维护累积状态
""")


def demo_stream_vs_invoke():
    """演示 stream() 和 invoke() 的区别。

    【关键知识点】
    stream() 事件格式: {node_name: partial_update}
    - partial_update 是节点函数的返回值，只包含该节点显式返回的字段
    - Annotated 累加字段：stream 只显示增量，不显示累加结果
    - 覆盖字段：stream 显示新值
    - 未返回的字段不出现在 stream 事件中
    """

    class SimpleState(BaseModel):
        model_config = ConfigDict(validate_assignment=True)
        messages: Annotated[list[str], operator.add] = Field(default_factory=list)
        step_name: str = Field(default="")

    graph = StateGraph(SimpleState)

    def node_a(state):
        if isinstance(state, dict):
            current_messages = state.get('messages', [])
        else:
            current_messages = state.messages if hasattr(state, 'messages') else []

        print(f"  [NodeA] 内部看到的 messages: {current_messages}")
        return {"messages": ["A"], "step_name": "collect"}

    def node_b(state):
        if isinstance(state, dict):
            current_messages = state.get('messages', [])
        else:
            current_messages = state.messages if hasattr(state, 'messages') else []

        print(f"  [NodeB] 内部看到的 messages: {current_messages}")
        return {"messages": ["B"], "step_name": "analyze"}

    graph.add_node("node_a", node_a)
    graph.add_node("node_b", node_b)
    graph.set_entry_point("node_a")
    graph.add_edge("node_a", "node_b")
    graph.add_edge("node_b", END)

    app = graph.compile()

    print("\n>>> 使用 stream() - 逐节点返回部分更新:")
    print("    事件格式: {node_name: partial_update}\n")
    for event in app.stream({}):
        for node_name, partial_update in event.items():
            print(f"  节点 {node_name} 完成:")
            print(f"    partial_update = {partial_update}")
            if "messages" in partial_update:
                print(f"    → messages (Annotated累加): 仅增量 {partial_update['messages']}")
            if "step_name" in partial_update:
                print(f"    → step_name (覆盖): 新值 '{partial_update['step_name']}'")

    print("\n>>> 使用 invoke() - 返回最终完整状态:")
    result = app.invoke({})
    print(f"  最终状态: {result}")
    print(f"    messages: {result['messages']}  (累加结果)")
    print(f"    step_name: '{result['step_name']}'  (被覆盖为最后一个节点的值)")

    print("\n>>> 手动累积 stream 事件 (模拟 invoke):")
    accumulated = {"messages": [], "step_name": ""}
    for event in app.stream({}):
        for node_name, partial_update in event.items():
            if "messages" in partial_update:
                accumulated["messages"].extend(partial_update["messages"])
            if "step_name" in partial_update:
                accumulated["step_name"] = partial_update["step_name"]
    print(f"  手动累积结果: {accumulated}")
    print(f"  与 invoke() 一致: {accumulated == result}")

    assert result['messages'] == ["A", "B"], "messages 应该累加"
    assert result['step_name'] == "analyze", "step_name 应该被覆盖"


demo_stream_vs_invoke()


# ============================================================
# 第五部分：实际应用场景
# ============================================================

print("\n" + "=" * 80)
print("第五部分：实际应用场景")
print("=" * 80)


class KnowledgeBaseState(BaseModel):
    """
    知识库工作流状态（实际应用）。

    【字段设计决策】

    1. sources, analyses, articles - 使用覆盖策略
       原因：每个节点会重新生成完整的列表
       例如：collect_node 返回所有采集到的数据
            analyze_node 返回所有分析结果
            organize_node 返回所有整理后的条目

    2. logs - 使用累加策略
       原因：每个节点都要添加自己的日志
       最终需要看到所有节点的执行日志

    3. cost_tracker - 手动累加
       原因：这是复杂对象，包含多个字段
       在节点内部手动累加更清晰可控

    4. iteration, review_passed - 使用覆盖策略
       原因：单值字段，每次更新都是新值
    """
    model_config = ConfigDict(validate_assignment=True)

    # ===== 覆盖字段 =====
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

    # ===== 累加字段 =====
    logs: Annotated[list[str], operator.add] = Field(
        default_factory=list,
        description="执行日志（累加）"
    )

    # ===== 单值字段 =====
    review_passed: bool = Field(default=False)
    iteration: int = Field(default=0, ge=0, le=3)

    # ===== 手动累加字段 =====
    total_tokens: int = Field(default=0, ge=0)


def demo_knowledge_base_workflow():
    """演示知识库工作流的实际效果。"""
    print("\n>>> 知识库工作流演示")

    graph = StateGraph(KnowledgeBaseState)

    def collect_node(state):
        """
        采集节点。

        【设计决策】
        - sources: 覆盖（本次采集的所有数据）
        - logs: 累加（添加本节点日志）
        - total_tokens: 手动累加（累加本次 API 调用的 token）
        """
        print("  [Collect] 执行")

        # 模拟采集数据
        sources = [
            {"title": "repo-1", "url": "https://github.com/test/repo-1"},
            {"title": "repo-2", "url": "https://github.com/test/repo-2"},
        ]

        # 模拟 token 使用
        tokens_used = 100

        return {
            "sources": sources,                              # 覆盖
            "logs": ["[Collect] 采集了 2 条数据"],          # 累加
            "total_tokens": state.total_tokens + tokens_used,  # 手动累加
        }

    def analyze_node(state):
        """
        分析节点。

        【注意】
        sources 字段已经被 collect_node 覆盖
        logs 字段已经累加了 collect_node 的日志
        """
        print("  [Analyze] 执行")

        if isinstance(state, dict):
            current_logs = state.get('logs', [])
            current_tokens = state.get('total_tokens', 0)
        else:
            current_logs = state.logs if hasattr(state, 'logs') else []
            current_tokens = state.total_tokens if hasattr(state, 'total_tokens') else 0

        print(f"    当前 logs 数量: {len(current_logs)}")  # 应该有 1 条
        print(f"    当前 total_tokens: {current_tokens}")  # 应该是 100

        # 模拟分析
        analyses = [
            {"url": "https://github.com/test/repo-1", "score": 0.8},
            {"url": "https://github.com/test/repo-2", "score": 0.6},
        ]

        tokens_used = 500

        return {
            "analyses": analyses,                            # 覆盖
            "logs": ["[Analyze] 分析了 2 条数据"],          # 累加
            "total_tokens": state.total_tokens + tokens_used,
        }

    def organize_node(state):
        """整理节点。"""
        print("  [Organize] 执行")

        # 过滤低分
        if isinstance(state, dict):
            analyses = state.get('analyses', [])
        else:
            analyses = state.analyses if hasattr(state, 'analyses') else []

        articles = [a for a in analyses if a.get('score', 0) >= 0.7]

        return {
            "articles": articles,                            # 覆盖
            "logs": ["[Organize] 过滤后剩余 1 条"],          # 累加
        }

    def save_node(state):
        """保存节点。"""
        print("  [Save] 执行")
        return {
            "logs": ["[Save] 保存完成"],                     # 累加
        }

    # 构建图
    graph.add_node("collect", collect_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("organize", organize_node)
    graph.add_node("save", save_node)

    graph.set_entry_point("collect")
    graph.add_edge("collect", "analyze")
    graph.add_edge("analyze", "organize")
    graph.add_edge("organize", "save")
    graph.add_edge("save", END)

    app = graph.compile()

    # 执行
    result = app.invoke(KnowledgeBaseState().model_dump())

    print("\n  最终结果:")
    print(f"    sources: {len(result['sources'])} 条")
    print(f"    analyses: {len(result['analyses'])} 条")
    print(f"    articles: {len(result['articles'])} 条")
    print(f"    logs: {result['logs']}")
    print(f"    total_tokens: {result['total_tokens']}")

    # 验证
    assert len(result['sources']) == 2, "sources 应该有 2 条"
    assert len(result['analyses']) == 2, "analyses 应该有 2 条"
    assert len(result['articles']) == 1, "articles 应该有 1 条（过滤后）"
    assert len(result['logs']) == 4, f"logs 应该有 4 条，实际: {len(result['logs'])}"
    assert result['total_tokens'] == 600, "total_tokens 应该是 600"

    print("\n  ✅ 知识库工作流验证通过")


demo_knowledge_base_workflow()


# ============================================================
# 第六部分：自定义 Reducer
# ============================================================

print("\n" + "=" * 80)
print("第六部分：自定义 Reducer")
print("=" * 80)
print("""
【高级用法】
除了 operator.add，还可以自定义合并函数

常见场景：
1. 字典合并：merge_dicts
2. 保留最大值：max
3. 保留最小值：min
4. 去重合并：unique_merge
""")


def merge_dicts(left: dict, right: dict) -> dict:
    """
    自定义 Reducer：合并字典。

    【参数说明】
    - left: 原有值
    - right: 新值（节点返回的）

    【返回值】
    合并后的值
    """
    return {**left, **right}


def keep_max(left: float, right: float) -> float:
    """
    自定义 Reducer：保留最大值。

    【应用场景】
    best_score: 多个节点都要更新分数，保留最高的那个
    """
    return max(left, right)


class AdvancedState(BaseModel):
    """高级状态：使用自定义 Reducer。"""
    model_config = ConfigDict(validate_assignment=True)

    # 字典合并
    metadata: Annotated[dict, merge_dicts] = Field(default_factory=dict)

    # 保留最大值
    best_score: Annotated[float, keep_max] = Field(default=0.0, ge=0.0, le=1.0)

    # 累加列表
    logs: Annotated[list[str], operator.add] = Field(default_factory=list)


def demo_custom_reducer():
    """演示自定义 Reducer。"""
    print("\n>>> 自定义 Reducer 演示")

    graph = StateGraph(AdvancedState)

    def node_a(state):
        print("  [NodeA] 执行")
        return {
            "metadata": {"key1": "value1", "shared": "from_a"},
            "best_score": 0.7,
            "logs": ["A"],
        }

    def node_b(state):
        print("  [NodeB] 执行")

        # 查看当前 metadata
        if isinstance(state, dict):
            current_metadata = state.get('metadata', {})
            current_score = state.get('best_score', 0.0)
        else:
            current_metadata = state.metadata if hasattr(state, 'metadata') else {}
            current_score = state.best_score if hasattr(state, 'best_score') else 0.0

        print(f"    当前 metadata: {current_metadata}")  # 应该有 key1
        print(f"    当前 best_score: {current_score}")   # 应该是 0.7

        return {
            "metadata": {"key2": "value2", "shared": "from_b"},  # 会合并
            "best_score": 0.8,  # 更大，会保留
            "logs": ["B"],
        }

    def node_c(state):
        print("  [NodeC] 执行")

        if isinstance(state, dict):
            current_metadata = state.get('metadata', {})
            current_score = state.get('best_score', 0.0)
        else:
            current_metadata = state.metadata if hasattr(state, 'metadata') else {}
            current_score = state.best_score if hasattr(state, 'best_score') else 0.0

        print(f"    当前 metadata: {current_metadata}")  # 应该有 key1 和 key2
        print(f"    当前 best_score: {current_score}")   # 应该是 0.8

        return {
            "metadata": {"key3": "value3"},
            "best_score": 0.6,  # 更小，不会更新
            "logs": ["C"],
        }

    graph.add_node("node_a", node_a)
    graph.add_node("node_b", node_b)
    graph.add_node("node_c", node_c)

    graph.set_entry_point("node_a")
    graph.add_edge("node_a", "node_b")
    graph.add_edge("node_b", "node_c")
    graph.add_edge("node_c", END)

    app = graph.compile()
    result = app.invoke(AdvancedState().model_dump())

    print("\n  最终结果:")
    print(f"    metadata: {result['metadata']}")
    print(f"    best_score: {result['best_score']}")
    print(f"    logs: {result['logs']}")

    # 验证
    assert "key1" in result['metadata'], "metadata 应该有 key1"
    assert "key2" in result['metadata'], "metadata 应该有 key2"
    assert "key3" in result['metadata'], "metadata 应该有 key3"
    assert result['metadata']['shared'] == "from_b", "字典合并，后者覆盖前者"
    assert result['best_score'] == 0.8, "best_score 应该保留最大值 0.8"
    assert result['logs'] == ["A", "B", "C"], "logs 应该累加"

    print("\n  ✅ 自定义 Reducer 验证通过")


demo_custom_reducer()


# ============================================================
# 总结
# ============================================================

print("\n" + "=" * 80)
print("总结")
print("=" * 80)
print("""
【关键要点】

1. Annotated 和 Field 可以同时使用
   messages: Annotated[list[str], operator.add] = Field(default_factory=list)

2. Annotated 的作用
   - 定义状态合并策略
   - operator.add: 累加
   - 默认: 覆盖
   - 自定义函数: 自定义逻辑

3. 遇到的坑和解决方案

   坑 #1: Pydantic 赋值不验证
   解决: 设置 validate_assignment=True

   坑 #2: Pydantic 对象不支持 .get()
   解决: 类型检查，区分 dict 和 BaseModel

   坑 #3: stream() 只返回部分更新
   解决: 使用 invoke() 获取最终状态，或在节点内部打印当前状态
         stream() 事件格式: {node_name: partial_update}
         Annotated 累加字段在 stream 中只有增量，覆盖字段显示新值

4. 实际应用建议

   累加字段（需要 Annotated）:
   - messages, logs, metrics, events

   覆盖字段（不需要 Annotated）:
   - sources, analyses, articles
   - 单值字段: count, status, iteration

   手动累加字段:
   - 复杂对象: cost_tracker, metadata

5. 最佳实践

   a) 使用 Pydantic 获得验证和类型安全
   b) 使用 Annotated 定义合并策略
   c) 在节点函数中统一处理 state 类型
    d) 使用 invoke() 获取最终状态，stream() 用于日志和监控
         - stream 事件是节点返回值（部分更新），不是完整状态
         - Annotated 累加字段在 stream 中只有增量
         - 手动累积 stream 事件可还原完整状态
""")


print("\n" + "=" * 80)
print("所有演示完成 ✅")
print("=" * 80)

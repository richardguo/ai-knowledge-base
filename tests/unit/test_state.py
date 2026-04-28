"""KBState 状态定义单元测试。"""

import pytest

from workflows.state import KBState


class TestKBState:
    """KBState 类型定义测试。"""

    def test_kbstate_is_typed_dict(self):
        """验证 KBState 是 TypedDict 子类。"""
        assert hasattr(KBState, "__annotations__")
        annotations = KBState.__annotations__

        assert "sources" in annotations
        assert "analyses" in annotations
        assert "articles" in annotations
        assert "review_feedback" in annotations
        assert "review_passed" in annotations
        assert "iteration" in annotations
        assert "cost_tracker" in annotations

    def test_kbstate_field_types(self):
        """验证各字段类型定义正确。"""
        annotations = KBState.__annotations__

        assert annotations["sources"] == list[dict]
        assert annotations["analyses"] == list[dict]
        assert annotations["articles"] == list[dict]
        assert annotations["review_feedback"] == str
        assert annotations["review_passed"] == bool
        assert annotations["iteration"] == int
        assert annotations["cost_tracker"] == dict

    def test_kbstate_instance_creation(self):
        """验证可以创建符合类型的实例。"""
        state: KBState = {
            "sources": [{"title": "test", "url": "https://example.com"}],
            "analyses": [{"summary": "测试摘要", "tags": ["test"]}],
            "articles": [{"id": "test", "title": "测试条目"}],
            "review_feedback": "",
            "review_passed": False,
            "iteration": 0,
            "cost_tracker": {"total_tokens": 100},
        }

        assert state["sources"][0]["title"] == "test"
        assert state["iteration"] == 0
        assert state["review_passed"] is False

    def test_kbstate_optional_access(self):
        """验证字段可以安全访问和修改。"""
        state: KBState = {
            "sources": [],
            "analyses": [],
            "articles": [],
            "review_feedback": "",
            "review_passed": False,
            "iteration": 0,
            "cost_tracker": {},
        }

        state["iteration"] = 1
        state["review_passed"] = True
        state["cost_tracker"]["total_tokens"] = 500

        assert state["iteration"] == 1
        assert state["review_passed"] is True
        assert state["cost_tracker"]["total_tokens"] == 500

    def test_kbstate_partial_update(self):
        """验证可以创建部分状态更新（用于节点返回）。"""
        partial_update = {
            "sources": [{"title": "new"}],
            "cost_tracker": {"total_tokens": 200},
        }

        assert "sources" in partial_update
        assert "analyses" not in partial_update

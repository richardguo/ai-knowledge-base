"""
common.py 单元测试
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from common import (
    DESC_KEYWORDS,
    EXCLUDE_PATTERNS,
    TARGET_TOPICS,
    generate_collected_at,
    generate_timestamp,
    is_excluded,
    matches_ai,
    merge_items,
    to_gmt8,
)


class TestToGmt8:
    """测试 UTC 时间转换"""

    def test_z_suffix(self):
        """测试 Z 后缀的 UTC 时间"""
        result = to_gmt8("2026-04-16T17:56:15Z")
        assert result == "2026-04-17T01:56:15+08:00"

    def test_plus_00_00_suffix(self):
        """测试 +00:00 后缀的 UTC 时间"""
        result = to_gmt8("2026-04-16T17:56:15+00:00")
        assert result == "2026-04-17T01:56:15+08:00"

    def test_empty_string(self):
        """测试空字符串返回当前时间"""
        result = to_gmt8("")
        assert "+08:00" in result

    def test_invalid_format(self):
        """测试无效格式返回当前时间"""
        result = to_gmt8("invalid-date")
        assert "+08:00" in result


class TestIsExcluded:
    """测试排除规则"""

    def test_exclude_awesome_prefix(self):
        """测试 awesome- 前缀排除"""
        assert is_excluded("awesome-python", "") is True

    def test_exclude_curated_list(self):
        """测试 curated list 排除"""
        assert is_excluded("some-repo", "A curated list of resources") is True

    def test_exclude_book(self):
        """测试 book 排除"""
        assert is_excluded("ml-book", "") is True

    def test_exclude_course(self):
        """测试 course 排除"""
        assert is_excluded("ai-course", "") is True

    def test_exclude_roadmap(self):
        """测试 roadmap 排除"""
        assert is_excluded("dev-roadmap", "") is True

    def test_exclude_interview(self):
        """测试 interview 排除"""
        assert is_excluded("interview-questions", "") is True

    def test_exclude_cheatsheet(self):
        """测试 cheatsheet 排除"""
        assert is_excluded("python-cheatsheet", "") is True

    def test_not_excluded(self):
        """测试正常项目不排除"""
        assert is_excluded("pytorch", "Deep learning framework") is False

    def test_exclude_in_description(self):
        """测试描述中的排除关键词"""
        assert is_excluded("some-repo", "awesome book for learning") is True


class TestMatchesAi:
    """测试 AI 主题匹配"""

    def test_match_by_topic(self):
        """测试通过 topic 匹配"""
        assert matches_ai(["ai", "machine-learning"], "") is True

    def test_match_by_llm_topic(self):
        """测试 LLM topic 匹配"""
        assert matches_ai(["llm", "nlp"], "") is True

    def test_match_by_agent_topic(self):
        """测试 agent topic 匹配"""
        assert matches_ai(["agent", "automation"], "") is True

    def test_match_by_description(self):
        """测试通过描述匹配"""
        assert matches_ai([], "A machine learning framework") is True

    def test_match_by_description_ai(self):
        """测试描述中的 AI 关键词"""
        assert matches_ai([], "AI powered assistant") is True

    def test_match_by_description_llm(self):
        """测试描述中的 LLM 关键词"""
        assert matches_ai([], "LLM inference engine") is True

    def test_match_by_description_deep_learning(self):
        """测试描述中的 deep learning 关键词"""
        assert matches_ai([], "deep learning library") is True

    def test_no_match(self):
        """测试不匹配的情况"""
        assert matches_ai(["web", "frontend"], "A web framework") is False

    def test_empty_inputs(self):
        """测试空输入"""
        assert matches_ai([], "") is False


class TestGenerateTimestamp:
    """测试时间戳生成"""

    def test_format(self):
        """测试时间戳格式"""
        result = generate_timestamp()
        assert len(result) == 17
        assert result.count("-") == 3

    def test_contains_date_time(self):
        """测试包含日期和时间"""
        result = generate_timestamp()
        parts = result.split("-")
        assert len(parts) == 4
        assert len(parts[0]) == 4  # year
        assert len(parts[1]) == 2  # month
        assert len(parts[2]) == 2  # day
        assert len(parts[3]) == 6  # HHMMSS


class TestGenerateCollectedAt:
    """测试 ISO 8601 时间生成"""

    def test_format(self):
        """测试 ISO 8601 格式"""
        result = generate_collected_at()
        assert "+08:00" in result
        assert "T" in result

    def test_structure(self):
        """测试时间结构"""
        result = generate_collected_at()
        assert result.endswith("+08:00")
        date_part, time_part = result.split("T")
        assert len(date_part) == 10
        assert len(time_part) == 14


class TestMergeItems:
    """测试项目合并"""

    def test_add_new_item(self):
        """测试添加新项目"""
        existing = [{"url": "https://github.com/a/b", "title": "b"}]
        new = {"url": "https://github.com/c/d", "title": "d"}
        result = merge_items(existing, new)
        assert len(result) == 2

    def test_update_existing_item(self):
        """测试更新已有项目"""
        existing = [{"url": "https://github.com/a/b", "title": "old"}]
        new = {"url": "https://github.com/a/b", "title": "new"}
        result = merge_items(existing, new)
        assert len(result) == 1
        assert result[0]["title"] == "new"

    def test_empty_existing(self):
        """测试空列表添加"""
        new = {"url": "https://github.com/a/b", "title": "b"}
        result = merge_items([], new)
        assert len(result) == 1

    def test_multiple_updates(self):
        """测试多次更新同一项目"""
        existing = [{"url": "https://github.com/a/b", "stars": 100}]
        new1 = {"url": "https://github.com/a/b", "stars": 200}
        result1 = merge_items(existing, new1)
        new2 = {"url": "https://github.com/a/b", "stars": 300}
        result2 = merge_items(result1, new2)
        assert len(result2) == 1
        assert result2[0]["stars"] == 300


class TestConstants:
    """测试常量配置"""

    def test_target_topics_not_empty(self):
        """测试目标主题不为空"""
        assert len(TARGET_TOPICS) > 0
        assert "ai" in TARGET_TOPICS
        assert "llm" in TARGET_TOPICS
        assert "agent" in TARGET_TOPICS

    def test_exclude_patterns_not_empty(self):
        """测试排除模式不为空"""
        assert len(EXCLUDE_PATTERNS) > 0
        assert "awesome-" in EXCLUDE_PATTERNS
        assert "book" in EXCLUDE_PATTERNS

    def test_exclude_patterns_no_tutorial(self):
        """测试排除模式不含 tutorial"""
        assert "tutorial" not in EXCLUDE_PATTERNS

    def test_desc_keywords_not_empty(self):
        """测试描述关键词不为空"""
        assert len(DESC_KEYWORDS) > 0
        assert "ai" in DESC_KEYWORDS
        assert "llm" in DESC_KEYWORDS

    def test_desc_keywords_no_neural(self):
        """测试描述关键词不含 neural"""
        assert "neural" not in DESC_KEYWORDS


class TestFetchReadme:
    """测试 README 获取"""

    @patch("common.github_api_get")
    def test_readme_truncation(self, mock_api_get):
        """测试 README 截断到 5000 字符"""
        from common import fetch_readme

        long_content = "a" * 10000
        import base64
        encoded = base64.b64encode(long_content.encode()).decode()

        mock_response = MagicMock()
        mock_response.json.return_value = {"content": encoded}
        mock_api_get.return_value = mock_response

        result = fetch_readme("owner", "repo", "token")
        assert len(result) == 5000

    @patch("common.github_api_get")
    def test_readme_failure_returns_empty(self, mock_api_get):
        """测试 README 获取失败返回空字符串"""
        from common import fetch_readme

        mock_api_get.return_value = None
        result = fetch_readme("owner", "repo", "token")
        assert result == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

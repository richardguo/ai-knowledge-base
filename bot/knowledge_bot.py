"""知识库交互 Bot，提供搜索、订阅、权限控制等功能。"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request
from enum import Enum
from pathlib import Path
from typing import Any


class Intent(Enum):
    """用户意图枚举。"""

    SEARCH = "search"
    TODAY = "today"
    TOP = "top"
    SUBSCRIBE = "subscribe"
    HELP = "help"
    NEXT = "next"
    UNKNOWN = "unknown"


class Permission(Enum):
    """权限等级枚举。"""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Permission):
            return NotImplemented
        order = [Permission.READ, Permission.WRITE, Permission.DELETE]
        return order.index(self) >= order.index(other)

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Permission):
            return NotImplemented
        order = [Permission.READ, Permission.WRITE, Permission.DELETE]
        return order.index(self) > order.index(other)

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Permission):
            return NotImplemented
        order = [Permission.READ, Permission.WRITE, Permission.DELETE]
        return order.index(self) <= order.index(other)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Permission):
            return NotImplemented
        order = [Permission.READ, Permission.WRITE, Permission.DELETE]
        return order.index(self) < order.index(other)


_COMMAND_MAP: dict[str, Intent] = {
    "/search": Intent.SEARCH,
    "/today": Intent.TODAY,
    "/top": Intent.TOP,
    "/subscribe": Intent.SUBSCRIBE,
    "/help": Intent.HELP,
    "/next": Intent.NEXT,
}

_KEYWORD_MAP: list[tuple[re.Pattern[str], Intent]] = [
    (re.compile(r"搜索|查询|查找|search|find", re.IGNORECASE), Intent.SEARCH),
    (re.compile(r"今天|今日|daily|today", re.IGNORECASE), Intent.TODAY),
    (re.compile(r"热门|排行|top|榜单", re.IGNORECASE), Intent.TOP),
    (re.compile(r"订阅|subscribe|关注", re.IGNORECASE), Intent.SUBSCRIBE),
    (re.compile(r"帮助|help|用法|怎么用", re.IGNORECASE), Intent.HELP),
    (re.compile(r"下一页|翻页|next", re.IGNORECASE), Intent.NEXT),
]


def recognize_intent(text: str) -> tuple[Intent, str]:
    """识别用户输入的意图。

    优先匹配命令前缀（如 ``/search``），再匹配自然语言关键词。
    命令前缀后的内容作为参数返回。

    Args:
        text: 用户输入文本。

    Returns:
        ``(Intent, 参数字符串)`` 二元组。
    """
    text = text.strip()
    if not text:
        return Intent.UNKNOWN, ""

    for cmd, intent in _COMMAND_MAP.items():
        if text.startswith(cmd):
            param = text[len(cmd) :].strip()
            return intent, param

    for pattern, intent in _KEYWORD_MAP:
        if pattern.search(text):
            return intent, text

    return Intent.UNKNOWN, text


class SynonymExpander:
    """同义词扩展器，根据同义词组扩展查询词。

    同义词文件格式为 JSON 数组，每个元素是一个同义词组::

        [["智能体", "agent", "agents"], ["大模型", "llm"]]

    Args:
        synonyms_path: 同义词文件路径。
    """

    def __init__(self, synonyms_path: str = "bot/synonyms.json") -> None:
        self._path = Path(synonyms_path)
        self._groups: list[list[str]] = self._load()

    def _load(self) -> list[list[str]]:
        """加载同义词文件。

        Returns:
            同义词组列表。文件不存在时返回空列表。
        """
        if not self._path.exists():
            return []
        with self._path.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return data

    def expand(self, query: str) -> list[str]:
        """扩展查询词，返回原始词加所有匹配的同义词。

        对每个同义词组，若组中任一成员是查询词的子串（不区分大小写），
        则将该组所有成员加入结果。

        Args:
            query: 原始查询词。

        Returns:
            扩展后的查询词列表，至少包含原始查询词。
        """
        query_lower = query.lower()
        expanded = [query]
        seen = {query_lower}
        for group in self._groups:
            if any(member.lower() in query_lower for member in group):
                for synonym in group:
                    if synonym.lower() not in seen:
                        expanded.append(synonym)
                        seen.add(synonym.lower())
        return expanded


class Reranker:
    """LLM 重排器，调用外部 Rerank API 对搜索结果二次排序。

    从环境变量读取默认配置：
    - ``BAISHAN_RERANK_API_BASE``：API 端点
    - ``BAISHAN_API_KEY``：API 密钥
    - ``RERANK_MODEL_ID``：模型 ID

    Args:
        api_base: Rerank API 端点，为 None 时从环境变量读取。
        api_key: API 密钥，为 None 时从环境变量读取。
        model: 模型 ID，为 None 时从环境变量读取。
    """

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_base = api_base if api_base is not None else os.getenv("BAISHAN_RERANK_API_BASE", "")
        self._api_key = api_key if api_key is not None else os.getenv("BAISHAN_API_KEY", "")
        self._model = model if model is not None else os.getenv("RERANK_MODEL_ID", "bge-reranker-v2-m3")

    @property
    def is_configured(self) -> bool:
        """Reranker 是否已配置（API 端点和密钥均非空）。"""
        return bool(self._api_base and self._api_key)

    def rerank(self, query: str, documents: list[str], top_n: int = 5) -> list[int]:
        """对文档列表按与查询的相关度重排序。

        Args:
            query: 用户查询文本。
            documents: 待排序的文档文本列表。
            top_n: 返回前 N 个结果的索引。

        Returns:
            按相关度降序排列的文档索引列表。
            API 不可用时降级返回原始顺序的前 top_n 个索引。
        """
        if not documents:
            return []
        if not self.is_configured:
            return list(range(min(top_n, len(documents))))

        payload = json.dumps(
            {
                "model": self._model,
                "query": query,
                "documents": documents,
                "top_n": top_n,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(
            self._api_base,
            data=payload,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError):
            return list(range(min(top_n, len(documents))))

        results = data.get("results", [])
        sorted_results = sorted(
            results, key=lambda x: x.get("relevance_score", 0), reverse=True
        )
        return [r["index"] for r in sorted_results[:top_n]]


class SearchHistory:
    """搜索历史记录器，以 JSONL 格式追加记录查询。

    Args:
        path: 历史记录文件路径，为 None 时使用
            ``~/.knowledge_bot_history.jsonl``。
    """

    def __init__(self, path: str | None = None) -> None:
        if path is None:
            path = str(Path.home() / ".knowledge_bot_history.jsonl")
        self._path = Path(path)

    def record(self, user_id: str, query: str, result_count: int) -> None:
        """记录一次搜索查询。

        Args:
            user_id: 用户唯一标识。
            query: 搜索查询文本。
            result_count: 返回结果数量。
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": dt.datetime.now().isoformat(),
            "user_id": user_id,
            "query": query,
            "result_count": result_count,
        }
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class KnowledgeSearchEngine:
    """知识库搜索引擎，支持关键词、标签、日期范围过滤。

    Args:
        knowledge_dir: 知识条目目录路径。
    """

    def __init__(self, knowledge_dir: str = "knowledge/articles") -> None:
        self._dir = Path(knowledge_dir)

    def _load_all(self) -> list[dict[str, Any]]:
        """加载目录下所有知识条目。

        Returns:
            知识条目列表。
        """
        articles: list[dict[str, Any]] = []
        if not self._dir.exists():
            return articles
        for path in self._dir.glob("*.json"):
            if path.name == "index.json":
                continue
            with path.open(encoding="utf-8") as f:
                articles.append(json.load(f))
        return articles

    def search(
        self,
        keyword: str | list[str] | None = None,
        tags: list[str] | None = None,
        date_from: dt.date | str | None = None,
        date_to: dt.date | str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """搜索知识条目。

        Args:
            keyword: 关键词（字符串或列表），匹配 title / summary / tags
                （不区分大小写）。传入列表时，匹配任一关键词即命中。
            tags: 标签过滤列表，匹配任一标签即命中。
            date_from: 起始日期（含），支持 ``datetime.date`` 或
                ``"YYYY-MM-DD"`` 字符串。
            date_to: 结束日期（含），支持 ``datetime.date`` 或
                ``"YYYY-MM-DD"`` 字符串。
            limit: 返回条目上限。

        Returns:
            匹配的知识条目列表，按 relevance_score 降序排列。
        """
        articles = self._load_all()

        if keyword:
            keywords = [keyword] if isinstance(keyword, str) else keyword
            kws_lower = [k.lower() for k in keywords]
            articles = [
                a
                for a in articles
                if any(
                    kw in a.get("title", "").lower()
                    or kw in a.get("summary", "").lower()
                    or any(kw in t.lower() for t in a.get("tags", []))
                    for kw in kws_lower
                )
            ]

        if tags:
            tag_set = {t.lower() for t in tags}
            articles = [
                a for a in articles if tag_set & {t.lower() for t in a.get("tags", [])}
            ]

        if date_from is not None or date_to is not None:
            _from = self._parse_date(date_from) or dt.date.min
            _to = self._parse_date(date_to) or dt.date.max
            articles = [
                a
                for a in articles
                if _from <= dt.date.fromisoformat(a.get("collected_at", "")[:10]) <= _to
            ]

        articles.sort(key=lambda a: a.get("relevance_score", 0), reverse=True)
        return articles[:limit]

    @staticmethod
    def _parse_date(value: dt.date | str | None) -> dt.date | None:
        """解析日期参数。

        Args:
            value: ``datetime.date`` 或 ``"YYYY-MM-DD"`` 字符串或 None。

        Returns:
            解析后的日期，或 None。
        """
        if value is None:
            return None
        if isinstance(value, dt.date):
            return value
        return dt.date.fromisoformat(value)


class SubscriptionManager:
    """用户订阅管理，支持增删查。

    Args:
        store_path: 订阅数据持久化文件路径。
    """

    def __init__(
        self, store_path: str = "knowledge/processed/subscriptions.json"
    ) -> None:
        self._path = Path(store_path)
        self._data: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        """从文件加载订阅数据。

        Returns:
            以 user_id 为键的订阅字典。
        """
        if not self._path.exists():
            return {}
        with self._path.open(encoding="utf-8") as f:
            return json.load(f)

    def _save(self) -> None:
        """将订阅数据持久化到文件。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def add(
        self, user_id: str, tags: list[str] | None = None, daily: bool = False
    ) -> None:
        """添加或更新用户订阅。

        Args:
            user_id: 用户唯一标识。
            tags: 订阅标签列表。
            daily: 是否订阅每日简报。
        """
        existing = self._data.get(user_id, {})
        if tags:
            merged = list(set(existing.get("tags", []) + tags))
            existing["tags"] = sorted(merged)
        if daily:
            existing["daily"] = True
        self._data[user_id] = existing
        self._save()

    def remove(self, user_id: str) -> bool:
        """移除用户订阅。

        Args:
            user_id: 用户唯一标识。

        Returns:
            是否成功移除（用户存在时为 True）。
        """
        if user_id in self._data:
            del self._data[user_id]
            self._save()
            return True
        return False

    def get(self, user_id: str) -> dict[str, Any] | None:
        """查询用户订阅信息。

        Args:
            user_id: 用户唯一标识。

        Returns:
            订阅信息字典，不存在时返回 None。
        """
        return self._data.get(user_id)

    def list_subscribers(self, tag: str | None = None) -> list[str]:
        """列出所有订阅者。

        Args:
            tag: 按标签过滤，为 None 时返回全部订阅者。

        Returns:
            用户 ID 列表。
        """
        if tag is None:
            return list(self._data.keys())
        return [uid for uid, info in self._data.items() if tag in info.get("tags", [])]


class PermissionManager:
    """三级权限控制（READ / WRITE / DELETE）。

    Args:
        store_path: 权限数据持久化文件路径。
    """

    def __init__(
        self, store_path: str = "knowledge/processed/permissions.json"
    ) -> None:
        self._path = Path(store_path)
        self._data: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        """从文件加载权限数据。

        Returns:
            以 user_id 为键、权限等级名为值的字典。
        """
        if not self._path.exists():
            return {}
        with self._path.open(encoding="utf-8") as f:
            return json.load(f)

    def _save(self) -> None:
        """将权限数据持久化到文件。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def grant(self, user_id: str, permission: Permission) -> None:
        """授予用户指定权限等级。

        Args:
            user_id: 用户唯一标识。
            permission: 权限等级。
        """
        self._data[user_id] = permission.value
        self._save()

    def revoke(self, user_id: str) -> bool:
        """撤销用户权限。

        Args:
            user_id: 用户唯一标识。

        Returns:
            是否成功撤销。
        """
        if user_id in self._data:
            del self._data[user_id]
            self._save()
            return True
        return False

    def check(self, user_id: str, required: Permission) -> bool:
        """检查用户是否拥有指定权限等级。

        Args:
            user_id: 用户唯一标识。
            required: 所需最低权限等级。

        Returns:
            用户权限 >= required 时返回 True。
        """
        level_name = self._data.get(user_id)
        if level_name is None:
            return False
        try:
            user_perm = Permission(level_name)
        except ValueError:
            return False
        return user_perm >= required


def format_search_results(
    results: list[dict[str, Any]],
    custom_query_input: str | None = None,
) -> str:
    """将搜索结果格式化为人类可读的文本。

    Args:
        results: ``KnowledgeSearchEngine.search()`` 返回的知识条目列表。
        custom_query_input: 用户输入的查询文本，用于标题提示。

    Returns:
        格式化后的文本；无结果时返回提示字符串。
    """
    if not results:
        if custom_query_input:
            return f"未找到与「{custom_query_input}」相关的知识条目。"
        return "未找到匹配的知识条目。"

    header = (
        f"搜索「{custom_query_input}」的结果（共 {len(results)} 条）："
        if custom_query_input
        else f"搜索结果（共 {len(results)} 条）："
    )

    lines = [header, ""]
    for i, a in enumerate(results, 1):
        score = a.get("relevance_score", 0)
        title = a.get("title", "")
        url = a.get("url", "")
        summary = a.get("summary", "")[:60]
        lines.append(f"{i}. {title} [{score}/10]")
        lines.append(f"   {summary}...")
        lines.append(f"   {url}")
    return "\n".join(lines)


def _article_to_document(article: dict[str, Any]) -> str:
    """将知识条目转换为供 Reranker 使用的文档文本。

    Args:
        article: 知识条目字典。

    Returns:
        拼接 title + summary + tags 的文档字符串。
    """
    parts = [article.get("title", ""), article.get("summary", "")]
    parts.extend(article.get("tags", []))
    return " ".join(p for p in parts if p)


class KnowledgeBot:
    """知识库交互 Bot 主入口，整合搜索、订阅、权限模块。

    Args:
        knowledge_dir: 知识条目目录路径。
        synonyms_path: 同义词文件路径。
        history_path: 搜索历史文件路径，为 None 时使用
            ``~/.knowledge_bot_history.jsonl``。
    """

    _PAGE_SIZE = 5
    _SEARCH_CANDIDATE_LIMIT = 10

    def __init__(
        self,
        knowledge_dir: str = "knowledge/articles",
        synonyms_path: str = "bot/synonyms.json",
        history_path: str | None = None,
    ) -> None:
        self._search_engine = KnowledgeSearchEngine(knowledge_dir)
        self._subscription_mgr = SubscriptionManager()
        self._permission_mgr = PermissionManager()
        self._synonym_expander = SynonymExpander(synonyms_path)
        self._reranker = Reranker()
        self._search_history = SearchHistory(history_path)
        self._user_page_state: dict[str, dict[str, Any]] = {}

    def handle_message(self, user_id: str, text: str) -> str:
        """处理用户消息的统一入口。

        Args:
            user_id: 用户唯一标识。
            text: 用户输入文本。

        Returns:
            Bot 回复文本。
        """
        intent, param = recognize_intent(text)

        handlers = {
            Intent.SEARCH: self._handle_search,
            Intent.TODAY: self._handle_today,
            Intent.TOP: self._handle_top,
            Intent.SUBSCRIBE: self._handle_subscribe,
            Intent.HELP: self._handle_help,
            Intent.NEXT: self._handle_next,
        }

        handler = handlers.get(intent)
        if handler is None:
            return self._handle_unknown(user_id, text)

        return handler(user_id, param)

    def _handle_search(self, user_id: str, param: str) -> str:
        """处理搜索意图。

        流程：同义词扩展 → 规则匹配 top 10 → Rerank 二次排序 → 分页展示。

        Args:
            user_id: 用户唯一标识。
            param: 搜索关键词。

        Returns:
            搜索结果文本。
        """
        if not self._permission_mgr.check(user_id, Permission.READ):
            return "您没有搜索权限，请联系管理员。"

        if not param:
            return "请提供搜索关键词，例如：/search langflow 或 搜索 agent"

        expanded_keywords = self._synonym_expander.expand(param)

        results = self._search_engine.search(
            keyword=expanded_keywords, limit=self._SEARCH_CANDIDATE_LIMIT
        )

        if results and self._reranker.is_configured:
            docs = [_article_to_document(a) for a in results]
            top_indices = self._reranker.rerank(param, docs, top_n=min(5, len(results)))
            reranked_set = set(top_indices)
            reranked = [results[i] for i in top_indices if i < len(results)]
            remaining = [r for i, r in enumerate(results) if i not in reranked_set]
            results = reranked + remaining

        self._search_history.record(user_id, param, len(results))

        self._user_page_state[user_id] = {
            "results": results,
            "page": 0,
            "query": param,
        }

        page_results = results[: self._PAGE_SIZE]
        output = format_search_results(page_results, custom_query_input=param)
        if len(results) > self._PAGE_SIZE:
            output += f"\n\n共 {len(results)} 条结果，输入 /next 查看更多"
        return output

    def _handle_next(self, user_id: str, param: str) -> str:
        """处理翻页意图。

        Args:
            user_id: 用户唯一标识。
            param: 未使用。

        Returns:
            下一页搜索结果文本。
        """
        if not self._permission_mgr.check(user_id, Permission.READ):
            return "您没有查看权限，请联系管理员。"

        state = self._user_page_state.get(user_id)
        if state is None:
            return "没有可翻页的搜索结果，请先使用 /search 搜索。"

        results = state["results"]
        next_page = state["page"] + 1
        start = next_page * self._PAGE_SIZE
        end = start + self._PAGE_SIZE
        page_results = results[start:end]

        if not page_results:
            return f"已到最后一页，共 {len(results)} 条结果。"

        state["page"] = next_page
        total_pages = -(-len(results) // self._PAGE_SIZE)
        output = format_search_results(page_results, custom_query_input=state["query"])
        output += f"\n\n第 {next_page + 1}/{total_pages} 页"
        if end < len(results):
            output += "\n输入 /next 查看更多"
        return output

    def _handle_today(self, user_id: str, param: str) -> str:
        """处理今日简报意图。

        Args:
            user_id: 用户唯一标识。
            param: 未使用。

        Returns:
            今日知识条目文本。
        """
        if not self._permission_mgr.check(user_id, Permission.READ):
            return "您没有查看权限，请联系管理员。"

        today = dt.date.today().isoformat()
        results = self._search_engine.search(date_from=today, date_to=today, limit=10)

        if not results:
            return f"📭 {today} 暂无新增知识条目"

        lines = [f"📰 AI 知识日报 · {today}", ""]
        for i, a in enumerate(results, 1):
            score = a.get("relevance_score", 0)
            title = a.get("title", "")
            lines.append(f"{i}. {title} [{score}/10]")
        return "\n".join(lines)

    def _handle_top(self, user_id: str, param: str) -> str:
        """处理热门排行意图。

        Args:
            user_id: 用户唯一标识。
            param: 未使用。

        Returns:
            热门排行文本。
        """
        if not self._permission_mgr.check(user_id, Permission.READ):
            return "您没有查看权限，请联系管理员。"

        results = self._search_engine.search(limit=10)

        if not results:
            return "知识库暂无条目。"

        lines = ["🔥 AI 知识库热门排行 Top 10", ""]
        for i, a in enumerate(results, 1):
            score = a.get("relevance_score", 0)
            title = a.get("title", "")
            lines.append(f"{i}. {title} [{score}/10]")
        return "\n".join(lines)

    def _handle_subscribe(self, user_id: str, param: str) -> str:
        """处理订阅意图。

        Args:
            user_id: 用户唯一标识。
            param: 订阅参数（标签或 daily）。

        Returns:
            订阅操作结果文本。
        """
        if not self._permission_mgr.check(user_id, Permission.WRITE):
            return "您没有订阅权限，请联系管理员。"

        if not param:
            sub = self._subscription_mgr.get(user_id)
            if sub is None:
                return (
                    "您暂无订阅。用法：/subscribe daily 或 /subscribe agent-framework"
                )
            tags = sub.get("tags", [])
            daily = sub.get("daily", False)
            parts = []
            if tags:
                parts.append(f"标签: {', '.join(tags)}")
            if daily:
                parts.append("每日简报: 已订阅")
            return f"您的订阅：{' | '.join(parts)}"

        if param.lower() == "daily":
            self._subscription_mgr.add(user_id, daily=True)
            return "已订阅每日简报 ✅"

        tags = [t.strip() for t in param.replace(",", " ").split() if t.strip()]
        if tags:
            self._subscription_mgr.add(user_id, tags=tags)
            return f"已订阅标签：{', '.join(tags)} ✅"

        return "用法：/subscribe daily 或 /subscribe agent-framework"

    def _handle_help(self, user_id: str, param: str) -> str:
        """处理帮助意图。

        Args:
            user_id: 用户唯一标识。
            param: 未使用。

        Returns:
            帮助文本。
        """
        return (
            "📖 AI 知识库 Bot 使用指南\n\n"
            "🔍 搜索：/search <关键词> 或 搜索 <关键词>\n"
            "📰 今日：/today 或 今天\n"
            "🔥 热门：/top 或 热门\n"
            "📄 下一页：/next 或 下一页\n"
            "🔔 订阅：/subscribe daily 或 /subscribe <标签>\n"
            "❓ 帮助：/help 或 帮助\n\n"
            "权限等级：READ（搜索/查看）< WRITE（订阅）< DELETE（管理）"
        )

    def _handle_unknown(self, user_id: str, text: str) -> str:
        """处理未识别意图。

        Args:
            user_id: 用户唯一标识。
            text: 原始输入文本。

        Returns:
            提示文本。
        """
        return "未识别的指令。输入 /help 查看使用指南。"

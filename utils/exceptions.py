"""自定义异常类模块。

提供项目中使用的异常类定义。
"""

from __future__ import annotations


class LLMError(Exception):
    """LLM 调用错误。

    用于表示 LLM API 调用过程中的各类错误。

    Attributes:
        status_code: HTTP 状态码（可选），用于区分不同类型的错误。
            - None: 网络层错误（超时、连接失败等）
            - 429: 限流错误
            - 500/502/503/504: 服务端错误
            - 401: 认证错误
            - 其他: API 返回的其他错误码
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """初始化错误。

        Args:
            message: 错误信息。
            status_code: HTTP 状态码（可选）。
        """
        super().__init__(message)
        self.status_code = status_code

    def __repr__(self) -> str:
        """返回错误的字符串表示。"""
        if self.status_code is not None:
            return f"LLMError(message={self.args[0]!r}, status_code={self.status_code})"
        return f"LLMError(message={self.args[0]!r})"

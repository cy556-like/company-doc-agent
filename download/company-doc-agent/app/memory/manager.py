"""
对话记忆管理模块
管理每个用户/会话的对话历史，支持多轮对话
"""
from collections import defaultdict
from typing import Optional

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory


class InMemoryHistory(BaseChatMessageHistory):
    """
    基于内存的对话历史存储
    生产环境建议替换为 Redis / 数据库
    """

    def __init__(self):
        self._messages: list[BaseMessage] = []

    @property
    def messages(self) -> list[BaseMessage]:
        return self._messages

    def add_message(self, message: BaseMessage) -> None:
        self._messages.append(message)

    def clear(self) -> None:
        self._messages = []


# 全局会话存储：session_id -> ChatMessageHistory
_session_store: dict[str, InMemoryHistory] = defaultdict(InMemoryHistory)


def get_session_history(session_id: str) -> BaseChatMessageHistory:
    """获取指定会话的对话历史"""
    if session_id not in _session_store:
        _session_store[session_id] = InMemoryHistory()
    return _session_store[session_id]


def clear_session_history(session_id: str) -> None:
    """清除指定会话的对话历史"""
    if session_id in _session_store:
        _session_store[session_id].clear()
        del _session_store[session_id]


def get_history_messages(session_id: str) -> list[dict]:
    """获取会话历史的格式化版本（用于 API 返回）"""
    history = get_session_history(session_id)
    messages = []
    for msg in history.messages:
        role = "user" if isinstance(msg, HumanMessage) else "assistant"
        messages.append({"role": role, "content": msg.content})
    return messages

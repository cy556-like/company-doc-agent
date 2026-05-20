"""
对话记忆管理模块
基于文件的持久化存储，支持多用户隔离
"""
import os
import json

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
CONVERSATIONS_DIR = os.path.join(DATA_DIR, "conversations")


class FileBasedHistory:
    """基于文件的对话历史存储"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        os.makedirs(CONVERSATIONS_DIR, exist_ok=True)
        self._file_path = os.path.join(CONVERSATIONS_DIR, f"{session_id}.json")
        self._messages: list[BaseMessage] = self._load_messages()

    def _load_messages(self) -> list:
        """从文件加载消息"""
        if not os.path.exists(self._file_path):
            return []
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            messages = []
            for item in data:
                if item.get("role") == "user":
                    messages.append(HumanMessage(content=item["content"]))
                elif item.get("role") == "assistant":
                    messages.append(AIMessage(content=item["content"]))
            return messages
        except Exception:
            return []

    def _save_messages(self):
        """保存消息到文件"""
        data = []
        for msg in self._messages:
            if isinstance(msg, HumanMessage):
                data.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                data.append({"role": "assistant", "content": msg.content})
        with open(self._file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @property
    def messages(self) -> list[BaseMessage]:
        return self._messages

    def add_message(self, message: BaseMessage) -> None:
        self._messages.append(message)
        self._save_messages()

    def clear(self) -> None:
        self._messages = []
        if os.path.exists(self._file_path):
            os.remove(self._file_path)


# 全局缓存：session_id -> FileBasedHistory
_session_store: dict[str, FileBasedHistory] = {}


def get_session_history(session_id: str) -> FileBasedHistory:
    """获取指定会话的对话历史"""
    if session_id not in _session_store:
        _session_store[session_id] = FileBasedHistory(session_id)
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


def get_history_for_gradio(session_id: str) -> list:
    """获取 Gradio 格式的对话历史"""
    history = get_session_history(session_id)
    result = []
    for msg in history.messages:
        role = "user" if isinstance(msg, HumanMessage) else "assistant"
        result.append({"role": role, "content": msg.content})
    return result
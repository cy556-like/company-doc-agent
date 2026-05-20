"""
Agent 核心逻辑模块
使用 LangGraph 构建 ReAct 模式的 Agent
支持流式输出（Streaming）
"""
import asyncio
from typing import Annotated, AsyncGenerator
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.config import settings
from app.agent.tools import ALL_TOOLS
from app.agent.prompts import SYSTEM_PROMPT
from app.memory.manager import get_session_history

# 最大历史消息数量（加速推理，避免上下文过长）
MAX_HISTORY_MESSAGES = 10

# 最大工具调用轮数（防止无限循环）
MAX_TOOL_ROUNDS = 3


# ===== 1. 定义 Agent 状态 =====
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


# ===== 2. 创建 LLM =====
def create_llm():
    """创建 LLM 实例（启用 streaming 支持）"""
    return ChatOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        temperature=0.1,
        streaming=True,  # 启用流式输出
    )


# ===== 3. 构建 Agent 图 =====
def create_agent_graph():
    llm = create_llm()
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    def think(state: AgentState):
        messages = state["messages"]
        system_msg = SystemMessage(content=SYSTEM_PROMPT)
        response = llm_with_tools.invoke([system_msg] + messages)
        return {"messages": [response]}

    tool_node = ToolNode(ALL_TOOLS)

    def should_continue(state: AgentState):
        messages = state["messages"]
        tool_message_count = sum(1 for m in messages if isinstance(m, ToolMessage))
        if tool_message_count >= MAX_TOOL_ROUNDS:
            return END
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "act"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("think", think)
    graph.add_node("act", tool_node)
    graph.set_entry_point("think")
    graph.add_conditional_edges("think", should_continue, {"act": "act", END: END})
    graph.add_edge("act", "think")
    return graph.compile()


# ===== 4. 全局 Agent 实例 =====
_agent_graph = None


def get_agent():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = create_agent_graph()
    return _agent_graph


def reset_agent():
    global _agent_graph
    _agent_graph = None


def chat(user_input: str, session_id: str = "default") -> str:
    """非流式对话（保留兼容）"""
    agent = get_agent()
    history = get_session_history(session_id)
    recent_messages = history.messages[-MAX_HISTORY_MESSAGES:]
    all_messages = recent_messages + [HumanMessage(content=user_input)]
    result = agent.invoke({"messages": all_messages})
    ai_message = result["messages"][-1]
    history.add_message(HumanMessage(content=user_input))
    history.add_message(ai_message)
    return ai_message.content


# ===== 5. 流式对话 =====

# 工具中文名映射
TOOL_DISPLAY_NAMES = {
    "search_documents_tool": "🔍 搜索文档",
    "lookup_employee_tool": "👤 查询员工",
    "list_documents_tool": "📄 列出文档",
    "upload_document_tool": "📤 上传文档",
    "modify_document_tool": "✏️ 修改文档",
}


async def chat_stream_generator(user_input: str, session_id: str = "default") -> AsyncGenerator[dict, None]:
    """
    流式对话：逐token输出，同时显示工具调用进度
    Yields: {"type": "token"|"tool"|"done"|"error", ...}
    """
    agent = get_agent()
    history = get_session_history(session_id)
    recent_messages = history.messages[-MAX_HISTORY_MESSAGES:]
    all_messages = recent_messages + [HumanMessage(content=user_input)]

    full_response = ""

    try:
        async for event in agent.astream_events(
            {"messages": all_messages},
            version="v2",
        ):
            kind = event["event"]

            # LLM 输出 token
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                content = getattr(chunk, 'content', '')
                if content:
                    full_response += content
                    yield {"type": "token", "content": content}

            # 工具调用开始
            elif kind == "on_tool_start":
                tool_name = event.get("name", "")
                display_name = TOOL_DISPLAY_NAMES.get(tool_name, tool_name)
                yield {"type": "tool", "name": tool_name, "display": display_name}

    except Exception as e:
        # 流式失败 → 回退到非流式，模拟打字效果
        try:
            result = agent.invoke({"messages": all_messages})
            ai_message = result["messages"][-1]
            full_response = ai_message.content
            # 模拟打字效果
            for i in range(0, len(full_response), 3):
                yield {"type": "token", "content": full_response[i:i+3]}
                await asyncio.sleep(0.02)
        except Exception as e2:
            yield {"type": "error", "content": f"处理失败: {str(e2)}"}
            return

    # 保存到会话历史
    if full_response:
        try:
            history.add_message(HumanMessage(content=user_input))
            history.add_message(AIMessage(content=full_response))
        except Exception:
            pass

    yield {"type": "done"}

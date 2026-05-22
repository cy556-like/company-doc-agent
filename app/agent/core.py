"""
Agent 核心逻辑模块
使用 LangGraph 构建 ReAct 模式的 Agent
ReAct = Reasoning(推理) + Acting(行动) → 边思考边行动
支持流式输出（Streaming SSE）
"""
import asyncio
from typing import Annotated, AsyncGenerator
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.config import settings, VISION_MODELS, DEFAULT_VISION_MODEL
from app.agent.tools import ALL_TOOLS
from app.agent.prompts import SYSTEM_PROMPT
from app.memory.manager import get_session_history

# 最大历史消息数量（加速推理，避免上下文过长）
MAX_HISTORY_MESSAGES = 10

# 最大工具调用轮数（防止无限循环）
MAX_TOOL_ROUNDS = 3


# ===== 1. 定义 Agent 状态 =====
class AgentState(TypedDict):
    """
    Agent 的状态定义
    messages 使用 add_messages 策略：新消息追加而非覆盖
    """
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
    """
    构建 LangGraph Agent 执行图

    流程：用户输入 → LLM 思考 → 是否调用工具？
           ├─ 是 → 执行工具 → 回到 LLM 思考（循环，最多3轮）
           └─ 否 → 输出回答 → 结束
    """
    llm = create_llm()

    # 将工具绑定到 LLM，让它知道有哪些工具可以用
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    # 节点1: LLM 思考节点
    def think(state: AgentState):
        """LLM 思考：分析用户问题，决定是否调用工具"""
        messages = state["messages"]
        # 在开头插入系统提示词
        system_msg = SystemMessage(content=SYSTEM_PROMPT)
        response = llm_with_tools.invoke([system_msg] + messages)
        return {"messages": [response]}

    # 节点2: 工具执行节点（使用 LangGraph 内置的 ToolNode）
    tool_node = ToolNode(ALL_TOOLS)

    # 条件边：判断是否需要继续调用工具（限制最大轮数）
    def should_continue(state: AgentState):
        """
        判断是否需要继续调用工具
        如果工具调用轮数超过 MAX_TOOL_ROUNDS，则强制结束
        """
        messages = state["messages"]
        # 统计 ToolMessage 的数量，每轮工具调用会产生一个 ToolMessage
        tool_message_count = sum(1 for m in messages if isinstance(m, ToolMessage))

        if tool_message_count >= MAX_TOOL_ROUNDS:
            return END

        # 使用 LangGraph 内置判断：最后一条消息是否有工具调用
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "act"

        return END

    # ===== 构建状态图 =====
    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("think", think)       # 思考节点
    graph.add_node("act", tool_node)     # 行动节点

    # 设置入口
    graph.set_entry_point("think")

    # 添加条件边：思考后判断是否需要调用工具
    graph.add_conditional_edges(
        "think",
        should_continue,
        {
            "act": "act",   # 需要工具 → 去执行
            END: END,       # 不需要工具 → 结束
        },
    )

    # 执行完工具后，回到思考节点（形成 ReAct 循环）
    graph.add_edge("act", "think")

    return graph.compile()


# ===== 4. 全局 Agent 实例 =====
_agent_graph = None


def get_agent():
    """获取 Agent 单例（懒加载）"""
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = create_agent_graph()
    return _agent_graph


def reset_agent():
    """重置 Agent 实例（切换模型后调用，下次对话会自动重建）"""
    global _agent_graph
    _agent_graph = None


def chat(user_input: str, session_id: str = "default") -> str:
    """
    非流式对话（保留兼容）
    """
    agent = get_agent()

    # 获取该会话的历史消息
    history = get_session_history(session_id)

    # 只取最近 MAX_HISTORY_MESSAGES 条历史消息（加速推理）
    recent_messages = history.messages[-MAX_HISTORY_MESSAGES:]

    # 构建完整的消息列表 = 历史消息 + 新消息
    all_messages = recent_messages + [HumanMessage(content=user_input)]

    # 调用 Agent
    result = agent.invoke({"messages": all_messages})

    # 提取最后的 AI 回答
    ai_message = result["messages"][-1]

    # 保存到会话历史
    history.add_message(HumanMessage(content=user_input))
    history.add_message(ai_message)

    return ai_message.content


# ===== 5. 流式对话 =====

# 工具中文名映射
TOOL_DISPLAY_NAMES = {
    "search_documents_tool": "搜索文档",
    "lookup_employee_tool": "查询员工",
    "list_documents_tool": "列出文档",
    "upload_document_tool": "上传文档",
    "modify_document_tool": "修改文档",
    "delete_document_tool": "删除文档",
}


async def chat_stream_generator(user_input: str, session_id: str = "default") -> AsyncGenerator[dict, None]:
    """
    流式对话：逐token输出，同时显示工具调用进度
    Yields: {"type": "token"|"tool"|"thinking"|"done"|"error", ...}
    """
    agent = get_agent()
    history = get_session_history(session_id)
    recent_messages = history.messages[-MAX_HISTORY_MESSAGES:]
    all_messages = recent_messages + [HumanMessage(content=user_input)]

    full_response = ""

    try:
        # 先发一个"思考中"信号
        yield {"type": "thinking", "content": "正在思考..."}

        async for event in agent.astream_events(
            {"messages": all_messages},
            version="v2",
        ):
            kind = event["event"]

            # LLM 输出 token（逐字输出）
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

            # 工具调用结束
            elif kind == "on_tool_end":
                tool_name = event.get("name", "")
                display_name = TOOL_DISPLAY_NAMES.get(tool_name, tool_name)
                yield {"type": "tool_done", "name": tool_name, "display": display_name}

    except Exception as e:
        # 流式失败 → 回退到非流式
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


async def chat_stream_generator_multimodal(multimodal_content: list, session_id: str = "default") -> AsyncGenerator[dict, None]:
    """
    多模态流式对话：支持图片+文本的混合消息
    multimodal_content: [{"type":"text","text":"..."}, {"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}]
    注意：图片消息不走 Agent 工具调用（多模态模型不支持 function calling + 图片混用）
    """
    # 自动切换到视觉模型（当前模型不支持图片时）
    current_model = settings.LLM_MODEL
    use_model = current_model
    if current_model not in VISION_MODELS:
        use_model = DEFAULT_VISION_MODEL

    llm = ChatOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=use_model,
        temperature=0.1,
        streaming=True,
    )

    history = get_session_history(session_id)
    recent_messages = history.messages[-MAX_HISTORY_MESSAGES:]

    # 构建多模态 HumanMessage
    human_msg = HumanMessage(content=multimodal_content)
    all_messages = recent_messages + [human_msg]

    full_response = ""

    try:
        yield {"type": "thinking", "content": f"正在分析图片（使用{use_model}）..."}

        async for chunk in llm.astream([SystemMessage(content=SYSTEM_PROMPT)] + all_messages):
            content = getattr(chunk, 'content', '')
            if content:
                full_response += content
                yield {"type": "token", "content": content}

    except Exception as e:
        # 多模态失败，尝试降级为纯文本描述
        try:
            # 提取文本部分
            text_parts = [p["text"] for p in multimodal_content if p["type"] == "text"]
            fallback_text = "\n".join(text_parts) + "\n\n[注意：图片分析失败，请用文字描述你的问题]"
            async for event in chat_stream_generator(fallback_text, session_id):
                yield event
            return
        except Exception as e2:
            yield {"type": "error", "content": f"图片分析失败: {str(e2)}"}
            return

    # 保存到会话历史（用文本描述保存，避免base64占空间）
    if full_response:
        try:
            text_summary = " ".join([p["text"] for p in multimodal_content if p["type"] == "text"])
            history.add_message(HumanMessage(content=text_summary))
            history.add_message(AIMessage(content=full_response))
        except Exception:
            pass

    yield {"type": "done"}

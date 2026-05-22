"""
FastAPI 路由定义
提供 REST API 接口供外部调用
包含：认证、聊天（含流式）、文档管理、会话管理、模型管理
"""
import os
import asyncio
import shutil
import json
import base64
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent.core import chat, chat_stream_generator, reset_agent
from app.rag.document import index_document, search_documents, list_indexed_documents, delete_document
from app.auth.user_manager import login_user, register_user
from app.memory.manager import (
    get_history_messages, clear_session_history,
    create_chat, list_chats, delete_chat, rename_chat, update_chat_time,
)
from app.config import settings, AVAILABLE_MODELS, get_current_model, set_current_model

router = APIRouter()


# ===== 请求/响应模型 =====
class ChatRequest(BaseModel):
    """聊天请求"""
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    """聊天响应"""
    response: str
    session_id: str


class SearchRequest(BaseModel):
    """文档搜索请求"""
    query: str
    top_k: int = 3


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class RegisterRequest(BaseModel):
    """注册请求"""
    username: str
    password: str


class ModelSetRequest(BaseModel):
    """设置模型请求"""
    model_id: str


class RenameRequest(BaseModel):
    """重命名会话请求"""
    username: str
    chat_id: str
    new_title: str


# ===== 认证接口 =====

@router.post("/auth/login", summary="用户登录")
async def auth_login(req: LoginRequest):
    """用户登录验证"""
    result = login_user(req.username, req.password)
    return result


@router.post("/auth/register", summary="用户注册")
async def auth_register(req: RegisterRequest):
    """用户注册"""
    result = register_user(req.username, req.password)
    return result


# ===== 聊天接口 =====

@router.post("/chat", response_model=ChatResponse, summary="与 Agent 对话（非流式）")
async def chat_api(req: ChatRequest):
    """
    核心接口：与文档助手 Agent 对话（非流式）

    - 支持 RAG 文档问答
    - 支持员工信息查询
    - 支持多轮对话
    """
    try:
        response = chat(req.message, req.session_id)
        # 更新会话时间
        try:
            # 从 session_id 中提取 username
            parts = req.session_id.split("_", 1)
            if len(parts) == 2:
                update_chat_time(parts[0], req.session_id)
        except Exception:
            pass
        return ChatResponse(response=response, session_id=req.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 处理失败: {str(e)}")


@router.post("/chat/stream", summary="与 Agent 对话（流式 SSE）")
async def chat_stream_api(req: ChatRequest):
    """
    流式对话接口：逐 token 输出，同时显示工具调用进度
    返回 Server-Sent Events (SSE) 流
    """
    async def event_generator():
        async for chunk in chat_stream_generator(req.message, req.session_id):
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        # 更新会话时间
        try:
            parts = req.session_id.split("_", 1)
            if len(parts) == 2:
                update_chat_time(parts[0], req.session_id)
        except Exception:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat-with-file/stream", summary="带文件的流式对话")
async def chat_with_file_stream(
    file: UploadFile = File(...),
    message: str = Form(""),
    session_id: str = Form("default"),
):
    """
    带文件的流式对话：支持图片和文档
    - 图片（png/jpg/jpeg/gif/bmp/webp）：转为base64传给LLM分析
    - 文档（pdf/txt/docx）：索引后基于内容回答
    - 其他文件：读取文本内容（如有）传给LLM
    返回 Server-Sent Events (SSE) 流
    """
    ext = os.path.splitext(file.filename)[1].lower()
    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
    doc_exts = {".pdf", ".txt", ".docx"}
    code_exts = {".py", ".js", ".html", ".css", ".json", ".md", ".csv", ".xlsx", ".xls", ".doc", ".ppt", ".pptx"}

    if ext in image_exts:
        # 图片文件：base64编码，传给LLM做视觉分析
        file_content = await file.read()
        b64 = base64.b64encode(file_content).decode("utf-8")
        mime_map = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp",
        }
        mime_type = mime_map.get(ext, "image/png")
        full_message = f"[用户上传了图片: {file.filename}]\n\n{message}\n\n[图片数据: data:{mime_type};base64,{b64}]"

    elif ext in doc_exts:
        # 文档文件：索引到知识库后回答
        file_path = os.path.join(settings.DOCUMENTS_DIR, file.filename)
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        try:
            index_result = index_document(file_path, file.filename)
        except Exception as e:
            os.remove(file_path)
            raise HTTPException(status_code=500, detail=f"文档索引失败: {str(e)}")
        full_message = f"[用户上传了文档: {file.filename}]\n\n{message}"

    elif ext in code_exts:
        # 代码/其他文本文件：读取内容传给LLM
        try:
            file_content = await file.read()
            text = file_content.decode("utf-8", errors="replace")
            full_message = f"[用户上传了文件: {file.filename}]\n\n文件内容：\n```\n{text[:8000]}\n```\n\n{message}"
        except Exception:
            full_message = f"[用户上传了文件: {file.filename}，但无法读取内容]\n\n{message}"
    else:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")

    # 流式回答
    async def event_generator():
        async for chunk in chat_stream_generator(full_message, session_id):
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        try:
            parts = session_id.split("_", 1)
            if len(parts) == 2:
                update_chat_time(parts[0], session_id)
        except Exception:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ===== 文档管理接口 =====

@router.post("/upload", summary="上传文档到知识库")
async def upload_document(file: UploadFile = File(...)):
    """
    上传文档并自动索引到向量数据库
    支持 PDF、TXT、DOCX 格式
    """
    # 检查文件格式
    allowed_ext = {".pdf", ".txt", ".docx"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext}，仅支持 {allowed_ext}",
        )

    # 保存文件
    file_path = os.path.join(settings.DOCUMENTS_DIR, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # 索引文档
    try:
        result = index_document(file_path, file.filename)
        return {"status": "success", "detail": result}
    except Exception as e:
        # 索引失败则删除文件
        os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"文档索引失败: {str(e)}")


@router.post("/search", summary="搜索文档内容")
async def search_api(req: SearchRequest):
    """在文档库中搜索相关内容"""
    results = search_documents(req.query, req.top_k)
    return {"query": req.query, "results": results}


@router.get("/documents", summary="列出所有已索引文档")
async def list_documents():
    """获取知识库中所有文档列表"""
    docs = list_indexed_documents()
    return {"documents": docs, "count": len(docs)}


@router.delete("/documents/{filename}", summary="从知识库删除文档")
async def delete_document_api(filename: str):
    """
    从知识库中删除指定文档
    同时删除 ChromaDB 中的向量分块和原始文件
    """
    result = delete_document(filename)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail=result["message"])
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])
    return {"status": "success", "detail": result}


# ===== 会话历史接口 =====

@router.get("/history/{session_id}", summary="获取对话历史")
async def get_history(session_id: str):
    """获取指定会话的对话历史"""
    messages = get_history_messages(session_id)
    return {"session_id": session_id, "messages": messages, "count": len(messages)}


@router.delete("/history/{session_id}", summary="清除对话历史")
async def delete_history(session_id: str):
    """清除指定会话的对话历史"""
    clear_session_history(session_id)
    return {"status": "success", "message": f"会话 {session_id} 的历史已清除"}


# ===== 会话管理接口 =====

@router.get("/chats", summary="获取用户会话列表")
async def get_chats(username: str):
    """获取用户的所有会话列表"""
    chats = list_chats(username)
    return {"success": True, "chats": chats}


@router.post("/chats", summary="创建新会话")
async def create_chat_api(username: str, title: str = "新对话"):
    """为用户创建一个新的会话"""
    chat_info = create_chat(username, title)
    return {"success": True, "chat": chat_info}


@router.delete("/chats/{chat_id}", summary="删除会话")
async def delete_chat_api(chat_id: str, username: str):
    """删除用户的某个会话"""
    delete_chat(username, chat_id)
    return {"success": True, "message": "会话已删除"}


@router.put("/chats/{chat_id}/rename", summary="重命名会话")
async def rename_chat_api(chat_id: str, req: RenameRequest):
    """重命名用户的某个会话"""
    rename_chat(req.username, req.chat_id, req.new_title)
    return {"success": True, "message": "会话已重命名"}


# ===== 模型管理接口 =====

@router.get("/models", summary="获取可用模型列表")
async def get_models():
    """获取所有可用的 LLM 模型列表"""
    current = get_current_model()
    return {"models": AVAILABLE_MODELS, "current": current}


@router.post("/models/set", summary="切换模型")
async def set_model(req: ModelSetRequest):
    """切换当前使用的 LLM 模型"""
    success = set_current_model(req.model_id)
    if success:
        return {"success": True, "message": f"已切换到模型: {req.model_id}"}
    return {"success": False, "message": f"不支持的模型: {req.model_id}"}

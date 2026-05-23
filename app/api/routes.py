"""
FastAPI 路由定义
提供 REST API 接口供外部调用
包含：认证（JWT）、聊天（含流式）、文档管理、会话管理、模型管理、统计
"""
import os
import asyncio
import shutil
import json
import base64
import logging
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel

from app.agent.core import chat, chat_stream_generator, chat_stream_generator_multimodal, reset_agent
from app.rag.document import index_document, search_documents, list_indexed_documents, delete_document
from app.auth.user_manager import login_user, register_user
from app.auth.jwt_handler import create_token, verify_token, get_username_from_token
from app.memory.manager import (
    get_history_messages, clear_session_history,
    create_chat, list_chats, delete_chat, rename_chat, update_chat_time,
)
from app.config import settings, AVAILABLE_MODELS, get_current_model, set_current_model
from app.utils.stats import record_message, record_session, get_stats

logger = logging.getLogger(__name__)

# 文件大小限制：50MB
MAX_FILE_SIZE = 50 * 1024 * 1024

router = APIRouter()


# ===== JWT 认证依赖 =====
def get_current_user(request: Request) -> str:
    """
    从请求中提取当前用户名（JWT Token 或兼容旧方式）
    不强制认证，但如果有 Token 则验证
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        username = get_username_from_token(token)
        if username:
            return username
    # 兼容：从查询参数获取
    username = request.query_params.get("username", "")
    return username


def require_auth(request: Request) -> str:
    """
    强制要求 JWT 认证
    返回已认证的用户名
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        username = get_username_from_token(token)
        if username:
            return username
    raise HTTPException(status_code=401, detail="未认证，请重新登录")


# ===== 请求/响应模型 =====
class ChatRequest(BaseModel):
    """聊天请求"""
    message: str
    session_id: str = "default"
    web_search: bool = False
    mode: str = "agent"  # agent / chat
    deep_think: bool = False


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
    """用户登录验证，返回 JWT Token"""
    result = login_user(req.username, req.password)
    if result.get("success"):
        # 签发 JWT Token
        token = create_token(req.username)
        result["token"] = token
    return result


@router.post("/auth/register", summary="用户注册")
async def auth_register(req: RegisterRequest):
    """用户注册"""
    result = register_user(req.username, req.password)
    if result.get("success"):
        # 注册成功也签发 Token
        token = create_token(req.username)
        result["token"] = token
    return result


@router.get("/auth/me", summary="验证 Token 有效性")
async def auth_me(request: Request):
    """验证当前 JWT Token 是否有效"""
    try:
        username = require_auth(request)
        return {"valid": True, "username": username}
    except HTTPException:
        return {"valid": False, "username": None}


# ===== 聊天接口 =====

@router.post("/chat", response_model=ChatResponse, summary="与 Agent 对话（非流式）")
async def chat_api(req: ChatRequest, username: str = Depends(get_current_user)):
    """
    核心接口：与文档助手 Agent 对话（非流式）

    - 支持 RAG 文档问答
    - 支持员工信息查询
    - 支持多轮对话
    """
    try:
        response = chat(req.message, req.session_id, web_search=req.web_search, mode=req.mode, deep_think=req.deep_think)
        # 更新会话时间
        try:
            parts = req.session_id.split("_", 1)
            if len(parts) == 2:
                update_chat_time(parts[0], req.session_id)
        except Exception:
            pass
        # 记录统计
        record_message(username=username or "anonymous", model_id=get_current_model())
        return ChatResponse(response=response, session_id=req.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 处理失败: {str(e)}")


@router.post("/chat/stream", summary="与 Agent 对话（流式 SSE）")
async def chat_stream_api(req: ChatRequest, username: str = Depends(get_current_user)):
    """
    流式对话接口：逐 token 输出，同时显示工具调用进度
    返回 Server-Sent Events (SSE) 流
    """
    # 记录统计
    record_message(username=username or "anonymous", model_id=get_current_model())

    async def event_generator():
        async for chunk in chat_stream_generator(req.message, req.session_id, web_search=req.web_search, mode=req.mode, deep_think=req.deep_think):
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            # 记录工具使用
            if chunk.get("type") == "tool":
                from app.utils.stats import record_message as _rm
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
    web_search: bool = Form(False),
    mode: str = Form("agent"),
    deep_think: bool = Form(False),
    username: str = Depends(get_current_user),
):
    """
    带文件的流式对话：支持图片和文档
    - 图片（png/jpg/jpeg/gif/bmp/webp）：转为base64传给LLM分析
    - 文档（pdf/txt/docx）：索引后基于内容回答
    - 其他文件：读取文本内容（如有）传给LLM
    返回 Server-Sent Events (SSE) 流
    """
    # 记录统计
    record_message(username=username or "anonymous", model_id=get_current_model())

    ext = os.path.splitext(file.filename)[1].lower()
    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
    doc_exts = {".pdf", ".txt", ".docx"}
    code_exts = {".py", ".js", ".html", ".css", ".json", ".md", ".csv", ".xlsx", ".xls", ".doc", ".ppt", ".pptx"}

    # 文件大小检查
    file_content_raw = await file.read()
    if len(file_content_raw) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"文件大小超过限制（最大 50MB），当前文件: {len(file_content_raw) // 1024 // 1024}MB")
    # 重置文件指针
    await file.seek(0)

    logger.info(f"收到文件上传: {file.filename}, 大小: {len(file_content_raw)} bytes")

    if ext in image_exts:
        # 图片文件：用多模态消息格式传给LLM做视觉分析
        file_content = await file.read()
        b64 = base64.b64encode(file_content).decode("utf-8")
        mime_map = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp",
        }
        mime_type = mime_map.get(ext, "image/png")
        # 构建多模态消息内容
        image_url = f"data:{mime_type};base64,{b64}"
        multimodal_content = [
            {"type": "text", "text": f"[用户上传了图片: {file.filename}]\n\n{message or '请描述这张图片'}"},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
        # 直接调用多模态流式生成
        async def event_generator():
            async for chunk in chat_stream_generator_multimodal(multimodal_content, session_id):
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
        async for chunk in chat_stream_generator(full_message, session_id, web_search=web_search, mode=mode, deep_think=deep_think):
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

    # 文件大小检查
    file_content_raw = await file.read()
    if len(file_content_raw) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"文件大小超过限制（最大 50MB）")
    await file.seek(0)

    logger.info(f"知识库上传文档: {file.filename}, 大小: {len(file_content_raw)} bytes")

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
    record_session()
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


# ===== 使用统计接口 =====

@router.get("/stats", summary="获取使用统计")
async def get_usage_stats(username: str = Depends(get_current_user)):
    """获取系统使用统计数据"""
    stats = get_stats()
    return {"success": True, "stats": stats}


# ===== 导出对话接口 =====

@router.get("/export/{session_id}", summary="导出对话")
async def export_chat(session_id: str, format: str = "md"):
    """
    导出对话为 Markdown 或 PDF 格式
    format: md | pdf
    """
    messages = get_history_messages(session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="没有可导出的对话内容")

    if format == "pdf":
        # PDF 导出
        try:
            from app.utils.pdf_generator import generate_chat_pdf
            pdf_bytes = generate_chat_pdf(messages, session_id)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename=chat_{session_id[:12]}.pdf"
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF 生成失败: {str(e)}")
    else:
        # Markdown 导出
        content = ""
        for msg in messages:
            role = "用户" if msg["role"] == "user" else "助手"
            content += f"**{role}：**\n\n{msg['content']}\n\n---\n\n"

        return Response(
            content=content.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename=chat_{session_id[:12]}.md"
            }
        )

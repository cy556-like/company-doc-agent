"""
FastAPI 路由定义
支持流式输出（SSE）
"""
import os
import shutil
import json
import asyncio
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent.core import chat, chat_stream_generator, TOOL_DISPLAY_NAMES
from app.rag.document import index_document, search_documents, list_indexed_documents, read_document_content
from app.memory.manager import (
    get_history_messages, clear_session_history,
    create_chat, list_chats, delete_chat, rename_chat, update_chat_time,
)
from app.auth.user_manager import login_user, register_user
from app.config import settings, AVAILABLE_MODELS, set_current_model, get_current_model

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    response: str
    session_id: str

class SearchRequest(BaseModel):
    query: str
    top_k: int = 3

class AuthRequest(BaseModel):
    username: str
    password: str

class RenameChatRequest(BaseModel):
    username: str
    chat_id: str
    new_title: str

class SetModelRequest(BaseModel):
    model_id: str


# ===== 认证 =====
@router.post("/auth/login")
async def auth_login(req: AuthRequest):
    return login_user(req.username, req.password)

@router.post("/auth/register")
async def auth_register(req: AuthRequest):
    return register_user(req.username, req.password)


# ===== 会话 =====
@router.post("/chats")
async def create_new_chat(username: str = Query(...), title: str = Query("新对话")):
    return {"success": True, "chat": create_chat(username, title)}

@router.get("/chats")
async def get_user_chats(username: str = Query(...)):
    return {"success": True, "chats": list_chats(username)}

@router.delete("/chats/{chat_id}")
async def delete_user_chat(chat_id: str, username: str = Query(...)):
    delete_chat(username, chat_id)
    return {"success": True, "message": "会话已删除"}

@router.put("/chats/{chat_id}/rename")
async def rename_user_chat(chat_id: str, req: RenameChatRequest):
    rename_chat(req.username, req.chat_id, req.new_title)
    return {"success": True, "message": "会话已重命名"}


# ===== Agent 对话（非流式，保留兼容） =====
@router.post("/chat", response_model=ChatResponse)
async def chat_api(req: ChatRequest):
    try:
        response = chat(req.message, req.session_id)
        parts = req.session_id.rsplit("_", 1)
        if len(parts) == 2:
            try: update_chat_time(parts[0], req.session_id)
            except: pass
        return ChatResponse(response=response, session_id=req.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 处理失败: {str(e)}")


# ===== Agent 对话（流式 SSE） =====
@router.post("/chat/stream")
async def chat_stream_api(req: ChatRequest):
    """流式对话：逐token输出，前端实时显示"""
    async def generate():
        async for chunk in chat_stream_generator(req.message, req.session_id):
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        # 更新会话时间
        parts = req.session_id.rsplit("_", 1)
        if len(parts) == 2:
            try: update_chat_time(parts[0], req.session_id)
            except: pass

    return StreamingResponse(generate(), media_type="text/event-stream")


# ===== 文件+对话（流式 SSE） =====
@router.post("/chat-with-file/stream")
async def chat_with_file_stream(
    file: UploadFile = File(...),
    message: str = Form(...),
    session_id: str = Form("default"),
):
    """ChatGPT风格：文件+消息对话，流式输出"""
    allowed_ext = {".pdf", ".txt", ".docx"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")

    file_path = os.path.join(settings.DOCUMENTS_DIR, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        try: index_document(file_path, file.filename)
        except: pass

        try: file_content = read_document_content(file_path)
        except Exception as e: file_content = f"(无法读取文件内容: {str(e)})"

        max_chars = 8000
        if len(file_content) > max_chars:
            file_content = file_content[:max_chars] + f"\n...(已截断，共{len(file_content)}字符)"

        enhanced_message = f"""[用户上传了文件: {file.filename}]

文件内容如下：
---
{file_content}
---

文件保存路径: {file_path}

用户的问题/要求: {message}"""

        async def generate():
            async for chunk in chat_stream_generator(enhanced_message, session_id):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            parts = session_id.rsplit("_", 1)
            if len(parts) == 2:
                try: update_chat_time(parts[0], session_id)
                except: pass

        return StreamingResponse(generate(), media_type="text/event-stream")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


# ===== 文件+对话（非流式，保留兼容） =====
@router.post("/chat-with-file")
async def chat_with_file(
    file: UploadFile = File(...),
    message: str = Form(...),
    session_id: str = Form("default"),
):
    allowed_ext = {".pdf", ".txt", ".docx"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")

    file_path = os.path.join(settings.DOCUMENTS_DIR, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        try: index_document(file_path, file.filename)
        except: pass
        try: file_content = read_document_content(file_path)
        except Exception as e: file_content = f"(无法读取文件内容: {str(e)})"

        max_chars = 8000
        if len(file_content) > max_chars:
            file_content = file_content[:max_chars] + f"\n...(已截断，共{len(file_content)}字符)"

        enhanced_message = f"""[用户上传了文件: {file.filename}]

文件内容如下：
---
{file_content}
---

文件保存路径: {file_path}

用户的问题/要求: {message}"""

        response = chat(enhanced_message, session_id)
        parts = session_id.rsplit("_", 1)
        if len(parts) == 2:
            try: update_chat_time(parts[0], session_id)
            except: pass
        return {"response": response, "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


# ===== 文档管理 =====
@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    allowed_ext = {".pdf", ".txt", ".docx"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")
    file_path = os.path.join(settings.DOCUMENTS_DIR, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        result = index_document(file_path, file.filename)
        return {"status": "success", "detail": result}
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"文档索引失败: {str(e)}")


@router.post("/modify-document")
async def modify_document(
    file: UploadFile = File(...),
    instruction: str = Form(...),
    username: str = Form("default"),
):
    allowed_ext = {".pdf", ".txt", ".docx"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")
    temp_dir = os.path.join(settings.DATA_DIR, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, file.filename)
    with open(temp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        content = read_document_content(temp_path)
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage
        llm = ChatOpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL, model=settings.LLM_MODEL, temperature=0.3)
        system_prompt = "你是一个文档修改助手。按修改要求修改文档，只返回修改后的完整内容，不要解释。保持原文档格式和结构，用中文输出。"
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=f"原始文档内容：\n\n{content}\n\n修改要求：{instruction}")]
        response = llm.invoke(messages)
        modified_content = response.content
        static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
        modified_dir = os.path.join(static_dir, "modified")
        os.makedirs(modified_dir, exist_ok=True)
        output_filename = f"modified_{file.filename}"
        output_path = os.path.join(modified_dir, output_filename)
        if ext == ".pdf":
            from app.utils.pdf_generator import generate_pdf
            success, actual_path = generate_pdf(modified_content, output_path)
            output_filename = os.path.basename(actual_path)
        elif ext == ".docx":
            try:
                from docx import Document
                doc = Document(temp_path)
                for p in doc.paragraphs: p.text = ""
                paras = modified_content.split("\n")
                if doc.paragraphs: doc.paragraphs[0].text = paras[0] if paras else ""
                for pt in paras[1:]: doc.add_paragraph(pt)
                doc.save(output_path)
            except ImportError:
                output_path = output_path.replace(".docx", ".txt")
                output_filename = os.path.basename(output_path)
                with open(output_path, "w", encoding="utf-8") as f: f.write(modified_content)
        else:
            with open(output_path, "w", encoding="utf-8") as f: f.write(modified_content)
        os.remove(temp_path)
        return {"success": True, "message": "文档修改完成！", "download_url": f"/static/modified/{output_filename}", "filename": output_filename}
    except Exception as e:
        if os.path.exists(temp_path): os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"文档修改失败: {str(e)}")


@router.post("/search")
async def search_api(req: SearchRequest):
    return {"query": req.query, "results": search_documents(req.query, req.top_k)}

@router.get("/documents")
async def list_documents():
    docs = list_indexed_documents()
    return {"documents": docs, "count": len(docs)}


# ===== 历史 =====
@router.get("/history/{session_id}")
async def get_history(session_id: str):
    msgs = get_history_messages(session_id)
    return {"session_id": session_id, "messages": msgs, "count": len(msgs)}

@router.delete("/history/{session_id}")
async def delete_history(session_id: str):
    clear_session_history(session_id)
    return {"status": "success", "message": f"会话 {session_id} 的历史已清除"}


# ===== 模型管理 =====
@router.get("/models")
async def get_models():
    return {"models": AVAILABLE_MODELS, "current": get_current_model()}

@router.post("/models/set")
async def set_model(req: SetModelRequest):
    success = set_current_model(req.model_id)
    if success:
        return {"success": True, "message": f"已切换到模型: {req.model_id}", "current": req.model_id}
    else:
        valid_ids = [m["id"] for m in AVAILABLE_MODELS]
        raise HTTPException(status_code=400, detail=f"不支持的模型: {req.model_id}，可选: {valid_ids}")

"""
FastAPI 路由定义
提供 REST API 接口供外部调用
"""
import os
import shutil
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.agent.core import chat
from app.rag.document import index_document, search_documents, list_indexed_documents
from app.memory.manager import get_history_messages, clear_session_history
from app.config import settings

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


# ===== API 接口 =====

@router.post("/chat", response_model=ChatResponse, summary="与 Agent 对话")
async def chat_api(req: ChatRequest):
    """
    核心接口：与文档助手 Agent 对话

    - 支持 RAG 文档问答
    - 支持员工信息查询
    - 支持多轮对话
    """
    try:
        response = chat(req.message, req.session_id)
        return ChatResponse(response=response, session_id=req.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 处理失败: {str(e)}")


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

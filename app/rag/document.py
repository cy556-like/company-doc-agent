"""
文档处理与向量化模块 (RAG)
负责：加载文档 → 分块 → 向量化 → 存入 ChromaDB → 检索
"""
import os
import json
import logging
from typing import Optional

from langchain_community.document_loaders import PyPDFLoader, TextLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma

from app.config import settings

logger = logging.getLogger(__name__)

# Embedding API 单次最大批量数（智谱限制 64 条）
EMBEDDING_BATCH_SIZE = 50

# ===== 单例模式：复用 Embedding 和 ChromaDB 连接 =====
_embeddings_instance = None
_vector_store_instance = None


def get_embeddings():
    """获取 Embedding 模型（单例复用，避免重复初始化）"""
    global _embeddings_instance
    if _embeddings_instance is None:
        embedding_model = getattr(settings, 'EMBEDDING_MODEL', 'embedding-3')
        _embeddings_instance = OpenAIEmbeddings(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            model=embedding_model,
        )
        logger.info(f"Embedding 模型已初始化: {embedding_model}")
    return _embeddings_instance


def get_vector_store():
    """获取 ChromaDB 向量数据库实例（单例复用）"""
    global _vector_store_instance
    if _vector_store_instance is None:
        embeddings = get_embeddings()
        _vector_store_instance = Chroma(
            persist_directory=settings.CHROMA_DIR,
            embedding_function=embeddings,
        )
        logger.info(f"ChromaDB 已连接: {settings.CHROMA_DIR}")
    return _vector_store_instance


def reset_vector_store():
    """重置向量数据库单例（配置变更时调用）"""
    global _vector_store_instance, _embeddings_instance
    _vector_store_instance = None
    _embeddings_instance = None
    logger.info("向量数据库单例已重置")


def load_document(file_path: str) -> list:
    """
    根据文件类型加载文档
    支持：PDF、TXT、DOCX
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        loader = PyPDFLoader(file_path)
    elif ext == ".txt":
        loader = TextLoader(file_path, encoding="utf-8")
    elif ext == ".docx":
        loader = Docx2txtLoader(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {ext}，仅支持 PDF/TXT/DOCX")

    return loader.load()


def split_documents(docs: list, chunk_size: int = 500, chunk_overlap: int = 100) -> list:
    """
    文档分块
    - chunk_size: 每块最大字符数
    - chunk_overlap: 块间重叠字符数（保证上下文连续性）
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
    )
    return splitter.split_documents(docs)


def index_document(file_path: str, filename: str = None) -> dict:
    """
    完整的文档索引流程：加载 → 分块 → 分批向量化 → 存储
    分批写入，避免 Embedding API 单次批量超限（智谱限制64条/次）

    Returns:
        dict: 包含分块数量和状态信息
    """
    if filename is None:
        filename = os.path.basename(file_path)

    logger.info(f"开始索引文档: {filename}")

    # 1. 加载文档
    docs = load_document(file_path)

    # 2. 给文档添加元数据
    for doc in docs:
        doc.metadata["source_file"] = filename

    # 3. 分块
    chunks = split_documents(docs)

    if not chunks:
        return {
            "filename": filename,
            "chunks": 0,
            "status": "success",
            "message": f"文档 {filename} 内容为空，无需索引",
        }

    # 4. 分批向量化并存储（每批不超过 EMBEDDING_BATCH_SIZE 条）
    vector_store = get_vector_store()
    total_chunks = len(chunks)
    batch_count = (total_chunks + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE

    for i in range(batch_count):
        start = i * EMBEDDING_BATCH_SIZE
        end = min(start + EMBEDDING_BATCH_SIZE, total_chunks)
        batch = chunks[start:end]
        try:
            vector_store.add_documents(batch)
        except Exception as e:
            # 如果中途失败，尝试回滚已写入的数据
            try:
                # 查找该文档已写入的分块并删除
                collection = vector_store._collection
                existing = collection.get(
                    where={"source_file": filename},
                    include=["metadatas"],
                )
                if existing.get("ids"):
                    collection.delete(ids=existing["ids"])
            except Exception:
                pass
            raise RuntimeError(f"第 {i+1}/{batch_count} 批向量化失败（分块 {start+1}-{end}）: {str(e)}")

    logger.info(f"文档索引完成: {filename}, 共 {total_chunks} 个分块")    
    return {
        "filename": filename,
        "chunks": total_chunks,
        "status": "success",
        "message": f"文档 {filename} 已成功索引，共 {total_chunks} 个分块（分 {batch_count} 批写入）",
    }


def search_documents(query: str, top_k: int = 3) -> list[dict]:
    """
    在向量数据库中检索与查询最相关的文档片段

    Args:
        query: 用户查询
        top_k: 返回最相关的 K 个结果

    Returns:
        list[dict]: 检索结果列表
    """
    vector_store = get_vector_store()
    results = vector_store.similarity_search_with_score(query, k=top_k)

    formatted = []
    for doc, score in results:
        formatted.append({
            "content": doc.page_content,
            "source": doc.metadata.get("source_file", "未知来源"),
            "relevance_score": round(1 - score, 4),  # 转换为相似度
        })

    return formatted


def list_indexed_documents() -> list[str]:
    """列出知识库中所有已索引的文档"""
    vector_store = get_vector_store()
    # 从 ChromaDB 的元数据中提取所有文档名
    try:
        collection = vector_store._collection
        all_docs = collection.get(include=["metadatas"])
        sources = set()
        for meta in all_docs["metadatas"]:
            if meta and "source_file" in meta:
                sources.add(meta["source_file"])
        return sorted(list(sources))
    except Exception:
        return []


def delete_document(filename: str) -> dict:
    """
    从知识库中删除指定文档
    包括：从 ChromaDB 删除向量分块 + 删除原始文件

    Args:
        filename: 要删除的文档文件名

    Returns:
        dict: 包含删除状态和详细信息
    """
    vector_store = get_vector_store()
    collection = vector_store._collection

    # 1. 查找该文档的所有分块 ID
    try:
        results = collection.get(
            where={"source_file": filename},
            include=["metadatas"],
        )
    except Exception as e:
        return {
            "filename": filename,
            "status": "error",
            "message": f"查询 ChromaDB 失败: {str(e)}",
        }

    chunk_ids = results.get("ids", [])
    if not chunk_ids:
        return {
            "filename": filename,
            "status": "not_found",
            "message": f"文档 {filename} 在知识库中未找到",
        }

    # 2. 从 ChromaDB 删除所有分块
    try:
        collection.delete(ids=chunk_ids)
    except Exception as e:
        return {
            "filename": filename,
            "status": "error",
            "message": f"从向量数据库删除失败: {str(e)}",
        }

    # 3. 删除原始文件
    file_deleted = False
    file_path = os.path.join(settings.DOCUMENTS_DIR, filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            file_deleted = True
        except Exception as e:
            return {
                "filename": filename,
                "chunks_deleted": len(chunk_ids),
                "file_deleted": False,
                "status": "partial",
                "message": f"向量分块已删除 {len(chunk_ids)} 个，但原始文件删除失败: {str(e)}",
            }

    return {
        "filename": filename,
        "chunks_deleted": len(chunk_ids),
        "file_deleted": file_deleted,
        "status": "success",
        "message": f"文档 {filename} 已成功删除（{len(chunk_ids)} 个分块，原始文件{'已删除' if file_deleted else '不存在'}）",
    }

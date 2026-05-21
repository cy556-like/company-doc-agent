"""
Agent 工具定义模块
每个工具 = Agent 的一个「能力」
Agent 会根据用户问题自动选择调用哪个工具
"""
import json
import os
import shutil
from typing import Optional

from langchain_core.tools import tool

from app.config import settings
from app.rag.document import search_documents, index_document, list_indexed_documents, delete_document


@tool
def search_documents_tool(query: str) -> str:
    """在公司文档库中搜索与查询相关的文档内容。当用户问关于公司制度、流程、规范等问题时使用。

    Args:
        query: 搜索查询内容
    """
    results = search_documents(query, top_k=3)

    if not results:
        return "未找到相关文档内容。"

    output = "检索到以下相关内容：\n\n"
    for i, r in enumerate(results, 1):
        output += f"【文档 {i}】来源: {r['source']}\n"
        output += f"{r['content']}\n"
        output += f"(相似度: {r['relevance_score']})\n\n"

    return output


@tool
def lookup_employee_tool(name: str = "", department: str = "") -> str:
    """查询公司员工信息，包括姓名、部门、职位、邮箱等。当用户问「某某在哪个部门」、「某部门有哪些人」等问题时使用。

    Args:
        name: 员工姓名（可选，模糊匹配）
        department: 部门名称（可选）
    """
    employees_file = settings.EMPLOYEES_FILE

    if not os.path.exists(employees_file):
        return "员工数据库暂未初始化，请先运行 scripts/seed_data.py 初始化数据。"

    with open(employees_file, "r", encoding="utf-8") as f:
        employees = json.load(f)

    results = employees

    # 按姓名过滤
    if name:
        results = [e for e in results if name in e.get("name", "")]

    # 按部门过滤
    if department:
        results = [e for e in results if department in e.get("department", "")]

    if not results:
        return f"未找到匹配的员工信息。（搜索条件：姓名={name}, 部门={department}）"

    output = f"找到 {len(results)} 位员工：\n\n"
    for e in results:
        output += f"{e['name']} | 部门: {e['department']} | 职位: {e['position']} | 邮箱: {e['email']}\n"
        if e.get("phone"):
            output += f"   电话: {e['phone']}\n"

    return output


@tool
def list_documents_tool() -> str:
    """列出知识库中所有可用的文档。当用户想了解有哪些文档时使用。"""
    docs = list_indexed_documents()

    if not docs:
        return "知识库中暂无文档。请先上传文档。"

    output = f"知识库中共有 {len(docs)} 个文档：\n\n"
    for i, doc in enumerate(docs, 1):
        output += f"  {i}. {doc}\n"

    return output


@tool
def upload_document_tool(file_path: str) -> str:
    """上传新文档到知识库。当用户需要添加新文档时使用。

    Args:
        file_path: 文档文件路径
    """
    if not os.path.exists(file_path):
        return f"文件不存在: {file_path}"

    try:
        result = index_document(file_path)
        return f"文档上传成功！{result['message']}"
    except Exception as e:
        return f"文档上传失败: {str(e)}"


@tool
def delete_document_tool(filename: str) -> str:
    """从知识库中删除指定文档。当用户想要删除某个文档时使用，会同时删除向量分块和原始文件。

    Args:
        filename: 要删除的文档文件名
    """
    try:
        result = delete_document(filename)
        if result["status"] == "not_found":
            return f"文档 {filename} 在知识库中未找到。"
        return result["message"]
    except Exception as e:
        return f"删除文档失败: {str(e)}"


# ===== 导出所有工具列表 =====
ALL_TOOLS = [
    search_documents_tool,
    lookup_employee_tool,
    list_documents_tool,
    upload_document_tool,
    delete_document_tool,
]

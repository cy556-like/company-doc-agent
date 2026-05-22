"""
Agent 工具定义模块
每个工具 = Agent 的一个「能力」
Agent 会根据用户问题自动选择调用哪个工具

Prompt Engineering 优化:
- 工具描述清晰定义触发条件和适用场景
- 参数说明包含类型、约束和使用建议
- 返回值格式标准化，便于 Agent 解析和引用
"""
import json
import os
from typing import Optional

from langchain_core.tools import tool

from app.config import settings
from app.rag.document import search_documents, index_document, list_indexed_documents, delete_document


@tool
def search_documents_tool(query: str) -> str:
    """搜索公司文档知识库，检索与查询语义相关的文档片段。

    触发条件：当用户询问公司制度、流程、规范、政策、规定等文档相关问题时使用。
    不适用：员工个人信息查询（用 lookup_employee_tool）、文档列表查看（用 list_documents_tool）。

    Args:
        query: 搜索查询，应为提取自用户问题的关键词或语义短语。
               建议：提取核心概念而非整句输入。
               示例：「年假制度」优于「我想知道公司年假制度是什么」
    """
    results = search_documents(query, top_k=3)

    if not results:
        return "【检索结果】未找到与查询相关的文档内容。建议：1）尝试换用不同关键词搜索；2）确认相关文档是否已上传至知识库。"

    output = f"【检索结果】共找到 {len(results)} 条相关内容：\n\n"
    for i, r in enumerate(results, 1):
        output += f"<document source=\"{r['source']}\" relevance=\"{r['relevance_score']}\">\n"
        output += f"{r['content']}\n"
        output += f"</document>\n\n"

    return output


@tool
def lookup_employee_tool(name: str = "", department: str = "") -> str:
    """查询公司员工的基本信息，支持按姓名和/或部门筛选。

    触发条件：当用户询问员工信息时使用，如「某某在哪个部门」「某部门有哪些人」「某某的联系方式」。
    注意：至少需要提供 name 或 department 其中一个参数。

    Args:
        name: 员工姓名，支持模糊匹配（部分匹配即可）。
              示例：「张」可匹配「张三」「张伟」
        department: 部门名称，支持模糊匹配。
              示例：「市场」可匹配「市场部」「市场营销部」
    """
    if not name and not department:
        return "【查询失败】请至少提供姓名或部门名称中的一个作为查询条件。"

    employees_file = settings.EMPLOYEES_FILE

    if not os.path.exists(employees_file):
        return "【系统提示】员工数据库暂未初始化，请先运行 scripts/seed_data.py 初始化数据。"

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
        return f"【查询结果】未找到匹配的员工信息。搜索条件：姓名=\"{name}\"，部门=\"{department}\"\n建议：检查姓名/部门名称是否正确，或尝试使用部分关键词搜索。"

    output = f"【查询结果】共找到 {len(results)} 位员工：\n\n"
    for e in results:
        output += f"<employee>\n"
        output += f"  姓名：{e['name']}\n"
        output += f"  部门：{e['department']}\n"
        output += f"  职位：{e['position']}\n"
        output += f"  邮箱：{e['email']}\n"
        if e.get("phone"):
            output += f"  电话：{e['phone']}\n"
        output += f"</employee>\n\n"

    return output


@tool
def list_documents_tool() -> str:
    """列出知识库中所有已索引的文档。

    触发条件：当用户想查看知识库中有哪些文档时使用。
    典型问题：「知识库有哪些文档」「文档列表」「你们有什么资料」。
    """
    docs = list_indexed_documents()

    if not docs:
        return "【文档列表】知识库中暂无文档。请先通过上传功能添加文档。"

    output = f"【文档列表】知识库中共有 {len(docs)} 个文档：\n\n"
    for i, doc in enumerate(docs, 1):
        # 根据文件类型标注
        ext = doc.rsplit('.', 1)[-1].lower() if '.' in doc else ''
        type_label = {'pdf': 'PDF文档', 'docx': 'Word文档', 'txt': '文本文件'}.get(ext, '文档')
        output += f"  {i}. {doc}（{type_label}）\n"

    return output


@tool
def upload_document_tool(file_path: str) -> str:
    """将新文档上传并索引到知识库，使其可被搜索。

    触发条件：当用户需要添加新文档到知识库时使用。
    支持格式：PDF、TXT、DOCX。
    处理流程：加载文件 → 文本分块 → 向量化 → 存入向量数据库。

    Args:
        file_path: 要上传的文档文件路径，必须是已存在于服务器上的文件。
    """
    if not os.path.exists(file_path):
        return f"【上传失败】文件不存在：{file_path}\n请确认文件路径是否正确，或先通过界面功能上传文件。"

    # 检查文件格式
    ext = file_path.rsplit('.', 1)[-1].lower() if '.' in file_path else ''
    supported = ['pdf', 'txt', 'docx']
    if ext not in supported:
        return f"【上传失败】不支持的文件格式：.{ext}。目前支持：{', '.join(['.'+e for e in supported])}"

    try:
        result = index_document(file_path)
        return f"【上传成功】文档已索引到知识库。{result['message']}"
    except Exception as e:
        return f"【上传失败】{str(e)}\n可能原因：文件损坏、内容为空或格式异常。请检查文件后重试。"


@tool
def delete_document_tool(filename: str) -> str:
    """从知识库中删除指定文档，同时移除其所有向量分块和原始文件。此操作不可恢复。

    触发条件：当用户确认要删除某个文档时使用。
    注意：删除操作不可逆，请在调用前确认用户已明确指定要删除的文档名称。

    Args:
        filename: 要删除的文档文件名（含扩展名），需与知识库中的文件名完全一致。
                  示例：「员工手册.pdf」而非「员工手册」
    """
    try:
        result = delete_document(filename)
        if result["status"] == "not_found":
            return f"【删除失败】文档 \"{filename}\" 在知识库中未找到。\n提示：请确认文件名是否正确（需包含扩展名），可通过 list_documents_tool 查看当前文档列表。"
        return f"【删除成功】{result['message']}"
    except Exception as e:
        return f"【删除失败】{str(e)}"


# ===== 导出所有工具列表 =====
ALL_TOOLS = [
    search_documents_tool,
    lookup_employee_tool,
    list_documents_tool,
    upload_document_tool,
    delete_document_tool,
]

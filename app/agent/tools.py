"""
Agent 工具定义模块
每个工具 = Agent 的一个「能力」
Agent 会根据用户问题自动选择调用哪个工具

Prompt Engineering 优化:
- 工具描述清晰定义触发条件和适用场景
- 参数说明包含类型、约束和使用建议
- 返回值格式标准化，便于 Agent 解析和引用
- 区分相似工具的适用场景，避免误选
"""
import json
import os
from typing import Optional

from langchain_core.tools import tool

from app.config import settings
from app.rag.document import search_documents, index_document, list_indexed_documents, delete_document


# ===== 联网搜索工具 =====
@tool
def web_search_tool(query: str) -> str:
    """搜索互联网获取实时信息。当你需要最新资讯、实时数据、或知识库中没有的信息时使用此工具。

    【用途】搜索互联网上的最新信息、新闻、实时数据等。
    【典型问题】「最新新闻」「今天天气」「某产品最新价格」「最新技术动态」「实时汇率」
    【不适用】查公司制度文档（用search_documents_tool）、查员工信息（用lookup_employee_tool）。

    Args:
        query: 搜索查询关键词。示例：「2024年最新AI技术动态」「北京今天天气」
    """
    try:
        import httpx
        from urllib.parse import quote_plus
        import re

        # 使用 Bing 搜索（国内可用：cn.bing.com）
        search_url = f"https://cn.bing.com/search?q={quote_plus(query)}&count=8"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        with httpx.Client(headers=headers, follow_redirects=True, timeout=15) as client:
            resp = client.get(search_url)
            html = resp.text

        # 解析 Bing 搜索结果
        results = []
        # Bing 搜索结果在 <li class="b_algo"> 中
        algo_pattern = re.compile(r'<li class="b_algo">(.*?)</li>', re.DOTALL)
        for match in algo_pattern.finditer(html):
            block = match.group(1)
            # 提取标题
            title_match = re.search(r'<a[^>]*>(.*?)</a>', block, re.DOTALL)
            title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else "无标题"
            # 提取链接
            href_match = re.search(r'href="(https?://[^"]+)"', block)
            href = href_match.group(1) if href_match else ""
            # 提取摘要
            snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
            if not snippet_match:
                snippet_match = re.search(r'<div class="b_caption"[^>]*>(.*?)</div>', block, re.DOTALL)
            snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip() if snippet_match else ""
            # 过滤掉空结果
            if title and title != "无标题":
                results.append({"title": title, "href": href, "snippet": snippet})

        if not results:
            return "【联网搜索】未找到相关结果。建议：1）尝试换用不同关键词搜索；2）检查网络连接是否正常。"

        output = f"【联网搜索】共找到 {len(results)} 条相关结果：\n\n"
        for i, r in enumerate(results[:5], 1):
            output += f"<web_result index=\"{i}\">\n"
            output += f"  标题：{r['title']}\n"
            output += f"  摘要：{r['snippet']}\n"
            if r['href']:
                output += f"  链接：{r['href']}\n"
            output += f"</web_result>\n\n"

        return output
    except Exception as e:
        return f"【联网搜索】搜索失败: {str(e)}\n建议：检查网络连接是否正常，或稍后重试。"


def _load_employees():
    """加载员工数据"""
    employees_file = settings.EMPLOYEES_FILE
    if not os.path.exists(employees_file):
        return None
    with open(employees_file, "r", encoding="utf-8") as f:
        return json.load(f)


@tool
def search_documents_tool(query: str) -> str:
    """搜索公司文档知识库，检索与查询语义相关的文档片段。

    【用途】查询公司制度、流程、规范、政策、规定等文档内容。
    【不适用】查员工信息（用lookup_employee_tool）、查看文档列表（用list_documents_tool）。

    Args:
        query: 搜索查询关键词。
               示例：「年假制度」「报销流程」「考勤规定」
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
    """查询公司员工信息。不传参数则列出全部员工，传参数则按条件筛选。

    【用途】查询员工姓名、部门、职位、联系方式等人员信息。
    【典型问题】「所有员工」「张三的信息」「技术部有哪些人」「公司有哪些部门的人」
    【不适用】查公司制度文档（用search_documents_tool）、查文档列表（用list_documents_tool）。

    Args:
        name: 员工姓名（可选，支持模糊匹配）。示例：「张」可匹配「张三」「张伟」
        department: 部门名称（可选，支持模糊匹配）。示例：「技术」可匹配「技术部」
    """
    employees = _load_employees()

    if employees is None:
        return "【系统提示】员工数据库暂未初始化，请先运行 scripts/seed_data.py 初始化数据。"

    results = employees

    # 按姓名过滤
    if name:
        results = [e for e in results if name in e.get("name", "")]

    # 按部门过滤
    if department:
        results = [e for e in results if department in e.get("department", "")]

    if not results:
        return f"【查询结果】未找到匹配的员工信息。搜索条件：姓名=\"{name}\"，部门=\"{department}\"\n建议：检查姓名/部门名称是否正确，或尝试使用部分关键词搜索。你也可以不传参数查看全部员工列表。"

    # 生成部门统计摘要
    dept_count = {}
    for e in results:
        dept = e.get("department", "未知")
        dept_count[dept] = dept_count.get(dept, 0) + 1

    output = f"【查询结果】共找到 {len(results)} 位员工"
    if dept_count:
        dept_summary = "、".join([f"{d} {c}人" for d, c in dept_count.items()])
        output += f"（{dept_summary}）"
    output += "：\n\n"

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
def list_departments_tool() -> str:
    """列出公司所有部门及各部门人数。

    【用途】当用户想知道公司有哪些部门、各部门有多少人时使用。
    【典型问题】「公司有哪些部门」「部门列表」「都有什么部门」。
    """
    employees = _load_employees()

    if employees is None:
        return "【系统提示】员工数据库暂未初始化，请先运行 scripts/seed_data.py 初始化数据。"

    # 统计部门
    dept_employees = {}
    for e in employees:
        dept = e.get("department", "未知")
        if dept not in dept_employees:
            dept_employees[dept] = []
        dept_employees[dept].append(e['name'])

    if not dept_employees:
        return "【查询结果】暂无部门信息。"

    output = f"【部门列表】公司共有 {len(dept_employees)} 个部门，{len(employees)} 位员工：\n\n"
    for i, (dept, names) in enumerate(dept_employees.items(), 1):
        output += f"  {i}. **{dept}**（{len(names)}人）：{'、'.join(names)}\n"

    output += f"\n如需查看某部门员工的详细信息，请告诉我部门名称。"

    return output


@tool
def list_documents_tool() -> str:
    """列出知识库中所有已索引的文档。

    【用途】查看知识库中有哪些可搜索的文档。
    【典型问题】「知识库有哪些文档」「文档列表」「你们有什么资料」。
    【不适用】查员工信息（用lookup_employee_tool）、查公司制度内容（用search_documents_tool）。
    """
    docs = list_indexed_documents()

    if not docs:
        return "【文档列表】知识库中暂无文档。请先通过上传功能添加文档。"

    output = f"【文档列表】知识库中共有 {len(docs)} 个文档：\n\n"
    for i, doc in enumerate(docs, 1):
        ext = doc.rsplit('.', 1)[-1].lower() if '.' in doc else ''
        type_label = {'pdf': 'PDF文档', 'docx': 'Word文档', 'txt': '文本文件'}.get(ext, '文档')
        output += f"  {i}. {doc}（{type_label}）\n"

    return output


@tool
def upload_document_tool(file_path: str) -> str:
    """将新文档上传并索引到知识库，使其可被搜索。

    【用途】当用户需要添加新文档到知识库时使用。
    支持格式：PDF、TXT、DOCX。

    Args:
        file_path: 要上传的文档文件路径，必须是已存在于服务器上的文件。
    """
    if not os.path.exists(file_path):
        return f"【上传失败】文件不存在：{file_path}\n请确认文件路径是否正确，或先通过界面功能上传文件。"

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

    【用途】当用户确认要删除某个文档时使用。
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


# ===== 导出工具列表 =====

# 基础工具（始终可用）
BASE_TOOLS = [
    search_documents_tool,
    lookup_employee_tool,
    list_departments_tool,
    list_documents_tool,
    upload_document_tool,
    delete_document_tool,
]

# 联网搜索工具（按需启用）
WEB_SEARCH_TOOLS = [
    web_search_tool,
]

# 全部工具
ALL_TOOLS = BASE_TOOLS + WEB_SEARCH_TOOLS


def get_tools(web_search: bool = False):
    """根据参数获取工具列表

    Args:
        web_search: 是否启用联网搜索工具

    Returns:
        工具列表
    """
    if web_search:
        return ALL_TOOLS
    return BASE_TOOLS

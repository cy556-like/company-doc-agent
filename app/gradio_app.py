"""
Gradio 前端界面
提供登录/注册 + 聊天界面，挂载到 FastAPI 上
"""
import os
import shutil
import gradio as gr
from app.agent.core import chat
from app.rag.document import index_document, list_indexed_documents, read_document_content
from app.config import settings
from app.auth.user_manager import verify_user, register_user
from app.memory.manager import get_history_for_gradio, clear_session_history


def save_modified_file(original_name: str, content: str) -> tuple:
    """根据原始文件格式保存修改后的文档"""
    base_name = os.path.splitext(original_name)[0]
    ext = os.path.splitext(original_name)[1].lower()

    if ext == ".docx":
        try:
            from docx import Document
            doc = Document()
            for paragraph_text in content.split("\n"):
                doc.add_paragraph(paragraph_text)
            modified_name = f"{base_name}_modified.docx"
            modified_path = os.path.join(settings.DOCUMENTS_DIR, modified_name)
            doc.save(modified_path)
            return modified_path, modified_name
        except ImportError:
            pass

    modified_name = f"{base_name}_modified.txt"
    modified_path = os.path.join(settings.DOCUMENTS_DIR, modified_name)
    with open(modified_path, "w", encoding="utf-8") as f:
        f.write(content)
    return modified_path, modified_name


def gradio_chat(message: str, history: list, session_id: str, file) -> tuple:
    """统一处理对话和文档修改"""
    if not message.strip() and file is None:
        return "", history, None

    # 情况1：有文件 + 有文字 → 文档修改
    if file is not None and message.strip():
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage

            original_name = getattr(file, 'orig_name', None) or os.path.basename(file.name)
            original_content = read_document_content(file.name)

            llm = ChatOpenAI(
                api_key=settings.LLM_API_KEY,
                base_url=settings.LLM_BASE_URL,
                model=settings.LLM_MODEL,
                temperature=0.3,
            )

            prompt = f"""请根据以下要求修改文档内容，直接输出修改后的完整文档内容，不要输出其他说明。

原始文档内容：
---
{original_content}
---

修改要求：{message}

请直接输出修改后的完整文档："""

            response = llm.invoke([HumanMessage(content=prompt)])
            modified_path, modified_name = save_modified_file(original_name, response.content)

            history.append({"role": "user", "content": f"[修改文档] {original_name}\n修改要求：{message}"})
            history.append({"role": "assistant", "content": f"文档修改完成！\n\n修改后的文件：{modified_name}\n点击下方链接下载"})

            return "", history, modified_path

        except Exception as e:
            history.append({"role": "user", "content": f"[修改文档] {message}"})
            history.append({"role": "assistant", "content": f"文档修改失败: {str(e)}"})
            return "", history, None

    # 情况2：有文件 + 没文字 → 上传文档到知识库
    if file is not None and not message.strip():
        try:
            original_name = getattr(file, 'orig_name', None) or os.path.basename(file.name)
            dest_path = os.path.join(settings.DOCUMENTS_DIR, original_name)
            shutil.copy2(file.name, dest_path)
            result = index_document(dest_path, original_name)
            history.append({"role": "user", "content": f"[上传文档] {original_name}"})
            history.append({"role": "assistant", "content": result['message']})
            return "", history, None
        except Exception as e:
            history.append({"role": "user", "content": "[上传文档]"})
            history.append({"role": "assistant", "content": f"上传失败: {str(e)}"})
            return "", history, None

    # 情况3：没文件 + 有文字 → 普通对话
    try:
        response = chat(message, session_id=session_id)
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": response})
        return "", history, None
    except Exception as e:
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": f"出错了: {str(e)}\n\n请检查 API Key 和网络设置"})
        return "", history, None


def gradio_list_docs() -> str:
    docs = list_indexed_documents()
    if not docs:
        return "知识库中暂无文档，请先上传。"
    output = f"知识库中共有 {len(docs)} 个文档：\n\n"
    for i, doc in enumerate(docs, 1):
        output += f"  {i}. {doc}\n"
    return output


def create_gradio_app():
    with gr.Blocks(title="企业文档智能助手") as demo:

        # 用 State 记录当前登录用户
        current_user = gr.State(None)

        # ===== 登录/注册区域 =====
        with gr.Column(visible=True) as login_section:
            gr.Markdown("# 企业文档智能助手\n请登录或注册后使用")

            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### 登录")
                    login_user = gr.Textbox(label="用户名", placeholder="输入用户名")
                    login_pass = gr.Textbox(label="密码", type="password", placeholder="输入密码")
                    login_btn = gr.Button("登录", variant="primary")
                    login_msg = gr.Markdown("")

                with gr.Column(scale=1):
                    gr.Markdown("### 注册新用户")
                    reg_user = gr.Textbox(label="用户名", placeholder="设置用户名（至少2个字符）")
                    reg_pass = gr.Textbox(label="密码", type="password", placeholder="设置密码（至少4个字符）")
                    reg_btn = gr.Button("注册")
                    reg_msg = gr.Markdown("")

        # ===== 对话区域（登录后显示）=====
        with gr.Column(visible=False) as chat_section:
            welcome_text = gr.Markdown("# 企业文档智能助手")
            gr.Markdown("> 基于 LangChain + LangGraph 的 ReAct Agent\n\n选择文档 + 输入修改要求 = AI 修改文档 | 不选文档 = 普通对话")

            chatbot = gr.Chatbot(label="对话", height=500)

            with gr.Row():
                msg_input = gr.Textbox(
                    label="输入问题或修改要求",
                    placeholder="例如：公司年假制度是什么？\n选择文档后输入：把语气改得更正式",
                    scale=4,
                    lines=2,
                )
                send_btn = gr.Button("发送", variant="primary", scale=1)

            with gr.Row():
                file_input = gr.File(
                    label="选择文档（可选）",
                    file_types=[".pdf", ".txt", ".docx"],
                    scale=3,
                )
                download_file = gr.File(
                    label="下载文件",
                    scale=3,
                    interactive=False,
                )

            with gr.Row():
                session_id = gr.Textbox(label="会话 ID", value="default", visible=False)
                list_btn = gr.Button("查看知识库文档", scale=1)
                delete_history_btn = gr.Button("删除对话历史", scale=1)
                logout_btn = gr.Button("退出登录", scale=1)

            docs_list = gr.Textbox(label="文档列表", interactive=False, lines=5)

        # ===== 登录逻辑 =====
        def handle_login(username, password):
            if not username.strip() or not password.strip():
                return (
                    None,
                    gr.update(visible=True),
                    gr.update(visible=False),
                    [],
                    "default",
                    "# 企业文档智能助手",
                    "<span style='color:red'>请输入用户名和密码</span>",
                )
            if verify_user(username, password):
                history = get_history_for_gradio(username)
                return (
                    username,
                    gr.update(visible=False),
                    gr.update(visible=True),
                    history,
                    username,
                    f"# 企业文档智能助手\n欢迎，**{username}**！",
                    "",
                )
            else:
                return (
                    None,
                    gr.update(visible=True),
                    gr.update(visible=False),
                    [],
                    "default",
                    "# 企业文档智能助手",
                    "<span style='color:red'>用户名或密码错误</span>",
                )

        def handle_register(username, password):
            if not username.strip() or not password.strip():
                return "<span style='color:red'>请输入用户名和密码</span>"
            success, msg = register_user(username, password)
            if success:
                return f"<span style='color:green'>{msg}</span>"
            else:
                return f"<span style='color:red'>{msg}</span>"

        def handle_logout(user):
            return (
                None,
                gr.update(visible=True),
                gr.update(visible=False),
                [],
                "default",
                "# 企业文档智能助手",
                "",
                "",
                "",
            )

        def handle_delete_history(user):
            if user:
                clear_session_history(user)
            return [], None

        def send_message(message, history, sid, file, user):
            if not user:
                return message, history, None, None
            msg, new_history, dl_file = gradio_chat(message, history, sid, file)
            return msg, new_history, dl_file, None

        # ===== 绑定事件 =====
        login_btn.click(
            handle_login,
            inputs=[login_user, login_pass],
            outputs=[current_user, login_section, chat_section, chatbot, session_id, welcome_text, login_msg],
        )

        login_pass.submit(
            handle_login,
            inputs=[login_user, login_pass],
            outputs=[current_user, login_section, chat_section, chatbot, session_id, welcome_text, login_msg],
        )

        reg_btn.click(
            handle_register,
            inputs=[reg_user, reg_pass],
            outputs=[reg_msg],
        )

        logout_btn.click(
            handle_logout,
            inputs=[current_user],
            outputs=[current_user, login_section, chat_section, chatbot, session_id, welcome_text, login_user, login_pass],
        )

        delete_history_btn.click(
            handle_delete_history,
            inputs=[current_user],
            outputs=[chatbot, download_file],
        )

        msg_input.submit(
            send_message,
            inputs=[msg_input, chatbot, session_id, file_input, current_user],
            outputs=[msg_input, chatbot, download_file, file_input],
        )

        send_btn.click(
            send_message,
            inputs=[msg_input, chatbot, session_id, file_input, current_user],
            outputs=[msg_input, chatbot, download_file, file_input],
        )

        list_btn.click(
            gradio_list_docs,
            outputs=[docs_list],
        )

    return demo
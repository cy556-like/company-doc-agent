"""
FastAPI 应用主入口
启动 API 服务 + Gradio 前端
"""
import os
import sys

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import router


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    app = FastAPI(
        title="企业文档智能助手 Agent",
        description="""
        基于 LangChain + LangGraph 的企业文档智能助手

        ## 功能
        - 文档问答：上传公司文档，AI 自动回答相关问题
        - 员工查询：查询员工信息、部门归属
        - 文档搜索：语义搜索文档内容
        - 多轮对话：支持上下文连续对话

        ## 技术栈
        - LangChain + LangGraph (ReAct Agent)
        - ChromaDB (向量数据库)
        - FastAPI (后端服务)
        - Gradio (前端界面)
        """,
        version="1.0.0",
    )

    # CORS 跨域支持
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册 API 路由
    app.include_router(router, prefix="/api/v1", tags=["Agent API"])

    # 健康检查
    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "company-doc-agent"}

    return app


app = create_app()


if __name__ == "__main__":
    # 确保数据目录存在
    os.makedirs(settings.DOCUMENTS_DIR, exist_ok=True)
    os.makedirs(settings.CHROMA_DIR, exist_ok=True)

    # 创建 Gradio 界面并挂载到 FastAPI
    from app.gradio_app import create_gradio_app
    import gradio as gr

    demo = create_gradio_app()
    app = gr.mount_gradio_app(app, demo, path="/ui")

    print("=" * 50)
    print("企业文档智能助手 Agent 启动中...")
    print(f"  API 地址: http://localhost:{settings.APP_PORT}")
    print(f"  API 文档: http://localhost:{settings.APP_PORT}/docs")
    print(f"  Gradio 界面: http://localhost:{settings.APP_PORT}/ui")
    print("=" * 50)

    uvicorn.run(
        app,
        host=settings.APP_HOST,
        port=settings.APP_PORT,
    )
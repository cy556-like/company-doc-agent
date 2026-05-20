"""
应用配置管理
支持动态切换 LLM 模型
"""
import os
from dotenv import load_dotenv

load_dotenv()

# 可用的 LLM 模型列表
AVAILABLE_MODELS = [
    # GLM-5 系列（最新）
    {"id": "glm-5.1", "name": "GLM-5.1", "desc": "最新旗舰，Coding对齐Claude Opus 4.6"},
    {"id": "glm-5-turbo", "name": "GLM-5-Turbo", "desc": "高智能基座，Agent能力SOTA"},
    {"id": "glm-5", "name": "GLM-5", "desc": "高智能基座，编程对齐Claude Opus 4.5"},
    # GLM-4.7 系列
    {"id": "glm-4.7", "name": "GLM-4.7", "desc": "高性能，综合能力提升"},
    {"id": "glm-4.7-flash", "name": "GLM-4.7-Flash", "desc": "快速版，性价比高"},
    # GLM-4 系列（经典）
    {"id": "glm-4-plus", "name": "GLM-4-Plus", "desc": "高性能，复杂任务首选"},
    {"id": "glm-4-long", "name": "GLM-4-Long", "desc": "超长上下文，支持128K"},
    {"id": "glm-4-flash", "name": "GLM-4-Flash", "desc": "最快，适合日常对话"},
    {"id": "glm-4-air", "name": "GLM-4-Air", "desc": "均衡，速度与质量兼顾"},
    {"id": "glm-4-air-0111", "name": "GLM-4-Air-0111", "desc": "Air升级版，效果更好"},
    {"id": "glm-4", "name": "GLM-4", "desc": "经典旗舰模型"},
]


class Settings:
    """应用配置"""

    # LLM 配置
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "glm-4-flash")

    # Embedding 模型
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "embedding-3")

    # 应用配置
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))

    # 数据目录
    DATA_DIR: str = os.getenv("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
    DOCUMENTS_DIR: str = os.getenv("DOCUMENTS_DIR", os.path.join(DATA_DIR, "documents"))
    CHROMA_DIR: str = os.getenv("CHROMA_DIR", os.path.join(DATA_DIR, "chroma_db"))
    EMPLOYEES_FILE: str = os.getenv("EMPLOYEES_FILE", os.path.join(DATA_DIR, "employees.json"))


settings = Settings()


def set_current_model(model_id: str) -> bool:
    """动态切换当前使用的模型"""
    valid_ids = [m["id"] for m in AVAILABLE_MODELS]
    if model_id in valid_ids:
        settings.LLM_MODEL = model_id
        # 重置 Agent 单例，让下次对话使用新模型
        from app.agent.core import reset_agent
        reset_agent()
        return True
    return False


def get_current_model() -> str:
    """获取当前使用的模型ID"""
    return settings.LLM_MODEL

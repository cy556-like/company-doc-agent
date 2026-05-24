# 企业智能助手 Agent2

这是一个基于 **LangChain + LangGraph + FastAPI + ChromaDB** 的企业文档智能问答系统，采用 **ReAct Agent** 模式。

### 🛠 技术栈

| 组件 | 技术 |
|------|------|
| 大模型 | 智谱 GLM 系列（GLM-5.1 / GLM-4-Flash 等） |
| Agent 框架 | LangGraph（ReAct 推理+行动循环） |
| RAG | ChromaDB + embedding-3 向量检索 |
| 后端 | FastAPI + SSE 流式输出 |
| 前端 | ChatGPT 风格界面 |

### ✨ 核心功能

- 📄 **RAG 文档问答**：上传文档后进行智能问答
- 👥 **员工信息查询**：查询公司员工信息
- 📝 **文档管理**：支持文档上传、删除
- 💬 **流式对话**：SSE 逐字输出，体验流畅
- 🔐 **用户认证**：注册/登录系统
- 📊 **多轮对话**：支持会话历史管理

### 📁 项目结构

```
app/
├── main.py          # FastAPI 入口
├── agent/
│   ├── core.py      # Agent 核心逻辑（ReAct）
│   ├── prompts.py   # 系统提示词
│   └── tools.py     # 工具集
├── rag/             # 文档索引与检索
├── memory/          # 对话历史管理
├── auth/            # 用户认证
└── static/          # 前端界面
```
简单来说，这就是**一个企业级的 AI 智能助手系统**，我就是运行在这个项目上的！😄

（来源：[GitHub - cy556-like/company-doc-agent](https://github.com/cy556-like/company-doc-agent)）
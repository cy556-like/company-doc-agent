# 企业文档智能助手 Agent

基于 **LangChain + LangGraph + FastAPI + ChromaDB** 的企业文档智能助手，采用 ReAct Agent 模式，支持 RAG 文档问答、员工查询、文档修改、流式输出等功能。

## 项目架构

```
company-doc-agent/
├── app/
│   ├── main.py                 # FastAPI 应用入口
│   ├── config.py               # 配置管理（模型列表、环境变量）
│   ├── agent/
│   │   ├── core.py             # Agent 核心逻辑（ReAct + 流式输出）
│   │   ├── prompts.py          # 系统提示词
│   │   └── tools.py            # Agent 工具集（5个工具）
│   ├── api/
│   │   └── routes.py           # API 路由（REST + SSE 流式端点）
│   ├── rag/
│   │   └── document.py         # RAG 文档索引与检索
│   ├── memory/
│   │   └── manager.py          # 多轮对话历史管理
│   ├── auth/
│   │   └── user_manager.py     # 用户注册/登录
│   ├── utils/
│   │   └── pdf_generator.py    # PDF 生成（fpdf2 + 中文支持）
│   └── static/
│       └── index.html          # ChatGPT 风格前端界面
├── data/                       # 运行时数据（自动创建）
│   ├── documents/              # 上传的文档
│   ├── chroma_db/              # 向量数据库
│   ├── conversations/          # 对话历史
│   └── users/                  # 用户数据
├── .env                        # 环境变量配置
├── requirements.txt            # Python 依赖
└── README.md
```

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| LLM | 智谱 GLM 系列 | GLM-5.1 / GLM-5-Turbo / GLM-4-Flash 等 |
| Agent | LangGraph (ReAct) | 推理+行动循环，最多3轮工具调用 |
| RAG | ChromaDB + embedding-3 | 向量存储与语义检索 |
| 后端 | FastAPI + SSE | REST API + 流式输出 |
| 前端 | HTML/CSS/JS | ChatGPT 风格，支持逐字流式渲染 |
| PDF | fpdf2 | 中文 PDF 生成 |

## 环境要求

- Python 3.10+
- Windows / Linux（ECS）

## 安装依赖

```bash
pip install -r requirements.txt
```

依赖包含：

```
fastapi, uvicorn, python-dotenv, pydantic    # Web 框架
langchain, langchain-openai, langgraph       # Agent 框架
chromadb, pypdf, docx2txt, fpdf2             # RAG 与文档处理
httpx                                         # HTTP 客户端
```

## 环境变量配置

在项目根目录创建 `.env` 文件：

```env
# LLM 配置（智谱 API）
LLM_API_KEY=你的智谱API密钥
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
LLM_MODEL=glm-4-flash

# Embedding 模型
EMBEDDING_MODEL=embedding-3

# 服务配置（可选）
APP_HOST=0.0.0.0
APP_PORT=8000
```

> 智谱 API 密钥获取：https://open.bigmodel.cn/

## 启动服务

```bash
# 开发模式（热重载）
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 生产模式
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

启动后访问：
- 前端界面：`http://你的IP:8000`
- API 文档：`http://你的IP:8000/docs`
- 健康检查：`http://你的IP:8000/health`

## API 端点一览

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/login` | 用户登录 |
| POST | `/api/v1/auth/register` | 用户注册 |

### 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/chat` | 普通对话（非流式） |
| POST | `/api/v1/chat/stream` | 流式对话（SSE 逐字输出） |
| POST | `/api/v1/chat-with-file` | 文件+对话（非流式） |
| POST | `/api/v1/chat-with-file/stream` | 文件+对话（流式 SSE） |

### 会话管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/chats` | 创建新会话 |
| GET | `/api/v1/chats` | 获取会话列表 |
| DELETE | `/api/v1/chats/{id}` | 删除会话 |
| PUT | `/api/v1/chats/{id}/rename` | 重命名会话 |
| GET | `/api/v1/history/{id}` | 获取对话历史 |
| DELETE | `/api/v1/history/{id}` | 清除对话历史 |

### 文档与模型

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/upload` | 上传文档到知识库 |
| GET | `/api/v1/documents` | 列出已索引文档 |
| POST | `/api/v1/search` | 搜索文档内容 |
| GET | `/api/v1/models` | 获取可用模型列表 |
| POST | `/api/v1/models/set` | 切换当前模型 |

## Agent 工具

| 工具 | 功能 | 触发方式 |
|------|------|----------|
| search_documents_tool | 语义搜索知识库文档 | 用户问文档相关问题 |
| lookup_employee_tool | 查询员工信息 | 用户问员工/部门信息 |
| list_documents_tool | 列出所有已索引文档 | 用户问有哪些文档 |
| upload_document_tool | 上传文档到知识库 | 用户要求上传 |
| modify_document_tool | 修改文档并生成 PDF | 用户明确要求修改文档 |

## 流式输出说明

前端默认使用 SSE 流式端点，体验效果：

1. **思考阶段** → 显示旋转动画 + "正在思考..."
2. **工具调用** → 显示工具标签（如 "搜索文档..." → "搜索文档 完成"）
3. **逐字输出** → 每个 token 实时渲染，带闪烁光标
4. **完成** → 光标消失，回答完整显示

后端实现：`agent.astream_events(version="v2")` + FastAPI `StreamingResponse`

## GitHub 与 ECS 同步

> 由于国内 ECS 无法直接访问 github.com，需通过 **GitHub API (api.github.com)** 同步文件。

### 前置条件

- GitHub 仓库：`cy556-like/company-doc-agent`
- GitHub Token：需有 repo 权限

### 本地推送到 GitHub

```bash
# 修改代码后
git add .
git commit -m "描述你的修改"
git push origin main
```

### ECS 从 GitHub 拉取单个文件

```powershell
# 通用模板（替换 {文件路径} 即可）
python -c "import requests,base64; r=requests.get('https://api.github.com/repos/cy556-like/company-doc-agent/contents/{文件路径}', headers={'Authorization':'token 你的GitHub Token','Accept':'application/vnd.github.v3+json'}); open('{文件路径}','wb').write(base64.b64decode(r.json()['content'])); print('updated')"

# 示例：更新 core.py
python -c "import requests,base64; r=requests.get('https://api.github.com/repos/cy556-like/company-doc-agent/contents/app/agent/core.py', headers={'Authorization':'token ghp_xxx','Accept':'application/vnd.github.v3+json'}); open('app/agent/core.py','wb').write(base64.b64decode(r.json()['content'])); print('updated')"

# 示例：更新 index.html
python -c "import requests,base64; r=requests.get('https://api.github.com/repos/cy556-like/company-doc-agent/contents/app/static/index.html', headers={'Authorization':'token ghp_xxx','Accept':'application/vnd.github.v3+json'}); open('app/static/index.html','wb').write(base64.b64decode(r.json()['content'])); print('updated')"
```

### 一次性更新所有核心文件

```powershell
# 在 ECS 项目根目录执行
$token = "你的GitHub Token"
$repo = "cy556-like/company-doc-agent"
$files = @(
    "app/agent/core.py",
    "app/agent/tools.py",
    "app/agent/prompts.py",
    "app/api/routes.py",
    "app/config.py",
    "app/main.py",
    "app/static/index.html",
    "app/rag/document.py",
    "app/memory/manager.py",
    "app/utils/pdf_generator.py"
)

foreach ($f in $files) {
    $url = "https://api.github.com/repos/$repo/contents/$f"
    $headers = @{ "Authorization" = "token $token"; "Accept" = "application/vnd.github.v3+json" }
    $resp = Invoke-RestMethod -Uri $url -Headers $headers
    $content = [System.Convert]::FromBase64String($resp.content)
    [System.IO.File]::WriteAllBytes($f, $content)
    Write-Host "Updated: $f"
}
```

### 同步后重启服务

```powershell
# 如果用 --reload 模式，修改文件会自动重启
# 否则手动重启
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 常见问题

### Q: 如何添加新的 LLM 模型？

编辑 `app/config.py` 中的 `AVAILABLE_MODELS` 列表，添加新模型的 `id`、`name`、`desc`，然后同步到 ECS 并重启。

### Q: 如何修改 Agent 的行为？

编辑 `app/agent/prompts.py` 中的 `SYSTEM_PROMPT`，调整 Agent 的角色设定和行为规则。

### Q: 如何添加新的 Agent 工具？

1. 在 `app/agent/tools.py` 中定义新工具函数并加 `@tool` 装饰器
2. 将新工具加入 `ALL_TOOLS` 列表
3. 在 `app/agent/core.py` 的 `TOOL_DISPLAY_NAMES` 中添加中文名映射
4. 同步到 ECS 并重启

### Q: 为什么 ECS 上 github.com 无法访问？

国内服务器访问 GitHub 不稳定，使用 `api.github.com`（GitHub API）可以正常访问，通过 API 下载文件内容并写入本地即可同步。

### Q: 流式输出不生效？

1. 确认后端 `core.py` 中 `create_llm()` 有 `streaming=True`
2. 确认前端 `sendMessage()` 调用的是 `/chat/stream` 而非 `/chat`
3. 浏览器 F12 Network 面板查看是否有 SSE 请求

# 🍓 智能营销助手 (Smart Marketing Assistant)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![Gradio](https://img.shields.io/badge/Gradio-4.0+-orange.svg)](https://gradio.app/)
[![LangChain](https://img.shields.io/badge/LangChain-0.1+-blue.svg)](https://python.langchain.com/)

智能营销助手是一个基于大语言模型（LLM）的垂直领域 AI Agent，旨在为营销人员提供市场洞察、数据分析、文案生成及业务咨询服务。项目采用 **前后端分离** 架构，后端基于 FastAPI + LangGraph 构建智能体编排，前端使用 Gradio 提供交互界面，支持流式对话、图表渲染及断点重传。

## ✨ 核心功能

*   **💬 多轮流式对话**：支持打字机效果的实时流式响应，提供流畅的聊天体验。
*   **🧠 智能意图识别**：自动识别用户意图（闲聊/业务分析），动态路由至不同的处理流程。
*   **🛠️ 多模态工具链**：
    *   **知识库检索 (RAG)**：基于 pgvector 的向量检索，回答关于平台规则、操作指南等专业问题。
    *   **市场调研 (Manus)**：集成 Manus AI 进行深度联网搜索，生成市场趋势报告。
    *   **数据分析**：自动生成可视化图表（Matplotlib）。
    *   **抖音业务模拟**：模拟查询抖音销量、评价、验券记录等业务数据。
    *   **环境感知**：获取实时天气、节假日信息，辅助营销决策。
*   **💾 持久化记忆与会话管理**：
    *   **Thread ID**：基于 PostgreSQL 的长期记忆，支持跨会话的历史回溯。
    *   **Request ID**：基于 Redis Stream 的短期记忆，支持断点重传（Resume）机制。
*   **⚙️ 动态配置管理**：集成 **Nacos** 配置中心，支持 Prompt（提示词）的在线热更新与版本回滚，无需重启服务。
*   **📊 全链路可观测性**：接入 **Arize Phoenix**，实现对 Agent 思考过程、工具调用及 Token 消耗的实时追踪与可视化。

## 🏗️ 技术架构

*   **Frontend**: Gradio (Web UI)
*   **Backend**: FastAPI (REST API + SSE Streaming)
*   **Agent Orchestration**: LangGraph (StateGraph)
*   **LLM Framework**: LangChain
*   **Database**: PostgreSQL (pgvector for Vector Store & Checkpoints)
*   **Message Queue**: Redis (Stream for Chat History & Event Sourcing)
*   **Configuration**: Nacos (Dynamic Configuration)
*   **Observability**: Arize Phoenix (OpenTelemetry Tracing)

## 🚀 快速开始

### 1. 环境准备

确保本地已安装以下服务：
*   **Python 3.10+**
*   **PostgreSQL** (需开启 `vector` 插件)
*   **Redis**
*   **Nacos** (可选，用于动态 Prompt 管理，若不启用将使用本地默认配置)

### 2. 安装依赖

```bash
# 克隆项目
git clone <repository_url>
cd marketing-assistant

# 创建虚拟环境 (推荐)
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置文件

在项目根目录创建 `.env` 文件，填入以下配置：

```ini
# LLM & API Keys
DEEPSEEK_API_KEY=your_deepseek_key
MANUS_API_KEY=your_manus_key
QWEATHER_KEY=your_qweather_key
AMAP_KEY=your_amap_key

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/marketing_agent

# Redis
REDIS_URL=redis://localhost:6379

# Nacos (Optional)
NACOS_SERVER_ADDR=127.0.0.1:8848
NACOS_NAMESPACE=public
NACOS_USERNAME=nacos
NACOS_PASSWORD=nacos

# Phoenix (Optional, for tracing)
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces
```

### 4. 初始化数据库

```bash
# 初始化表结构 (products, knowledge_chunks 等)
python scripts/init_db.py

# (可选) 导入初始商品数据
python scripts/insert_products_20260211.py

# (可选) 导入知识库文档 (需将 PDF 放入 app/knowledge/knowledge_db/)
# python app/knowledge/ingest.py
```

### 5. 启动服务

**步骤 1: 启动后端 API**

```bash
python server_redis.py
```
*   后端服务默认运行在 `http://localhost:8000`
*   会自动启动 Phoenix 监控服务（默认端口 6006）

**步骤 2: 启动前端 UI**

```bash
python web_ui.py
```
*   前端界面默认运行在 `http://localhost:7860`

## 📂 目录结构

```text
.
├── app/
│   ├── agents/             # Agent 核心逻辑
│   │   ├── tools/          # 工具集 (Search, Analysis, Chart, etc.)
│   │   └── memory_agent.py # LangGraph 编排与状态管理
│   ├── core/               # 核心组件 (LLM Client)
│   ├── knowledge/          # 知识库管理 (Ingest, Retrieval)
│   └── utils/              # 通用工具 (Nacos Client)
├── scripts/                # 初始化与数据脚本
├── static/                 # 静态资源 (生成的图表、上传的文件)
├── server_redis.py         # 后端入口 (FastAPI)
├── web_ui.py               # 前端入口 (Gradio)
├── requirements.txt        # 项目依赖
└── README.md               # 项目文档
```

## 🛠️ Nacos 配置说明

项目支持将关键 Prompt 托管至 Nacos，Data ID 如下：
*   `intent_classification_prompt`: 意图识别提示词
*   `available_tools_prompt`: 可用工具描述
*   `tool_planner_system_prompt`: 工具规划器系统提示词
*   `final_response_system_prompt`: 最终回复生成提示词
*   `knowledge_query_rewrite_prompt`: 知识库查询改写提示词

## 📊 可视化监控

启动后端后，访问 `http://localhost:6006` 即可进入 Phoenix 控制台，查看详细的 Trace 链路、Token 消耗及 Latency 分析。

## 📝 License

[MIT License](LICENSE)

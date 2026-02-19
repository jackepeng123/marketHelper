import asyncio
import json
import os
import atexit
import subprocess
import uuid
import redis.asyncio as redis
from typing import AsyncGenerator

from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from sse_starlette.sse import EventSourceResponse

# 复用已有的 Agent 逻辑
from app.agents.memory_agent import AgentState, _node_route, _node_chat, _node_analysis

_ = load_dotenv(find_dotenv())
DATABASE_URL = os.getenv("DATABASE_URL")

import signal
# import psutil # Unused

def kill_process_on_port(port):
    """根据端口号杀死占用该端口的进程"""
    try:
        # 使用 lsof 查找占用端口的进程
        # 注意：这里假设是在 Unix/Linux/macOS 环境下
        cmd = f"lsof -t -i:{port}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        pids = result.stdout.strip().split('\n')
        
        for pid in pids:
            if pid:
                try:
                    # 尝试优雅终止
                    os.kill(int(pid), signal.SIGTERM)
                    print(f"✅ Killed process {pid} on port {port}")
                except ProcessLookupError:
                    pass
                except Exception as e:
                    print(f"⚠️ Failed to kill process {pid} on port {port}: {e}")
                    # 如果需要更强力的清理，可以使用 SIGKILL
                    # os.kill(int(pid), signal.SIGKILL)
    except Exception as e:
        print(f"⚠️ Error checking port {port}: {e}")

def _maybe_start_phoenix_server() -> None:
    auto_start = os.getenv("PHOENIX_AUTO_START", "1").lower() not in {"0", "false", "no"}
    if not auto_start:
        return
    if not DATABASE_URL:
        return
    if os.getenv("PHOENIX_COLLECTOR_ENDPOINT"):
        return

    phoenix_port = os.getenv("PHOENIX_PORT", "6006")
    grpc_port = os.getenv("PHOENIX_GRPC_PORT", "4317")
    
    # ⚠️ 端口清理：在启动前清理占用端口的进程
    print(f"🧹 Checking ports {phoenix_port} and {grpc_port}...")
    kill_process_on_port(phoenix_port)
    kill_process_on_port(grpc_port)

    os.environ["PHOENIX_PORT"] = phoenix_port
    os.environ["PHOENIX_GRPC_PORT"] = grpc_port
    os.environ.setdefault("PHOENIX_SQL_DATABASE_URL", DATABASE_URL)
    os.environ.setdefault("PHOENIX_SQL_DATABASE_SCHEMA", os.getenv("PHOENIX_SQL_DATABASE_SCHEMA") or "phoenix")
    os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = f"http://localhost:{phoenix_port}/v1/traces"

    # 启动应用
    print(f"🚀 Starting Phoenix server on port {phoenix_port} (gRPC: {grpc_port})...")
    proc = subprocess.Popen(
        ["phoenix", "serve"],
        env=os.environ.copy(),
        stdout=None, # 可以重定向到文件以调试
        stderr=None,
        start_new_session=True, # 创建新进程组，避免收到父进程的信号
    )

    def _cleanup() -> None:
        print("🛑 Stopping Phoenix server...")
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutError:
                proc.kill()
        
        # 再次确保端口被释放
        kill_process_on_port(phoenix_port)
        kill_process_on_port(grpc_port)

    atexit.register(_cleanup)
    # 注册信号处理，确保 Ctrl+C 也能触发清理
    signal.signal(signal.SIGINT, lambda sig, frame: (_cleanup(), exit(0)))
    signal.signal(signal.SIGTERM, lambda sig, frame: (_cleanup(), exit(0)))

_maybe_start_phoenix_server()

from phoenix.otel import register

# -------------------------------------------------------------------------
# Phoenix 埋点配置
# -------------------------------------------------------------------------
# 1. 注册 Phoenix OpenTelemetry
# 这会自动拦截 LangChain/LangGraph 的内部调用，并发送给本地 Phoenix Server
# ⚠️ 修复：增加 instrument=True 以确保自动开启 LangChain Instrumentation
tracer_provider = register(
    project_name="marketing-agent", # 项目名称
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT") or "http://localhost:6006/v1/traces"
)

# 2. 显式开启 LangChain 的自动埋点 (有时候 register 默认不开启)
# ⚠️ 修正：LangChainInstrumentor 需要使用正确的 tracer_provider
# 当使用 register() 注册后，全局的 TracerProvider 会被设置，但 LangChainInstrumentor 
# 最好还是显式传入我们刚刚配置好的那个
from openinference.instrumentation.langchain import LangChainInstrumentor
LangChainInstrumentor().instrument(tracer_provider=tracer_provider)

app = FastAPI(title="智能营销助手 API (Redis Stream版)", version="1.0.0")

# 挂载静态文件目录，用于访问生成的图表
# 访问路径: http://localhost:8000/static/charts/xxx.png
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------------
# 配置
# -------------------------------------------------------------------------
REDIS_URL = "redis://localhost:6379"
STREAM_KEY_PREFIX = "chat:stream:"  # Redis Stream Key 前缀: chat:stream:{request_id}

# -------------------------------------------------------------------------
# Agent 构建
# -------------------------------------------------------------------------
def create_persistent_agent(checkpointer):
    """创建带持久化能力的 Agent Graph"""
    graph = StateGraph(AgentState)
    graph.add_node("route", _node_route)
    graph.add_node("chat", _node_chat)
    graph.add_node("analysis", _node_analysis)
    graph.add_edge(START, "route")

    def _choose(state: AgentState) -> str:
        return state.get("intent", "chat")

    graph.add_conditional_edges("route", _choose, {"chat": "chat", "analysis": "analysis"})
    graph.add_edge("chat", END)
    graph.add_edge("analysis", END)
    
    return graph.compile(checkpointer=checkpointer)

async def run_agent_and_push_to_redis(query: str, thread_id: str, request_id: str):
    redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    stream_key = f"{STREAM_KEY_PREFIX}{request_id}"
    
    # 保存 request_id -> thread_id 的映射，方便后续只通过 request_id 恢复会话
    await redis_client.set(f"req_meta:{request_id}:thread_id", thread_id, ex=3600) # 1小时过期

    try:
        # ⚠️ 注意: AsyncPostgresSaver 需要一个 async connection pool
        # 这里为了简化演示，我们在函数内创建连接池。生产环境建议全局维护连接池。
        from psycopg_pool import AsyncConnectionPool
        
        async with AsyncConnectionPool(conninfo=DATABASE_URL, kwargs={"autocommit": True}) as pool:
            checkpointer = AsyncPostgresSaver(pool)
            # 首次运行时需要建表（如果表不存在）
            # ⚠️ 注意: setup() 可能会尝试创建索引，PostgreSQL 不允许在事务块中并行创建索引
            # 但 AsyncPostgresSaver 的 setup 内部会处理这个问题，或者我们需要确保 conn 是 autocommit 模式
            await checkpointer.setup()
            
            agent = create_persistent_agent(checkpointer)
            config = {"configurable": {"thread_id": thread_id}}
            input_msg = {"messages": [HumanMessage(content=query)]}

            # Buffer for token merging
            token_buffer = []

            async for event in agent.astream_events(input_msg, config=config, version="v1"):
                event_kind = event["event"]
                event_name = event.get("name", "")
                tags = event.get("tags", [])
                
                # 构造消息 payload
                payload = {}
                
                # 1. 意图
                if event_kind == "on_chain_end" and event_name == "route":
                    output = event["data"].get("output", {})
                    if output and "intent" in output:
                        payload = {"type": "intent", "content": output["intent"]}

                # 2. 工具开始
                elif event_kind == "on_tool_start":
                    if event_name not in ["write_todos", "task", "unknown"]:
                        payload = {
                            "type": "tool_start",
                            "tool": event_name,
                            "args": json.dumps(event['data'].get('input'), ensure_ascii=False)
                        }

                # 3. 工具结束
                elif event_kind == "on_tool_end":
                    if event_name not in ["write_todos", "task", "unknown"]:
                        output_str = str(event['data'].get('output'))[:200] + "..."
                        payload = {
                            "type": "tool_end",
                            "tool": event_name,
                            "output": output_str
                        }

                # 4. LLM 流式 Token (仅当 tags 包含 'final_answer' 时推送)
                elif event_kind == "on_chat_model_stream":
                    if "final_answer" in tags:
                        content = event["data"]["chunk"].content
                        if content:
                            token_buffer.append(content)
                            # 简单的缓冲逻辑：积攒够 5 个字符，或者遇到标点，就发送
                            combined = "".join(token_buffer)
                            if len(combined) >= 5 or any(p in content for p in "，。！？,.!?\n"):
                                payload = {"type": "answer_chunk", "content": combined}
                                token_buffer = []

                # 如果有有效 payload，写入 Redis Stream
                if payload:
                    await redis_client.xadd(stream_key, payload)
            
            # 循环结束后，如果有剩余 buffer，一次性发完
            if token_buffer:
                await redis_client.xadd(stream_key, {"type": "answer_chunk", "content": "".join(token_buffer)})


        # 任务结束标记
        await redis_client.xadd(stream_key, {"type": "done", "content": "end"})
        # 设置过期时间，避免 Redis 堆积
        await redis_client.expire(stream_key, 600)  # 10分钟后过期

    except Exception as e:
        print(f"Error in background task: {e}")
        await redis_client.xadd(stream_key, {"type": "error", "content": str(e)})
    finally:
        await redis_client.aclose()


# -------------------------------------------------------------------------
# API 接口
# -------------------------------------------------------------------------
@app.get("/chat/stream")
async def chat_stream_get(query: str = None, thread_id: str = None, request_id: str = None, last_event_id: str = "0-0"):
    """
    流式对话接口 (GET 版，方便浏览器测试)
    - 接收: query (可选), thread_id (可选), request_id (可选), last_event_id (可选)
    - 返回: SSE 流
    """
    redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)

    # 1. 尝试通过 request_id 恢复 thread_id
    # 如果客户端只传了 request_id，我们尝试从 Redis 中获取对应的 thread_id (如果之前存储过)
    # 或者我们可以在 Redis 中单独存一个映射关系：request_id -> thread_id
    # 但目前我们没有显式存这个映射。
    # 变通方案：在 Redis Stream 的 meta 信息里，或者 key 的命名里？
    # 目前 Stream Key 是 chat:stream:{request_id}
    # 我们可以约定，Stream 的第一条消息或者由单独的 string key 存储 metadata。
    
    # 为了简化，我们假设：如果是断点重传（有 request_id），我们先检查 Stream 是否存在。
    # 如果存在，我们不需要 query。
    
    if request_id:
        stream_key = f"{STREAM_KEY_PREFIX}{request_id}"
        exists = await redis_client.exists(stream_key)
        
        if exists:
            # 如果流存在，说明任务还在进行或者数据还在。
            # 我们需要获取 thread_id 吗？
            # 对于 SSE 客户端来说，thread_id 主要是为了下一次对话。
            # 如果这次对话还在继续，我们可以从 meta 信息里拿到 thread_id（如果我们存了的话）。
            # 在 run_agent_and_push_to_redis 中，并没有显式存 thread_id 到 Stream。
            # 改进：我们可以在 Stream 的第一条消息（meta）里放入 thread_id。
            # 或者，我们可以要求客户端必须传 thread_id。
            
            # 用户现在的需求是：只传 request_id，自动补齐 thread_id。
            # 这意味着我们需要持久化 request_id -> thread_id 的关系。
            # 让我们在 run_agent_and_push_to_redis 里加一个 Set 操作。
            stored_thread_id = await redis_client.get(f"req_meta:{request_id}:thread_id")
            if stored_thread_id:
                thread_id = stored_thread_id
            
            # 如果没有找到 thread_id，且客户端也没传，那也没办法，只能用 default
            if not thread_id:
                thread_id = "default_thread" # Fallback
        else:
             # 如果 Stream 不存在（过期了）
             if not query:
                 # 这种情况下，没法恢复了。
                 raise HTTPException(status_code=400, detail="Session expired. Please start a new conversation.")
             
             # 如果有 query，说明是新开对话（或者重启），需要 thread_id
             if not thread_id:
                 thread_id = "default_thread"
             # 重启任务
             asyncio.create_task(run_agent_and_push_to_redis(query, thread_id, request_id))

    else:
        # 没有 request_id，说明是全新请求
        if not query:
            raise HTTPException(status_code=400, detail="Query is required for new request")
        
        request_id = str(uuid.uuid4())
        if not thread_id:
            thread_id = "default_thread"
        
        asyncio.create_task(run_agent_and_push_to_redis(query, thread_id, request_id))

    # 再次确认 stream_key
    stream_key = f"{STREAM_KEY_PREFIX}{request_id}"
    
    # 定义 SSE 生成器 (Consumer)
    async def event_generator() -> AsyncGenerator[dict, None]:
        # 需要重新连接 Redis (因为外面的 redis_client 可能需要关闭，或者为了并发安全)
        # 最好在 generator 内部管理连接
        local_redis = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
        current_id = last_event_id
        
        # 第一次连接时，先发一个 meta 事件
        yield {"event": "meta", "data": json.dumps({"request_id": request_id, "thread_id": thread_id})}
        
        try:
            while True:
                streams = await local_redis.xread({stream_key: current_id}, count=1, block=5000)
                
                if not streams:
                    # 检查 Stream 是否还存在（可能过期被删了）
                    # 或者任务是否已经完成但被清理了
                    continue
                    
                for _, messages in streams:
                    for msg_id, msg_data in messages:
                        current_id = msg_id
                        msg_type = msg_data.get("type")
                        
                        if msg_type == "done":
                            return
                        if msg_type == "error":
                            yield {"event": "error", "data": msg_data.get("content")}
                            return

                        yield {"event": "message", "id": msg_id, "data": json.dumps(msg_data, ensure_ascii=False)}
        finally:
            await local_redis.aclose()
            
    # 关闭外层的 client
    await redis_client.aclose()

    return EventSourceResponse(event_generator())

if __name__ == "__main__":
    import uvicorn
    print("🚀 启动 Redis Stream 版 API 服务...")
    print(f"🔗 Redis URL: {REDIS_URL}")
    uvicorn.run(app, host="0.0.0.0", port=8000)

import asyncio
import json
import os
import uuid
import redis.asyncio as redis
from typing import AsyncGenerator

from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from sse_starlette.sse import EventSourceResponse

# 复用已有的 Agent 逻辑
from app.agents.memory_agent import AgentState, _node_route, _node_chat, _node_knowledge, _node_analysis

_ = load_dotenv(find_dotenv())

app = FastAPI(title="智能营销助手 API (Redis Stream版)", version="1.0.0")

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
DB_PATH = "checkpoints.sqlite"
STREAM_KEY_PREFIX = "chat:stream:"  # Redis Stream Key 前缀: chat:stream:{request_id}

# -------------------------------------------------------------------------
# Agent 构建
# -------------------------------------------------------------------------
def create_persistent_agent(checkpointer):
    """创建带持久化能力的 Agent Graph"""
    graph = StateGraph(AgentState)
    graph.add_node("route", _node_route)
    graph.add_node("chat", _node_chat)
    graph.add_node("knowledge", _node_knowledge)
    graph.add_node("analysis", _node_analysis)
    graph.add_edge(START, "route")

    def _choose(state: AgentState) -> str:
        return state.get("intent", "chat")

    graph.add_conditional_edges("route", _choose, {"chat": "chat", "knowledge": "knowledge", "analysis": "analysis"})
    graph.add_edge("chat", END)
    graph.add_edge("knowledge", END)
    graph.add_edge("analysis", END)
    
    return graph.compile(checkpointer=checkpointer)

# -------------------------------------------------------------------------
# 后台任务：执行 Agent 并写入 Redis Stream
# -------------------------------------------------------------------------
async def run_agent_and_push_to_redis(query: str, thread_id: str, request_id: str):
    redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    stream_key = f"{STREAM_KEY_PREFIX}{request_id}"
    
    try:
        # 使用异步 AsyncSqliteSaver
        async with AsyncSqliteSaver.from_conn_string(DB_PATH) as checkpointer:
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
        await redis_client.close()


# -------------------------------------------------------------------------
# API 接口
# -------------------------------------------------------------------------
@app.get("/chat/stream")
async def chat_stream_get(query: str, thread_id: str = "default_thread"):
    """
    流式对话接口 (GET 版，方便浏览器测试)
    - 接收: query, thread_id (query params)
    - 返回: SSE 流
    """
    request_id = str(uuid.uuid4())
    stream_key = f"{STREAM_KEY_PREFIX}{request_id}"
    
    # 启动后台任务 (Producer)
    asyncio.create_task(run_agent_and_push_to_redis(query, thread_id, request_id))

    # 定义 SSE 生成器 (Consumer)
    async def event_generator() -> AsyncGenerator[dict, None]:
        redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
        last_id = "0-0"
        
        try:
            while True:
                streams = await redis_client.xread({stream_key: last_id}, count=1, block=5000)
                
                if not streams:
                    continue
                    
                for _, messages in streams:
                    for msg_id, msg_data in messages:
                        last_id = msg_id
                        msg_type = msg_data.get("type")
                        
                        if msg_type == "done":
                            return
                        if msg_type == "error":
                            yield {"event": "error", "data": msg_data.get("content")}
                            return

                        yield {"event": "message", "data": json.dumps(msg_data, ensure_ascii=False)}
        finally:
            await redis_client.close()

    return EventSourceResponse(event_generator())

if __name__ == "__main__":
    import uvicorn
    print("🚀 启动 Redis Stream 版 API 服务...")
    print(f"🔗 Redis URL: {REDIS_URL}")
    uvicorn.run(app, host="0.0.0.0", port=8000)

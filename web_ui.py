import gradio as gr
import json
import uuid
import asyncio
import httpx
import re
import os
from typing import AsyncGenerator

# -------------------------------------------------------------------------
# 配置
# -------------------------------------------------------------------------
# 后端 API 地址 (server_redis.py)
API_BASE_URL = "http://localhost:8000"
STATIC_BASE_URL = f"{API_BASE_URL}/static"

# -------------------------------------------------------------------------
# 客户端逻辑 (State Management)
# -------------------------------------------------------------------------
def get_or_create_thread_id(request: gr.Request) -> str:
    """
    获取当前用户的会话 ID。
    Gradio 的 request 对象包含客户端信息。
    """
    # 简单的做法：利用 Gradio 的 session_hash 作为 thread_id
    if request and hasattr(request, "session_hash"):
        return f"gradio_{request.session_hash}"
    return f"gradio_{uuid.uuid4().hex[:8]}"

def generate_request_id() -> str:
    return str(uuid.uuid4())

async def stream_chat_from_api(query: str, thread_id: str, request_id: str):
    """
    连接 SSE 接口，获取流式回复
    """
    url = f"{API_BASE_URL}/chat/stream"
    params = {
        "query": query,
        "thread_id": thread_id,
        "request_id": request_id
    }
    
    async with httpx.AsyncClient(timeout=None) as client:
        try:
            async with client.stream("GET", url, params=params) as response:
                if response.status_code != 200:
                    yield {"type": "error", "content": f"API Error: {response.status_code}"}
                    return

                current_event = None
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    
                    if line.startswith("event: "):
                        current_event = line[7:].strip()
                    elif line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)
                            if current_event == "meta":
                                yield {"type": "meta", "content": data}
                            elif current_event == "error":
                                yield {"type": "error", "content": data}
                            else:
                                # 普通消息，data 应该已经是 dict 且包含 type
                                yield data
                        except json.JSONDecodeError:
                            pass
                        # Reset event after data (assuming standard SSE structure)
                        current_event = None

        except Exception as e:
            yield {"type": "error", "content": f"Connection Error: {str(e)}"}

# -------------------------------------------------------------------------
# Gradio 处理函数
# -------------------------------------------------------------------------
async def chat_handler(message: str, history: list, thread_id_in: str, request_id_in: str):
    """
    Gradio 聊天处理函数 (Generator)
    """
    if not message.strip() and not request_id_in:
        # 如果既没有消息也没有 request_id (用于重连)，则不处理
        return
        
    # 1. 确定 Thread ID
    # 如果用户输入了 Thread ID，优先使用；否则生成新的
    thread_id = thread_id_in.strip() if thread_id_in else f"gradio_{uuid.uuid4().hex[:8]}"
    
    # 2. 确定 Request ID
    # 如果用户输入了 Request ID，说明是想重连某个流；否则设为 None (让后端生成)
    request_id = request_id_in.strip() if request_id_in else None
    
    # 3. 更新 UI (User Message)
    # 如果是新消息，添加到历史
    if message.strip():
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": ""})
    elif request_id:
        # 仅有 request_id 的情况（断点重传）
        # 如果 history 为空（例如刷新页面后），或者最后一条不是 assistant，我们需要添加一个 assistant 气泡来显示结果
        if not history or history[-1]["role"] != "assistant":
             history.append({"role": "assistant", "content": ""})
    
    # 初始 yield：更新 ID 显示，清空输入框
    yield history, "", thread_id, request_id or "", ""
    
    # 4. 流式调用 API
    full_response = ""
    # 如果是重连 (有 request_id 无 message)，需要获取之前的历史记录可能比较麻烦
    # 这里主要处理：新消息 or 带着 request_id 重连流
    
    # 注意：如果 history 不为空，上次的回答可能已经显示了一部分。
    # 为了简单，我们这里假设是新的一轮，或者追加到最后一条。
    if not history: 
        history = [] # Should not happen if message is there

    async for event in stream_chat_from_api(message, thread_id, request_id):
        event_type = event.get("type")
        content = event.get("content", "")
        
        # 0. Meta 信息 (后端返回的确认 ID)
        if event_type == "meta":
            meta_data = event.get("content", {}) # 这里 content 其实是 dict
            # 更新确认后的 ID
            if "thread_id" in meta_data:
                thread_id = meta_data["thread_id"]
            if "request_id" in meta_data:
                request_id = meta_data["request_id"]
            yield history, "", thread_id, request_id, ""

        # A. 意图识别
        elif event_type == "intent":
            intent = content
            yield history, "", thread_id, request_id, intent
            
        # B. 工具调用 (显示思考过程)
        elif event_type == "tool_start":
            tool_name = event.get("tool")
            args = event.get("args")
            full_response += f"\n> 🛠️ **正在调用工具**: `{tool_name}`\n"
            history[-1]["content"] = full_response
            yield history, "", thread_id, request_id, ""
            
        elif event_type == "tool_end":
            tool_name = event.get("tool")
            output = event.get("output", "")
            # 替换本地文件路径为 URL (如果是图表)
            if "static/charts" in output:
                # 假设 output 是 JSON 或包含路径的字符串，做个简单替换
                # 这里简单处理：如果 output 包含 chart_xxx.png，替换为 markdown 图片
                match = re.search(r'(static/charts/chart_\w+\.png)', output)
                if match:
                    rel_path = match.group(1)
                    img_url = f"{API_BASE_URL}/{rel_path}"
                    full_response += f"\n![Chart]({img_url})\n"
                else:
                    full_response += f"> ✅ `{tool_name}` 完成。\n"
            else:
                full_response += f"> ✅ `{tool_name}` 完成。\n"
                
            history[-1]["content"] = full_response
            yield history, "", thread_id, request_id, ""

        # C. LLM 回答 (打字机效果)
        elif event_type == "answer_chunk":
            full_response += content
            history[-1]["content"] = full_response
            yield history, "", thread_id, request_id, ""
            
        # D. 错误处理
        elif event_type == "error":
            full_response += f"\n❌ **Error**: {content}"
            history[-1]["content"] = full_response
            yield history, "", thread_id, request_id, ""

# -------------------------------------------------------------------------
# UI 构建
# -------------------------------------------------------------------------
with gr.Blocks(title="🍓 智能营销助手") as demo:
    # 状态变量 (移除 state，直接用 UI 组件值)
    
    gr.Markdown("# 🍓 智能营销助手")
    gr.Markdown(
        "基于 **Phoenix + LangGraph + Redis Stream** 的全功能演示。\n"
        "- **持久化**: 刷新页面不丢失历史和特点对话 (需配合 Thread ID和Request ID)\n"
        "- **流式输出**: 实时打字机效果\n"
        "- **可视化**: 自动渲染生成的图表"
    )
    
    with gr.Row():
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(
                height=600, 
                show_label=False,
                avatar_images=(None, "https://api.dicebear.com/7.x/bottts/svg?seed=marketing")
            )
        with gr.Column(scale=1):
            with gr.Accordion("🛠️ 调试参数 (可用于断点重传)", open=True):
                gr.Markdown("### 会话控制")
                thread_id_input = gr.Textbox(
                    label="Thread ID (会话ID)", 
                    placeholder="输入 ID 以恢复历史会话...",
                    value=lambda: f"gradio_{uuid.uuid4().hex[:8]}"
                )
                request_id_input = gr.Textbox(
                    label="Request ID (请求ID)", 
                    placeholder="输入 ID 以恢复特定对话..."
                )
                intent_display = gr.Textbox(
                    label="Detected Intent (当前意图)", 
                    interactive=False
                )
                gr.Markdown("""
                - **Thread ID**: 标识某一轮完整的对话历史。输入旧的id（可以自己给定）可以恢复之前的上下文记忆。
                - **Request ID**: 标识某一次具体的提问请求。输入旧的id可以自动映射到那一轮的历史对话，并恢复那一次对话，用于断点续传。
                - **Intent**: 识别到的当前用户意图。
                """)

    with gr.Row():
        with gr.Column(scale=8):
            msg = gr.Textbox(
                placeholder="输入你的问题", 
                show_label=False, 
                container=False,
                autofocus=True
            )
        with gr.Column(scale=1):
            submit_btn = gr.Button("🚀 发送", variant="primary")
            
    # 事件绑定
    # inputs: [msg, history, thread_id, request_id]
    # outputs: [chatbot, msg, thread_id, request_id, intent]
    
    msg.submit(
        fn=chat_handler,
        inputs=[msg, chatbot, thread_id_input, request_id_input],
        outputs=[chatbot, msg, thread_id_input, request_id_input, intent_display]
    )
    
    submit_btn.click(
        fn=chat_handler,
        inputs=[msg, chatbot, thread_id_input, request_id_input],
        outputs=[chatbot, msg, thread_id_input, request_id_input, intent_display]
    )


if __name__ == "__main__":
    print("🚀 启动 Gradio 前端...")
    print(f"🔗 后端 API 地址: {API_BASE_URL}")
    
    # 自动清理 7860 端口
    try:
        import subprocess
        # 查找占用 7860 端口的进程
        cmd = "lsof -t -i:7860"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        pids = result.stdout.strip().split('\n')
        for pid in pids:
            if pid:
                print(f"🧹 Killing process {pid} on port 7860...")
                subprocess.run(f"kill -9 {pid}", shell=True)
    except Exception as e:
        print(f"⚠️ Failed to clean port 7860: {e}")

    # 启动 Gradio
    demo.queue().launch(server_name="0.0.0.0", server_port=7860, theme=gr.themes.Soft())

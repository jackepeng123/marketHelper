import gradio as gr
import os
import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.agents.memory_agent import create_memory_router_agent
from langchain_core.messages import HumanMessage
from dotenv import find_dotenv, load_dotenv

_ = load_dotenv(find_dotenv())

# 1. 创建 Agent
agent = create_memory_router_agent()

# 2. 定义核心处理逻辑
async def process_chat(user_message, file_obj, history):
    """
    处理用户输入并生成回复
    """
    if not user_message and not file_obj:
        return history, ""

    # 构造 Prompt
    final_input = user_message
    
    # 如果有文件，获取路径
    if file_obj:
        # file_obj 在 Gradio 新版中可能是 str (路径) 或 NamedString
        file_path = file_obj.name if hasattr(file_obj, "name") else str(file_obj)
        final_input = f"{user_message}\n[System Note: User uploaded a file at {file_path}. If the user asks for analysis, use the 'analyze_sales_file' tool to read it.]"

    # 更新历史记录 (User msg)
    display_msg = user_message
    if file_obj:
        display_msg += f"\n[已上传文件: {os.path.basename(file_path)}]"
    
    history = history + [[display_msg, None]] # 先占位

    # 调用 Agent
    thread_id = "gradio_demo_user"
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        # 调用 LangGraph
        state = await agent.ainvoke({"messages": [HumanMessage(content=final_input)]}, config=config)
        
        # 获取回复
        if state and "messages" in state and len(state["messages"]) > 0:
            last_msg = state["messages"][-1]
            ai_response = getattr(last_msg, "content", str(last_msg))
        else:
            ai_response = "Error: No response from agent."
            
    except Exception as e:
        ai_response = f"System Error: {str(e)}"

    # 更新历史记录 (AI msg)
    history[-1][1] = ai_response
    return history, "" # 清空输入框

# 3. 手动构建界面 (使用 Blocks)
with gr.Blocks(title="🍓 智能营销助手", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🍓 智能营销助手")
    gr.Markdown("支持多模态交互！你可以上传 Excel 销量报表，我会帮你分析转化率、退款情况等。")
    
    chatbot = gr.Chatbot(height=500, show_label=False)
    
    with gr.Row():
        with gr.Column(scale=8):
            msg = gr.Textbox(placeholder="请输入问题...", show_label=False, container=False)
        with gr.Column(scale=1):
            # 兼容 Gradio 3.x: type="file" 而不是 "filepath"
            upload_btn = gr.File(label="上传表格", file_types=[".xlsx", ".xls", ".csv"], file_count="single", type="file")
        with gr.Column(scale=1):
            submit_btn = gr.Button("发送", variant="primary")

    # 绑定事件
    submit_btn.click(
        fn=process_chat,
        inputs=[msg, upload_btn, chatbot],
        outputs=[chatbot, msg]
    )
    
    msg.submit(
        fn=process_chat,
        inputs=[msg, upload_btn, chatbot],
        outputs=[chatbot, msg]
    )

# 4. 创建 FastAPI 并挂载
app = FastAPI()

# 挂载静态目录
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

# 挂载 Gradio
app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    print("🚀 启动服务中... 请访问 http://localhost:7860")
    uvicorn.run(app, host="0.0.0.0", port=7860)

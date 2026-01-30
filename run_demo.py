import os
import asyncio
from dotenv import find_dotenv, load_dotenv
from langchain_core.messages import HumanMessage
from app.agents.memory_agent import create_memory_router_agent

_ = load_dotenv(find_dotenv())

async def main():
    print("🌟 欢迎使用智能营销助手")
    
    # 提问用例：
    # 1、你好，我叫root
    # 2、你认识我吗
    # 3、抖音后台怎么上架商品
    # 4、我们上架商品的第二步是什么
    # 5、最近草莓蛋糕销量不太好，如果考虑天气，请你帮我分析原因并给出营销建议
    # 6、如果不考虑天气，请你总结刚刚的回答

    thread_id = input("请输入 thread_id（回车默认 demo）：").strip() or "demo"
    agent = create_memory_router_agent()

    while True:
        user_query = input("\n👤 请输入问题（输入 exit 退出）：").strip()
        if not user_query:
            continue
        if user_query.lower() in {"exit", "quit"}:
            break

        config = {"configurable": {"thread_id": thread_id}}
        state = await agent.ainvoke({"messages": [HumanMessage(content=user_query)]}, config=config)
        messages = state.get("messages", [])
        if messages:
            last = messages[-1]
            print("\n🤖", getattr(last, "content", str(last)))

if __name__ == "__main__":
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("❌ 错误: 未找到 DEEPSEEK_API_KEY 环境变量。")
    else:
        asyncio.run(main())

import asyncio
import json
from langchain_core.messages import HumanMessage, SystemMessage
from app.core.llm import get_deepseek_model
from app.agents.tools.marketing_tools import get_internal_sales_data, search_market_trends, get_weather
from app.agents.tools.context_tool import get_context_info
from app.agents.tools.knowledge_tool import search_knowledge_base

# -------------------------------------------------------------------------
# 路由与处理逻辑
# -------------------------------------------------------------------------

async def classify_intent(query: str) -> str:
    """
    判断用户意图：
    - "chat": 简单闲聊
    - "analysis": 营销分析 (DeepAgent)
    - "knowledge": 知识库问答 (How-to/操作指南)
    """
    model = get_deepseek_model(temperature=0.0)
    
    prompt = f"""
    You are an intent classifier. Analyze the user's query and return ONLY one of the following labels:
    - "chat": For casual greetings, simple questions, or requests that don't need data analysis (e.g., "Hello", "Who are you").
    - "analysis": For requests related to marketing analysis, sales data, market trends, or business advice (e.g., "Analyze sales", "Why is my product not selling").
    - "knowledge": For specific "how-to" questions, operational guides, or platform UI usage questions (e.g., "How to upload on Douyin", "Where is the live button").
    
    User Query: "{query}"
    
    Return ONLY the label.
    """
    
    response = await model.ainvoke([HumanMessage(content=prompt)])
    intent = response.content.strip().lower().replace('"', '')
    return intent

async def handle_simple_chat(query: str):
    print("🤖 正在进行简单对话...")
    model = get_deepseek_model(temperature=0.7)
    async for chunk in model.astream([HumanMessage(content=query)]):
        if chunk.content:
            print(chunk.content, end="", flush=True)
    print("\n")

async def handle_knowledge_query(query: str):
    print("📚 正在检索知识库...")
    
    # 1. 检索 (调用新工具)
    result = search_knowledge_base.invoke({"query": query})
    context = ""
    if result.get("status") == "success":
        for item in result.get("results", []):
            context += f"Source: {item['source']}\nContent: {item['content']}\n\n"
    else:
        context = "未找到相关操作指南，请尝试访问官方帮助中心。"
        
    print(f"✅ 检索到相关知识:\n{context}\n")
    
    # 2. 生成回答
    print("🤖 正在生成回答...")
    model = get_deepseek_model(temperature=0.1)
    prompt = f"""
    基于以下参考信息回答用户的问题。如果参考信息不足，请诚实告知。
    
    参考信息:
    {context}
    
    用户问题: {query}
    """
    
    async for chunk in model.astream([HumanMessage(content=prompt)]):
        if chunk.content:
            print(chunk.content, end="", flush=True)
    print("\n")

async def _plan_marketing_tools(query: str) -> list[dict]:
    model = get_deepseek_model(temperature=0.0)
    system = """
你是一个工具选择器。根据用户问题，从下列工具中选择需要调用的工具，并为每个工具给出参数。
要求：
1) 只输出严格 JSON，不要输出任何其它文字。
2) tools 是数组，每个元素包含 name 和 args。
3) 每个工具最多调用一次；不要为了“更全面”重复调用同一个工具。
4) 如果用户明确排除某因素（例如“不谈天气/不考虑天气”），不要选择对应工具。
可用工具：
- get_internal_sales_data: 内部销量与库存（args: product_name, days）
- search_market_trends: 外部趋势与竞品（args: keyword, platform）
- get_weather: 天气信息（args: city）
JSON 格式示例：
{"tools":[{"name":"get_internal_sales_data","args":{"product_name":"草莓蛋糕","days":7}},{"name":"search_market_trends","args":{"keyword":"草莓蛋糕","platform":"all"}}]}
"""
    user = f"用户问题：{query}"
    resp = await model.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
    text = (resp.content or "").strip()
    try:
        start = text.find("{")
        end = text.rfind("}")
        payload = json.loads(text[start : end + 1])
        tools = payload.get("tools", [])
        if isinstance(tools, list):
            normalized: list[dict] = []
            seen: set[str] = set()
            allowed = {"get_internal_sales_data", "search_market_trends", "get_weather"}
            for item in tools:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                args = item.get("args") or {}
                if name in allowed and name not in seen and isinstance(args, dict):
                    normalized.append({"name": name, "args": args})
                    seen.add(name)
            if normalized:
                return normalized
    except Exception:
        pass

    exclude_weather = any(k in query for k in ["不谈天气", "不考虑天气", "不含天气", "排除天气"])
    planned = [
        {"name": "get_internal_sales_data", "args": {"product_name": "草莓蛋糕"}},
        {"name": "search_market_trends", "args": {"keyword": "草莓蛋糕", "platform": "all"}},
    ]
    if not exclude_weather:
        planned.append({"name": "get_weather", "args": {}})
    return planned

async def handle_marketing_analysis(query: str):
    print("🚀 正在初始化营销分析流程...")

    plan = await _plan_marketing_tools(query)
    tool_map = {
        "get_internal_sales_data": get_internal_sales_data,
        "search_market_trends": search_market_trends,
        "get_weather": get_weather,
    }

    print(f"🛠️  [执行计划]: 将调用工具 -> {', '.join([p['name'] for p in plan])}")

    async def _run_one(call: dict):
        name = call["name"]
        args = call.get("args") or {}
        print(f"\n🛠️  [执行工具]: {name} -> 参数: {args}")
        tool = tool_map[name]
        out = await tool.ainvoke(args)
        print(f"✅ [工具返回]: {name} -> 结果: {str(out)[:200]}...")
        return {"tool": name, "output": out}

    results = await asyncio.gather(*[_run_one(c) for c in plan], return_exceptions=True)
    normalized_results = []
    for r in results:
        if isinstance(r, Exception):
            normalized_results.append({"tool": "unknown", "output": {"error": str(r)}})
        else:
            normalized_results.append(r)

    model = get_deepseek_model(temperature=0.1)
    system = """
你是一名资深的零售营销专家。你将收到用户问题与工具返回的数据。
要求：
1) 只输出最终报告，不要输出思考过程，不要自问自答，不要反问用户。
2) 不要调用任何工具。
3) 输出为纯文本，不要使用 Markdown 标记（例如 ##、**、- 等）。
"""
    user = "用户问题：\n" + query + "\n\n工具返回数据（JSON）：\n" + json.dumps(normalized_results, ensure_ascii=False)
    async for chunk in model.astream([SystemMessage(content=system), HumanMessage(content=user)]):
        if chunk.content:
            print(chunk.content, end="", flush=True)
    print("\n")

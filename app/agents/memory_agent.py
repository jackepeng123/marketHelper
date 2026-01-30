import asyncio
import json
from typing import Annotated, Any
from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.core.llm import get_deepseek_model
from app.agents.tools.marketing_tools import get_internal_sales_data, get_weather, search_market_trends


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    intent: str


MOCK_KNOWLEDGE_BASE: dict[str, dict[str, str]] = {
    "抖音": {
        "ui": "抖音的UI界面主要包括首页（推荐/关注）、朋友、消息、我四个底部Tab。中间的'+'号用于发布视频。",
        "上架": "在抖音后台上架商品，请进入【抖店后台】->【商品管理】->【新建商品】，填写标题、价格、库存并上传图片后提交审核。",
        "直播": "开启直播需要实名认证。点击底部'+'号，选择右下角的【开直播】，设置封面和标题后即可开始。",
    },
    "小红书": {
        "笔记": "发布笔记请点击底部'+'号，选择【图片】或【视频】，编辑滤镜和贴纸，添加正文和话题标签后发布。",
        "薯条": "薯条是小红书的内容推广工具，可以在笔记右上角菜单中找到【薯条推广】入口。",
    },
}


def _last_user_text(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content or ""
    return ""

def _recent_messages(messages: list[BaseMessage], keep_last: int = 12) -> list[BaseMessage]:
    if keep_last <= 0:
        return []
    if len(messages) <= keep_last:
        return messages
    return messages[-keep_last:]

def _infer_platform_from_history(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            text = msg.content or ""
            for platform in MOCK_KNOWLEDGE_BASE.keys():
                if platform in text:
                    return platform
    return ""

def _infer_product_from_history(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        text = getattr(msg, "content", "") or ""
        if "草莓蛋糕" in text:
            return "草莓蛋糕"
    return ""


async def _search_mock_knowledge(query: str, messages: list[BaseMessage] | None = None) -> str:
    results: list[str] = []
    for platform, data in MOCK_KNOWLEDGE_BASE.items():
        if platform in query:
            for key, content in data.items():
                if key in query or platform in query:
                    results.append(f"[{platform}-{key}]: {content}")
    if not results:
        platform = _infer_platform_from_history(messages or [])
        if platform:
            return await _search_mock_knowledge(f"{platform}{query}", None)
        return "未找到相关操作指南，请尝试访问官方帮助中心。"
    return "\n".join(results)


async def _classify_intent_text(query: str) -> str:
    model = get_deepseek_model(temperature=0.0)
    prompt = f"""
You are an intent classifier. Analyze the user's query and return ONLY one of the following labels:
- \"chat\": For casual greetings, simple questions, or requests that don't need data analysis.
- \"analysis\": For requests related to marketing analysis, sales data, market trends, or business advice.
- \"knowledge\": For specific how-to questions, operational guides, or platform UI usage questions.

User Query: \"{query}\"

Return ONLY the label.
"""
    resp = await model.ainvoke([HumanMessage(content=prompt)])
    return (resp.content or "").strip().lower().replace('"', "")


def _log(msg: str):
    print(msg, flush=True)

async def _plan_marketing_tools(query: str) -> list[dict[str, Any]]:
    _log("🛠️  [执行计划]: 正在进行 -> 规划工具调用并并行获取数据")
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
            normalized: list[dict[str, Any]] = []
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
                planned = normalized
                tools_str = ", ".join(t.get("name", "unknown") for t in planned)
                _log(f"🛠️  [执行计划]: 将调用工具 -> {tools_str}")
                return planned
    except Exception:
        pass

    exclude_weather = any(k in query for k in ["不谈天气", "不考虑天气", "不含天气", "排除天气"])
    planned: list[dict[str, Any]] = [
        {"name": "get_internal_sales_data", "args": {"product_name": "草莓蛋糕"}},
        {"name": "search_market_trends", "args": {"keyword": "草莓蛋糕", "platform": "all"}},
    ]
    if not exclude_weather:
        planned.append({"name": "get_weather", "args": {}})
    tools_str = ", ".join(t.get("name", "unknown") for t in planned)
    _log(f"🛠️  [执行计划]: 将调用工具 -> {tools_str}")
    return planned


async def _node_route(state: AgentState) -> dict[str, Any]:
    query = _last_user_text(state["messages"])
    intent = await _classify_intent_text(query)
    if intent not in {"chat", "knowledge", "analysis"}:
        intent = "chat"
    _log(f"\n🔍 意图识别结果: [{intent}]")
    return {"intent": intent}


async def _node_chat(state: AgentState) -> dict[str, Any]:
    # _log("🤖 正在进行简单对话...")  # Chat usually doesn't need detailed logs
    model = get_deepseek_model(temperature=0.7)
    resp = await model.ainvoke(_recent_messages(state["messages"]))
    return {"messages": [AIMessage(content=resp.content or "")]}


async def _node_knowledge(state: AgentState) -> dict[str, Any]:
    _log("🛠️  [执行计划]: 正在进行 -> 知识库检索与回答生成")
    query = _last_user_text(state["messages"])
    context = await _search_mock_knowledge(query, state["messages"])
    _log("✅ [检索完成]: 已获取知识片段")
    model = get_deepseek_model(temperature=0.1)
    system = "你是平台操作指南助手。结合对话历史与参考信息回答用户问题。不要编造。"
    model_messages: list[BaseMessage] = [
        SystemMessage(content=system),
        *_recent_messages(state["messages"]),
        HumanMessage(content=f"补充参考信息（用于回答上一条用户问题）：\n{context}"),
    ]
    resp = await model.ainvoke(model_messages, config={"tags": ["final_answer"]})
    return {"messages": [AIMessage(content=resp.content or "")]}


async def _node_analysis(state: AgentState) -> dict[str, Any]:
    query = _last_user_text(state["messages"])
    inferred_product = _infer_product_from_history(state["messages"])
    query_for_plan = query
    if inferred_product and inferred_product not in query_for_plan:
        query_for_plan = f"{query_for_plan}（商品：{inferred_product}）"
    
    plan = await _plan_marketing_tools(query_for_plan)
    
    # Subagent mapping display (Mocking the subagent call log for better UX)
    tool_to_subagent = {
        "get_internal_sales_data": "internal_data_analyst",
        "search_market_trends": "market_researcher",
        "get_weather": "weather_consultant"
    }
    
    for tool_call in plan:
        t_name = tool_call["name"]
        sub_name = tool_to_subagent.get(t_name, "unknown_agent")
        _log(f"🛠️  [调用子智能体]: {sub_name} -> 任务: 执行 {t_name}")

    tool_map = {
        "get_internal_sales_data": get_internal_sales_data,
        "search_market_trends": search_market_trends,
        "get_weather": get_weather,
    }

    async def _run_one(call: dict[str, Any]) -> dict[str, Any]:
        name = call["name"]
        args = call.get("args") or {}
        _log(f"🛠️  [执行工具]: {name} -> 参数: {args}")
        out = await tool_map[name].ainvoke(args)
        return {"tool": name, "output": out}

    results = await asyncio.gather(*[_run_one(c) for c in plan], return_exceptions=True)
    normalized_results: list[dict[str, Any]] = []
    for r in results:
        if isinstance(r, Exception):
            normalized_results.append({"tool": "unknown", "output": {"error": str(r)}})
        else:
            t_name = r.get("tool", "unknown")
            t_out = str(r.get("output", ""))[:100] + "..."
            _log(f"✅ [工具返回]: {t_name} -> 结果: {t_out}")
            normalized_results.append(r)

    model = get_deepseek_model(temperature=0.1)
    system = """
你是一名资深的零售营销专家。你将收到用户问题与工具返回的数据。
要求：
1) 只输出最终报告，不要输出思考过程，不要自问自答，不要反问用户。
2) 不要调用任何工具。
3) 输出为纯文本，不要使用 Markdown 标记（例如 ##、**、- 等）。
"""
    tool_data = "工具返回数据（JSON）：\n" + json.dumps(normalized_results, ensure_ascii=False)
    model_messages = [
        SystemMessage(content=system),
        *_recent_messages(state["messages"]),
        HumanMessage(content=tool_data),
    ]
    resp = await model.ainvoke(model_messages, config={"tags": ["final_answer"]})
    return {"messages": [AIMessage(content=resp.content or "")]}


def create_memory_router_agent():
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
    return graph.compile(checkpointer=InMemorySaver())

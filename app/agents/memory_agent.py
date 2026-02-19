import asyncio
import json
from typing import Annotated, Any
from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.core.llm import get_deepseek_model
from app.agents.tools.context_tool import get_context_info
from app.agents.tools.manus_tool import manus_market_research
from app.agents.tools.file_tool import analyze_sales_file


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    intent: str

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



def _infer_product_from_history(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        text = getattr(msg, "content", "") or ""
        if "草莓蛋糕" in text:
            return "草莓蛋糕"
    return ""


def _infer_platform_from_history(messages: list[BaseMessage]) -> str:
    # 简化：仅保留结构，暂不依赖 MOCK 数据
    return ""


async def _search_mock_knowledge(query: str, messages: list[BaseMessage] | None = None) -> str:
    # 已废弃：直接返回空字符串
    return ""


from datetime import datetime

# ...

async def _classify_intent_text(query: str, messages: list[BaseMessage] | None = None) -> str:
    model = get_deepseek_model(temperature=0.0)
    
    # 构造历史对话上下文（仅取最后两轮，避免干扰过多）
    context = ""
    if messages:
        recent = _recent_messages(messages, keep_last=4)
        for msg in recent:
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            content = getattr(msg, "content", str(msg))
            context += f"{role}: {content}\n"
            
    prompt = f"""
You are an intent classifier. Analyze the user's query within the conversation context and return ONLY one of the following labels:
- "chat": For casual greetings, simple questions, or requests that don't need data analysis or external knowledge.
- "analysis": For requests related to marketing analysis, sales data, market trends, business advice, OR specific how-to questions/operational guides (knowledge retrieval).

Current Date: {datetime.now().strftime('%Y-%m-%d')}

Conversation Context:
{context}

User Query: "{query}"

Return ONLY the label.
"""
    resp = await model.ainvoke([HumanMessage(content=prompt)])
    return (resp.content or "").strip().lower().replace('"', "")



def _log(msg: str):
    print(msg, flush=True)

from app.agents.tools.file_tool import analyze_sales_file
from app.agents.tools.douyin_tools import get_douyin_verify_records, get_douyin_comments, get_douyin_sales_report
from app.agents.tools.knowledge_tool import search_knowledge_base

available_tools_prompt = """
可用工具：
- search_knowledge_base: 内部知识库检索（args: query）。
  * 用于回答名词解释、操作指南、平台规则等问题（如“抖音怎么上架”）。
- manus_market_research: 外部深度市场调研（args: query, depth）。
  * 用于查询市场趋势、竞品分析、行业报告等外部信息。
  * depth 可选: 'quick'。
- get_context_info: 环境上下文（天气、节假日、位置）（args: city, date, forecast_days）
- analyze_sales_file: Excel/CSV 表格文件分析（args: file_path, need_chart, chart_type）。
  * 仅在检测到用户上传了文件（提示中包含 'User uploaded a file at...'）时，或者用户明确要求分析当前上传的表格时调用此工具。
  * 不要因为历史消息里有文件就重复调用，除非用户当前意图是分析它。
  * 支持 need_chart 和 chart_type 参数。
- get_douyin_verify_records: 抖音验券历史查询（args: date）。
  * date: YYYY-MM-DD，默认为昨日。
- get_douyin_comments: 抖音商品评价查询（args: product_name）。
  * 用于查询特定商品的最新评价（最近90天）。
- get_douyin_sales_report: 抖音周期性销售报表（args: start_date, end_date, need_chart）。
  * 用于查询一段时间（如上周、上个月）的销售汇总和趋势。need_chart 默认为 True。
"""

async def _plan_marketing_tools(query: str, messages: list[BaseMessage]) -> list[dict[str, Any]]:
    _log("🛠️  [执行计划]: 正在进行 -> 规划工具调用并并行获取数据")
    model = get_deepseek_model(temperature=0.0)
    system = f"""
你是一个工具选择器。根据用户问题，从下列工具中选择需要调用的工具，并为每个工具给出参数。
Today is: {datetime.now().strftime('%Y-%m-%d')}

要求：
1) 只输出严格 JSON，不要输出任何其它文字。
2) tools 是数组，每个元素包含 name 和 args。
3) 每个工具最多调用一次。
4) 如果用户明确排除某因素，不要选择对应工具。
5) 【重要 - 避免重复调用】：
   - 在决定调用工具前，必须仔细检查 CONTEXT (对话历史)。
   - 如果用户的问题是基于历史数据进行的追问（例如“为什么这么低？”、“有什么改进建议？”），且相关数据（如销售报表、评论）已经在历史对话中给出，则 **不要** 再次调用工具。返回空数组 [] 即可。
   - 只有当用户明确要求新的时间段、新的数据、或历史记录中缺少回答当前问题所需的数据时，才调用工具。
   - 如果历史记录中已经有图表，且用户没有要求画新图，不要重复生成图表。

{available_tools_prompt}

JSON 格式示例：
{{"tools":[{{"name":"get_douyin_sales_report","args":{{"start_date":"2024-01-01", "end_date": "2024-01-07", "need_chart": true}}}},{{"name":"get_context_info","args":{{"city":"上海", "forecast_days": "15d"}}}}]}}
"""
    # ...
    input_messages = [SystemMessage(content=system)] + _recent_messages(messages)
    input_messages.append(HumanMessage(content=f"Current Plan Request: {query}"))

    resp = await model.ainvoke(input_messages)
    text = (resp.content or "").strip()
    try:
        start = text.find("{")
        end = text.rfind("}")
        payload = json.loads(text[start : end + 1])
        tools = payload.get("tools", [])
        if isinstance(tools, list):
            normalized: list[dict[str, Any]] = []
            seen: set[str] = set()
            allowed = {"manus_market_research", "get_context_info", "analyze_sales_file", "get_douyin_verify_records", "get_douyin_comments", "get_douyin_sales_report", "search_knowledge_base"}
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
        {"name": "manus_market_research", "args": {"query": "草莓蛋糕市场趋势", "depth": "general"}},
    ]
    if not exclude_weather:
        planned.append({"name": "get_context_info", "args": {}})
    tools_str = ", ".join(t.get("name", "unknown") for t in planned)
    _log(f"🛠️  [执行计划]: 将调用工具 -> {tools_str}")
    return planned


async def _node_route(state: AgentState) -> dict[str, Any]:
    query = _last_user_text(state["messages"])
    intent = await _classify_intent_text(query, state["messages"])
    
    if intent not in {"chat", "analysis"}:
        intent = "chat"
    _log(f"\n🔍 意图识别结果: [{intent}]")
    return {"intent": intent}


async def _node_chat(state: AgentState) -> dict[str, Any]:
    # ⚠️ 修复：增加 tags=["final_answer"] 使得流式输出能被捕获
    model = get_deepseek_model(temperature=0.7)
    resp = await model.ainvoke(_recent_messages(state["messages"]), config={"tags": ["final_answer"]})
    return {"messages": [AIMessage(content=resp.content or "")]}


async def _node_knowledge(state: AgentState) -> dict[str, Any]:
    # 已废弃，但为了保持 Graph 结构定义暂留空实现，或直接移除节点定义
    # 在 create_memory_router_agent 中已经移除了该节点的注册
    pass


async def _node_analysis(state: AgentState) -> dict[str, Any]:
    query = _last_user_text(state["messages"])
    inferred_product = _infer_product_from_history(state["messages"])
    query_for_plan = query
    if inferred_product and inferred_product not in query_for_plan:
        query_for_plan = f"{query_for_plan}（商品：{inferred_product}）"
    
    plan = await _plan_marketing_tools(query_for_plan, state["messages"])
    
    # Subagent mapping display (Mocking the subagent call log for better UX)
    tool_to_subagent = {
        "manus_market_research": "market_researcher",
        "get_context_info": "context_consultant",
        "analyze_sales_file": "file_data_analyst",
        "get_douyin_verify_records": "douyin_operations_specialist",
        "get_douyin_comments": "douyin_operations_specialist",
        "get_douyin_sales_report": "douyin_operations_specialist",
        "search_knowledge_base": "knowledge_librarian"
    }
    
    for tool_call in plan:
        t_name = tool_call["name"]
        sub_name = tool_to_subagent.get(t_name, "unknown_agent")
        _log(f"🛠️  [调用子智能体]: {sub_name} -> 任务: 执行 {t_name}")

    tool_map = {
        "manus_market_research": manus_market_research,
        "get_context_info": get_context_info,
        "analyze_sales_file": analyze_sales_file,
        "get_douyin_verify_records": get_douyin_verify_records,
        "get_douyin_comments": get_douyin_comments,
        "get_douyin_sales_report": get_douyin_sales_report,
        "search_knowledge_base": search_knowledge_base
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
3) 输出为纯文本，不要使用 Markdown 标记（例如 ##、**、- 等），但图表链接除外。
4) 【重要】如果工具返回了图片 URL (chart_url)，必须在报告末尾以 Markdown 图片格式 `![Chart](url)` 独立一行展示。
   - 如果本轮对话没有调用工具，或者工具没有返回新的图片，**严禁** 复制历史消息中的旧图片链接。
   - 只有当 `chart_url` 出现在下方的“工具返回数据”中时，才允许展示。
5) 仅在回答针对过去销量的归因分析类问题时，如果你发现销售数据（如 get_douyin_sales_report 返回的数据）在某些具体日期有异常波动（如暴跌或暴涨），且目前缺乏那几天的天气数据，才请在报告结尾主动建议用户：“我注意到 [日期] 的销量有异常波动，是否需要我查询那几天的历史天气以进行归因分析？”。对于未来策划类问题，不要输出此建议。
6) 请注意，系统目前仅支持查询过去 10 天内的历史天气。不要建议用户查询超过 10 天前的历史数据。
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
    graph.add_node("analysis", _node_analysis)
    graph.add_edge(START, "route")

    def _choose(state: AgentState) -> str:
        return state.get("intent", "chat")

    graph.add_conditional_edges("route", _choose, {"chat": "chat", "analysis": "analysis"})
    graph.add_edge("chat", END)
    graph.add_edge("analysis", END)
    return graph.compile(checkpointer=InMemorySaver())

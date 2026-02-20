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
from app.utils.nacos_client import get_prompt


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

from datetime import datetime

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
            
    base_prompt = get_prompt("intent_classification_prompt")
    prompt = f"""{base_prompt}

Current Date: {datetime.now().strftime('%Y-%m-%d')}

Conversation Context:
{context}

User Query: "{query}"
"""
    resp = await model.ainvoke([HumanMessage(content=prompt)])
    return (resp.content or "").strip().lower().replace('"', "")



def _log(msg: str):
    print(msg, flush=True)

from app.agents.tools.file_tool import analyze_sales_file
from app.agents.tools.douyin_tools import get_douyin_verify_records, get_douyin_comments, get_douyin_sales_report
from app.agents.tools.knowledge_tool import search_knowledge_base

# 移除硬编码的 available_tools_prompt，改为在函数内获取或动态构建
# available_tools_prompt = ... (Moved to Nacos)

async def _plan_marketing_tools(query: str, messages: list[BaseMessage]) -> list[dict[str, Any]]:
    _log("🛠️  [执行计划]: 正在进行 -> 规划工具调用并并行获取数据")
    model = get_deepseek_model(temperature=0.0)
    
    base_system = get_prompt("tool_planner_system_prompt")
    available_tools = get_prompt("available_tools_prompt")
    
    system = f"""{base_system}
Today is: {datetime.now().strftime('%Y-%m-%d')}

{available_tools}
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

    # 移除所有硬编码的 Fallback 逻辑，如果解析失败或无工具调用，则返回空列表，交给后续 LLM 处理或报错
    _log("⚠️ [执行计划]: 无法解析工具调用或没有匹配工具，返回空列表")
    return []


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
    # 移除 inferred_product 逻辑，直接使用用户 query
    plan = await _plan_marketing_tools(query, state["messages"])
    
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
    system = get_prompt("final_response_system_prompt")
    
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

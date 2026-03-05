import os
import time
import requests
import json
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class MarketResearchInput(BaseModel):
    query: str = Field(..., description="需要调研的市场问题或关键词，例如'2026年草莓蛋糕流行趋势'")
    depth: str = Field(default="general", description="调研深度：'quick'(快速/lite)")

@tool("manus_market_research", args_schema=MarketResearchInput)
def manus_market_research(query: str, depth: str = "general") -> dict:
    """
    使用 Manus AI 进行深度市场调研和网络搜索。
    当用户需要了解外部市场趋势、竞品分析、行业报告时调用此工具。
    这是一个耗时操作（可能需要1-3分钟），请耐心等待。
    """
    api_key = os.getenv("MANUS_API_KEY")
    if not api_key:
        return {"error": "MANUS_API_KEY not found in environment variables. Please set it in .env"}
    
    base_url = "https://api.manus.im/v1"
    headers = {
        "Content-Type": "application/json",
        "API_KEY": api_key, # 优先使用官方推荐的 Header
        "Authorization": f"Bearer {api_key}" # 保留兼容性
    }
    
    # 映射 profile
    profile_map = {
        "quick": "manus-1.6-lite",
        "general": "manus-1.6-lite", # 强制降级为 lite 以节省成本
    }
    agent_profile = profile_map.get(depth, "manus-1.6-lite")
    
    try:
        # 1. 创建任务 (Create Task)
        print(f"🚀 [Manus] Starting research task: {query} (Profile: {agent_profile})")
        create_url = f"{base_url}/responses"
        payload = {
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": query}
                    ]
                }
            ],
            "extra_body": {
                "task_mode": "agent",
                "agent_profile": agent_profile
            }
        }
        
        resp = requests.post(create_url, headers=headers, json=payload, timeout=30)
        
        if resp.status_code != 200:
            return {"error": f"Manus Create Failed: {resp.status_code} {resp.text}"}
            
        task_data = resp.json()
        task_id = task_data.get("id")
        if not task_id:
            return {"error": "No task ID returned from Manus"}
            
        print(f"⏳ [Manus] Task Created ID: {task_id}, Waiting for completion...")
        
        # 2. 轮询状态 (Polling)
        max_retries = 60 # 最多等待 60 * 3秒 = 3分钟
        retrieve_url = f"{base_url}/responses/{task_id}"
        
        for _ in range(max_retries):
            time.sleep(3) # 每3秒查一次
            
            poll_resp = requests.get(retrieve_url, headers=headers, timeout=10)
            if poll_resp.status_code != 200:
                print(f"⚠️ [Manus] Poll failed: {poll_resp.status_code}")
                continue
                
            poll_data = poll_resp.json()
            status = poll_data.get("status")
            
            if status == "completed":
                print("✅ [Manus] Task Completed!")
                # 3. 提取结果
                output = poll_data.get("output", [])
                full_text = ""
                
                # 增强解析逻辑
                # 有些时候 assistant 的消息可能分布在多条，或者 content 结构不同
                assistant_msgs = [m for m in output if m.get("role") == "assistant"]
                
                for msg in assistant_msgs:
                    content = msg.get("content")
                    if isinstance(content, str):
                        full_text += content + "\n"
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):
                                item_type = item.get("type")
                                if item_type == "text":
                                    full_text += item.get("text", "") + "\n"
                                elif item_type == "output_file":
                                    full_text += f"\n[File Generated: {item.get('fileName')}]({item.get('fileUrl')})\n"
                            elif isinstance(item, str):
                                full_text += item + "\n"
                
                if not full_text:
                    # 如果 output 里没找到，尝试找 output 同级的 result 字段 (有些 API 变种)
                    if "result" in poll_data:
                        full_text = str(poll_data["result"])
                    else:
                        # 打印调试信息
                        print(f"⚠️ [Manus Debug] Output structure: {json.dumps(output, ensure_ascii=False)[:500]}...")
                        full_text = f"Task completed but text parsing failed. Debug Info: Status={status}, OutputLen={len(output)}"
                    
                return {
                    "status": "success",
                    "keyword": query,
                    "report": full_text,
                    "source": "Manus AI"
                }
                
            elif status == "error":
                return {"error": f"Manus Task Failed: {poll_data}"}
                
            # 如果是 running 或 pending，继续循环
            
        return {"error": "Manus Task Timeout after 3 minutes."}

    except Exception as e:
        return {"error": f"Manus System Error: {str(e)}"}

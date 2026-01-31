import os
from langchain_openai import ChatOpenAI

# -------------------------------------------------------------------------
# DeepSeek 模型配置
# -------------------------------------------------------------------------
# 注意：DeepSeek 兼容 OpenAI SDK，因此使用 ChatOpenAI 类
# Base URL 设置为 https://api.deepseek.com

def get_deepseek_model(temperature: float = 0.0):
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    
    return ChatOpenAI(
        model="deepseek-chat", # DeepSeek V3.2
        openai_api_key=api_key,
        openai_api_base="https://api.deepseek.com",
        temperature=temperature,
        max_tokens=4096,
        streaming=True 
    )

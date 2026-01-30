import os
from langchain_openai import ChatOpenAI

# -------------------------------------------------------------------------
# DeepSeek 模型配置
# -------------------------------------------------------------------------
# 注意：DeepSeek 兼容 OpenAI SDK，因此使用 ChatOpenAI 类
# Base URL 设置为 https://api.deepseek.com
# 
# 环境变量 DEEPSEEK_API_KEY 需要在运行前设置
# export DEEPSEEK_API_KEY="sk-..."

def get_deepseek_model(temperature: float = 0.0):
    """
    获取配置好的 DeepSeek Chat 模型实例
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "sk-placeholder") # 实际运行时请确保环境变量已设置
    
    return ChatOpenAI(
        model="deepseek-chat", # DeepSeek V3 (Chat)
        openai_api_key=api_key,
        openai_api_base="https://api.deepseek.com",
        temperature=temperature,
        max_tokens=4096,
        streaming=True # 支持流式输出
    )

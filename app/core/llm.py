import os
from langchain_openai import ChatOpenAI
from langchain_community.embeddings import QianfanEmbeddingsEndpoint
from dotenv import load_dotenv, find_dotenv

# -------------------------------------------------------------------------
# 加载环境变量
# -------------------------------------------------------------------------
# ⚠️ 注意: 移除重复加载，避免并发读取 .env 导致 TimeoutError
# 仅当环境变量未加载时尝试加载
if not os.getenv("OPENAI_API_KEY"):
    _ = load_dotenv(find_dotenv())

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

from langchain_community.embeddings import QianfanEmbeddingsEndpoint
from dotenv import find_dotenv, load_dotenv

_ = load_dotenv(find_dotenv())

ak = (os.environ.get('QIANFAN_ACCESS_KEY') or '').strip()
sk = (os.environ.get('QIANFAN_SECRET_KEY') or '').strip()

def get_embeddings_model():
    """
    获取 Embedding 模型。
    使用百度千帆 Embedding-V1。
    需要环境变量: QIANFAN_ACCESS_KEY, QIANFAN_SECRET_KEY
    """
    return QianfanEmbeddingsEndpoint()

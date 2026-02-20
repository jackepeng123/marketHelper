import os
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from dotenv import load_dotenv, find_dotenv
from app.core.llm import get_embeddings_model, get_deepseek_model
from langchain_core.messages import SystemMessage, HumanMessage
from app.utils.nacos_client import get_prompt

_ = load_dotenv(find_dotenv())
DB_URL = os.getenv("DATABASE_URL")

class KnowledgeSearchInput(BaseModel):
    query: str = Field(..., description="用户的查询问题")

def _rewrite_query(query: str) -> str:
    """
    使用 LLM 对用户查询进行改写，使其更适合知识库检索。
    """
    try:
        model = get_deepseek_model(temperature=0.0)
        # 从 Nacos 获取 Prompt
        base_prompt = get_prompt("knowledge_query_rewrite_prompt")
        # 替换 Prompt 中的变量 (如果 prompt 中包含 {query} 占位符)
        if "{query}" in base_prompt:
            prompt = base_prompt.format(query=query)
        else:
            # Fallback for old prompt format just in case
            prompt = f"{base_prompt}\n\n用户原始查询: \"{query}\"\n改写后的查询:\n"
            
        resp = model.invoke([HumanMessage(content=prompt)])
        rewritten = resp.content.strip()
        print(f"🔄 Query Rewritten: '{query}' -> '{rewritten}'")
        return rewritten
    except Exception as e:
        print(f"⚠️ Query rewrite failed: {e}")
        return query

@tool("search_knowledge_base", args_schema=KnowledgeSearchInput)
def search_knowledge_base(query: str) -> dict:
    """
    检索内部知识库（PDF文档、操作指南等）。
    当用户询问关于具体操作流程、名词解释、平台规则（如抖音、小红书等）时使用。
    """
    if not DB_URL:
        return {"error": "DATABASE_URL not set"}

    # 1. Query 改写
    search_query = _rewrite_query(query)
    
    # 2. Embedding
    try:
        embeddings_model = get_embeddings_model()
        query_vector = embeddings_model.embed_query(search_query)
    except Exception as e:
        return {"error": f"Embedding generation failed: {str(e)}"}

    # 3. 数据库检索
    try:
        engine = create_engine(DB_URL)
        sql = text("""
            SELECT content, source, (embedding <=> CAST(:query_vector AS vector)) as distance
            FROM knowledge_chunks
            ORDER BY embedding <=> CAST(:query_vector AS vector) ASC
            LIMIT 3
        """)
        
        with engine.connect() as conn:
            results = conn.execute(sql, {"query_vector": query_vector}).fetchall()
            
        if not results:
            return {"status": "no_result", "message": "未找到相关知识库内容。"}
            
        chunks = []
        for row in results:
            chunks.append({
                "content": row[0],
                "source": os.path.basename(row[1]), # 只保留文件名
                "similarity": round(1 - row[2], 4)
            })
            
        return {
            "status": "success", 
            "original_query": query,
            "rewritten_query": search_query,
            "results": chunks
        }
            
    except Exception as e:
        return {"error": f"Database search failed: {str(e)}"}

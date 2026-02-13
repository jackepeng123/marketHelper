import os
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from dotenv import load_dotenv, find_dotenv
from app.core.llm import get_embeddings_model, get_deepseek_model
from langchain_core.messages import SystemMessage, HumanMessage

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
        # 参考了 RAG 教程的场景化改写提示词
        prompt = f"""
你是一个专业的搜索引擎查询优化器。请将用户的原始查询改写为更清晰、更准确、更适合向量检索的形式。

【改写策略参考】
1. 口语化表达规范化：将“这个APP咋用”改写为“APP使用指南”
2. 冗长查询精炼化：去除冗余描述，提取核心实体和意图
3. 拼写错误纠正：自动修正明显的错别字
4. 术语缩写扩展：如将“HRBP”扩展或解释为“人力资源业务合作伙伴”
5. 符号描述语义化：将“倒三角符号”改写为具体的数学术语“nabla算子”或“梯度”

【要求】
- 保持原意，不要过度发散。
- 如果包含代词（如“它”），尝试基于常识还原指代对象。
- 只输出改写后的查询语句，不要输出任何解释、分析或引号。

用户原始查询: "{query}"
改写后的查询:
"""
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

import os
import sys
# 将项目根目录添加到 sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

import json
from sqlalchemy import create_engine, text
from dotenv import load_dotenv, find_dotenv
from app.core.llm import get_embeddings_model

# 加载环境变量
_ = load_dotenv(find_dotenv())
DB_URL = os.getenv("DATABASE_URL")

def search_knowledge(query: str, top_k: int = 3):
    """
    测试检索效果工具：
    输入问题，直接查看从数据库中检索到了哪些文本片段。
    用于评估 Embedding 和切分的效果。
    """
    if not DB_URL:
        print("❌ Error: DATABASE_URL not set.")
        return

    print(f"🔍 Searching for: '{query}'")
    
    # 1. 获取 Embedding
    try:
        embeddings_model = get_embeddings_model()
        query_vector = embeddings_model.embed_query(query)
    except Exception as e:
        print(f"❌ Failed to generate embedding: {e}")
        return

    # 2. 数据库查询
    engine = create_engine(DB_URL)
    
    # ⚠️ 修复：显式转换 query_vector 为 vector 类型
    # PostgreSQL pgvector 需要明确告诉它传入的数组是 vector 类型
    
    sql = text(f"""
        SELECT content, source, (embedding <=> CAST(:query_vector AS vector)) as distance
        FROM knowledge_chunks
        ORDER BY embedding <=> CAST(:query_vector AS vector) ASC
        LIMIT :top_k
    """)
    
    print(f"💾 Querying PostgreSQL (Top {top_k})...")
    
    with engine.connect() as conn:
        results = conn.execute(sql, {
            "query_vector": query_vector, 
            "top_k": top_k
        }).fetchall()
        
        if not results:
            print("📭 No results found.")
            return

        print(f"\n✅ Found {len(results)} relevant chunks:\n" + "="*50)
        
        for i, row in enumerate(results):
            score = 1 - row[2] # 将距离转换为相似度 (0~1)
            source = row[1]
            content = row[0]
            
            print(f"\n[Rank {i+1}] Similarity: {score:.4f} | Source: {source}")
            print(f"Content Preview: {content[:100]}...") # 只打印前100字预览
            print("-" * 30)
            print(content) # 打印全文以便检查完整性
            print("="*50)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        q = sys.argv[1]
    else:
        q = input("请输入测试问题: ")
    
    search_knowledge(q)

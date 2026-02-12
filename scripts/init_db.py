import os
import sqlalchemy
from sqlalchemy import create_engine, text
from dotenv import load_dotenv, find_dotenv

_ = load_dotenv(find_dotenv())

DB_URL = os.getenv("DATABASE_URL")

def init_db():
    print(f"🔌 Connecting to database: {DB_URL}")
    engine = create_engine(DB_URL)
    
    try:
        with engine.connect() as conn:
            # 1. 启用 pgvector 扩展
            print("🔧 Enabling pgvector extension...")
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()
            
            # 2. 创建 Knowledge Chunks 表
            print("📚 Creating knowledge_chunks table...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id BIGSERIAL PRIMARY KEY,
                    content TEXT NOT NULL,
                    embedding vector(1536),
                    metadata JSONB DEFAULT '{}',
                    source VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.commit()
            
            # 3. 创建 Checkpoints 表 (LangGraph Standard Schema)
            print("💾 Creating checkpoints table (LangGraph Standard)...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    thread_id TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    parent_checkpoint_id TEXT,
                    type TEXT,
                    checkpoint BYTEA,
                    metadata BYTEA,
                    PRIMARY KEY (thread_id, checkpoint_id)
                );
                
                CREATE TABLE IF NOT EXISTS checkpoint_blobs (
                    thread_id TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    blob BYTEA,
                    PRIMARY KEY (thread_id, checkpoint_id, type)
                );
                
                CREATE TABLE IF NOT EXISTS checkpoint_writes (
                    thread_id TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    idx INTEGER NOT NULL,
                    channel TEXT NOT NULL,
                    type TEXT,
                    blob BYTEA,
                    PRIMARY KEY (thread_id, checkpoint_id, task_id, idx)
                );
            """))
            conn.commit()
            
            # 4. 创建 Products 表 (业务数据)
            print("🛍️ Creating products table...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    product_id BIGINT NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    category VARCHAR(100),
                    price DECIMAL(10, 2),
                    status INTEGER DEFAULT 1,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.commit()
            
        print("✅ Database initialization completed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Tip: Make sure PostgreSQL is running and DATABASE_URL is correct.")

if __name__ == "__main__":
    init_db()

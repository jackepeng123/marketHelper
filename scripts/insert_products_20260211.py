import os
import sys
# 将项目根目录添加到 sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

import pandas as pd
import sqlalchemy
from sqlalchemy import create_engine, text
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
from app.core.llm import get_embeddings_model

# 加载环境变量
_ = load_dotenv(find_dotenv())

# Excel 文件路径
EXCEL_PATH = os.path.join(os.path.dirname(__file__), "生意经_商品列表_20260211_2324.xlsx")

# 数据库连接
DB_URL = os.getenv("DATABASE_URL")

def import_products():
    if not os.path.exists(EXCEL_PATH):
        print(f"❌ Error: Excel file not found at {EXCEL_PATH}")
        return

    print(f"🔌 Connecting to database...")
    engine = create_engine(DB_URL)
    
    print(f"📖 Reading Excel file...")
    try:
        df = pd.read_excel(EXCEL_PATH)
    except Exception as e:
        print(f"❌ Error reading Excel: {e}")
        return

    # 初始化 Embedding 模型
    print("🧠 Initializing Embedding Model...")
    try:
        embeddings_model = get_embeddings_model()
    except Exception as e:
        print(f"❌ Failed to init embedding model: {e}")
        return

    # 准备数据
    products_to_insert = []
    
    print("🔄 Processing rows and generating embeddings...")
    for index, row in df.iterrows():
        try:
            # 1. 提取基础字段
            p_id = str(row.get('商品id', '')).strip()
            name = str(row.get('商品名称', '')).strip()
            category = str(row.get('商品三级品类名称', '')).strip()
            
            # 2. 计算价格 (核销金额 / 核销券数)
            write_off_count = float(row.get('商品核销券数', 0))
            write_off_amount = float(row.get('商品核销金额', 0))
            
            price = 0.0
            if write_off_count > 0:
                price = write_off_amount / write_off_count
            
            # 3. 计算向量 (Embedding)
            # 使用商品名称 + 分类作为语义输入，增加匹配准确度
            text_to_embed = f"{name} {category}"
            embedding_vector = embeddings_model.embed_query(text_to_embed)

            # 4. 构造插入对象
            products_to_insert.append({
                "product_id": p_id,
                "name": name,
                "category": category,
                "price": price,
                "status": 1,
                "embedding": embedding_vector, # 插入向量
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            })
            
            if (index + 1) % 10 == 0:
                print(f"   ... Processed {index + 1} products")
            
        except Exception as e:
            print(f"⚠️ Skipping row {index}: {e}")
            continue
            
    if not products_to_insert:
        print("⚠️ No valid products found to insert.")
        return

    # 执行插入
    print(f"💾 Inserting {len(products_to_insert)} products into database...")
    
    with engine.connect() as conn:
        # 1. 确保表结构匹配
        # 这里不再自动 ALTER，假设 init_db.py 已经创建了正确的表结构
        
        # 2. 插入数据
        insert_sql = text("""
            INSERT INTO products (product_id, name, category, price, status, embedding, created_at, updated_at)
            VALUES (:product_id, :name, :category, :price, :status, :embedding, :created_at, :updated_at)
        """)
        
        try:
            # 批量插入可能比较慢，特别是带向量，如果数据量大可以分批
            conn.execute(insert_sql, products_to_insert)
            conn.commit()
            print("✅ Import completed successfully!")
        except Exception as e:
            print(f"❌ Insert failed: {e}")
            conn.rollback()

if __name__ == "__main__":
    import_products()

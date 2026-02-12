import os
import pandas as pd
import sqlalchemy
from sqlalchemy import create_engine, text
from datetime import datetime
from dotenv import load_dotenv, find_dotenv

# 加载环境变量
_ = load_dotenv(find_dotenv())

# Excel 文件路径
EXCEL_PATH = "/Users/penghaofeng/Desktop/项目/营销助手/生意经_商品列表_20260211_2324.xlsx"

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

    # 准备数据
    products_to_insert = []
    
    print("🔄 Processing rows...")
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
            
            # 3. 构造插入对象
            products_to_insert.append({
                "product_id": p_id,
                "name": name,
                "category": category,
                "price": price,
                "status": 1,
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            })
            
        except Exception as e:
            print(f"⚠️ Skipping row {index}: {e}")
            continue
            
    if not products_to_insert:
        print("⚠️ No valid products found to insert.")
        return

    # 执行插入
    print(f"💾 Inserting {len(products_to_insert)} products into database...")
    
    with engine.connect() as conn:
        # 1. 确保表结构匹配 (简单的 Schema Migration)
        # 检查是否存在 product_id 和 category 列，如果没有则添加
        # 注意：这只是一个简单的容错处理
        try:
            conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS product_id VARCHAR(255);"))
            conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS category VARCHAR(255);"))
            conn.commit()
        except Exception as e:
            print(f"⚠️ Schema update warning: {e}")

        # 2. 插入数据
        # 使用 SQLAlchemy 的参数化查询防止 SQL 注入
        insert_sql = text("""
            INSERT INTO products (product_id, name, category, price, status, created_at, updated_at)
            VALUES (:product_id, :name, :category, :price, :status, :created_at, :updated_at)
        """)
        
        try:
            conn.execute(insert_sql, products_to_insert)
            conn.commit()
            print("✅ Import completed successfully!")
        except Exception as e:
            print(f"❌ Insert failed: {e}")
            conn.rollback()

if __name__ == "__main__":
    import_products()

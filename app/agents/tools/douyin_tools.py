import os
import requests
import json
import time
from datetime import datetime, timedelta
from typing import Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from dotenv import load_dotenv, find_dotenv
from app.agents.tools.chart_tool import generate_chart

# 加载环境变量
_ = load_dotenv(find_dotenv())

# 配置
CLIENT_KEY = os.getenv("CLIENT_KEY")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
ACCOUNT_ID = os.getenv("ACCOUNT_ID")
POI_ID = os.getenv("POI_ID")
DB_URL = os.getenv("DATABASE_URL")

# 数据库引擎 (用于查 product_id)
db_engine = create_engine(DB_URL) if DB_URL else None

def get_client_token():
    """
    通过 Client Credentials 模式获取 access_token (即 client_token)。
    注意：这里获取的是 client_token，虽然接口返回字段叫 access_token。
    """
    if not CLIENT_KEY or not CLIENT_SECRET:
        print("❌ Error: Missing CLIENT_KEY or CLIENT_SECRET in .env")
        return None

    url = 'https://open.douyin.com/oauth/client_token/'
    headers = {'Content-Type': 'application/json'}
    payload = {
        "grant_type": "client_credential",
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET
    }
    
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        data = resp.json()
        if data.get("message") == "success" and "data" in data:
            return data["data"].get("access_token")
        else:
            print(f"❌ Failed to get client_token: {data}")
            return None
    except Exception as e:
        print(f"❌ Request Error: {e}")
        return None

def get_headers():
    token = get_client_token()
    return {
        'content-type': 'application/json',
        'access-token': token,
    }

# -------------------------------------------------------------------------
# Tool 1: 验券历史查询
# -------------------------------------------------------------------------
class VerifyRecordInput(BaseModel):
    date: str = Field(default=None, description="查询日期，格式 YYYY-MM-DD。如果不填默认查询昨天。")

@tool("get_douyin_verify_records", args_schema=VerifyRecordInput)
def get_douyin_verify_records(date: str = None) -> dict:
    """
    查询抖音店铺的验券（核销）历史记录。
    可以查询某的一天的订单核销情况，包含核销时间、金额等信息。
    """
    if not ACCOUNT_ID:
        return {"error": "Missing ACCOUNT_ID in .env"}

    # 获取 headers (包含动态获取的 token)
    headers = get_headers()
    if not headers.get('access-token'):
        return {"error": "Failed to obtain access_token (client_token). Check CLIENT_KEY/SECRET."}

    # 处理日期 -> 时间戳
    try:
        if date:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        else:
            target_date = datetime.now() - timedelta(days=1) # 默认昨天
            
        start_dt = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = target_date.replace(hour=23, minute=59, second=59, microsecond=0)
        
        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())
    except ValueError:
        return {"error": "Invalid date format. Please use YYYY-MM-DD"}

    url = 'https://open.douyin.com/goodlife/v1/fulfilment/certificate/verify_record/query/'
    params = {
        'account_id': ACCOUNT_ID,
        'cursor': '0',
        'size': 20, # 假设一天不超过20单，或者后续加翻页逻辑
        'start_time': start_ts,
        'end_time': end_ts,
    }
    
    try:
        print(f"🚀 [Douyin] Querying verify records for {start_dt.date()}...")
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return {"error": f"API HTTP Error: {response.status_code}", "detail": response.text}
            
        data = response.json()
        
        # 数据清洗
        if data.get("data", {}).get("error_code") == 0:
            return _process_verify_data(data, start_dt.strftime("%Y-%m-%d"))
        else:
            return {"error": "Douyin API Error", "raw": data}
        
    except Exception as e:
        return {"error": f"Request Failed: {str(e)}"}
    
# -------------------------------------------------------------------------
# Tool 2: 抖音销售报表 (多天聚合 + 画图)
# -------------------------------------------------------------------------
class SalesReportInput(BaseModel):
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    need_chart: bool = Field(default=True, description="是否需要生成趋势图")

@tool("get_douyin_sales_report", args_schema=SalesReportInput)
def get_douyin_sales_report(start_date: str, end_date: str, need_chart: bool = True) -> dict:
    """
    生成抖音店铺的销售报表（周报/月报）。
    自动查询指定时间段内的每日核销数据，聚合总收入，并生成趋势图。
    """
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        days = (end_dt - start_dt).days + 1
        
        if days > 31:
            return {"error": "Date range too long. Max 31 days allowed."}
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD"}

    daily_results = []
    total_revenue = 0.0
    total_orders = 0
    product_agg = {}
    
    chart_x = []
    chart_y = []
    
    print(f"🚀 [Douyin Report] Generating report from {start_date} to {end_date} ({days} days)...")
    
    for i in range(days):
        current_dt = start_dt + timedelta(days=i)
        current_date_str = current_dt.strftime("%Y-%m-%d")
        
        # 复用 get_douyin_verify_records 的逻辑 (直接调用函数而非 Tool invoke，减少 overhead)
        # 注意：这里我们直接调用内部逻辑，避免 Tool 的额外包装
        
        # 构造时间戳
        day_start = current_dt.replace(hour=0, minute=0, second=0)
        day_end = current_dt.replace(hour=23, minute=59, second=59)
        
        # 获取 Token
        headers = get_headers()
        if not headers.get('access-token'):
            return {"error": "Failed to get token"}
            
        url = 'https://open.douyin.com/goodlife/v1/fulfilment/certificate/verify_record/query/'
        params = {
            'account_id': ACCOUNT_ID,
            'cursor': '0',
            'size': 20,
            'start_time': int(day_start.timestamp()),
            'end_time': int(day_end.timestamp()),
        }
        
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                raw_data = resp.json()
                if raw_data.get("data", {}).get("error_code") == 0:
                    processed = _process_verify_data(raw_data, current_date_str)
                    
                    # 聚合数据
                    daily_rev = processed["summary"]["total_revenue"]
                    total_revenue += daily_rev
                    total_orders += processed["summary"]["total_orders"]
                    
                    chart_x.append(current_date_str)
                    chart_y.append(daily_rev)
                    
                    # 聚合商品
                    for p_name, p_data in processed["product_breakdown"].items():
                        if p_name not in product_agg:
                            product_agg[p_name] = {"count": 0, "revenue": 0.0}
                        product_agg[p_name]["count"] += p_data["count"]
                        product_agg[p_name]["revenue"] += p_data["revenue"]
                        
                    daily_results.append({
                        "date": current_date_str,
                        "revenue": daily_rev,
                        "orders": processed["summary"]["total_orders"]
                    })
                else:
                    print(f"⚠️ API Error for {current_date_str}: {raw_data}")
            
            # 简单的限流保护 (QPS 200 很高，但保险起见 sleep 0.1s)
            time.sleep(0.1)
            
        except Exception as e:
            print(f"⚠️ Request failed for {current_date_str}: {e}")

    # 生成图表
    chart_info = {}
    if need_chart and chart_x:
        chart_res = generate_chart.invoke({
            "chart_type": "line",
            "title": f"Douyin Sales Trend ({start_date} ~ {end_date})",
            "x_data": chart_x,
            "y_data": chart_y,
            "x_label": "Date",
            "y_label": "Revenue (CNY)"
        })
        if chart_res.get("status") == "success":
            chart_info["chart_url"] = chart_res.get("image_url")
            chart_info["chart_markdown"] = chart_res.get("markdown")

    # 排序热门商品
    sorted_products = sorted(product_agg.items(), key=lambda x: x[1]["revenue"], reverse=True)
    top_products = {k: v for k, v in sorted_products[:5]}

    report = {
        "period": f"{start_date} to {end_date}",
        "summary": {
            "total_revenue": round(total_revenue, 2),
            "total_orders": total_orders,
            "avg_daily_revenue": round(total_revenue / days, 2) if days > 0 else 0
        },
        "top_selling_products": top_products,
        "daily_trend": daily_results
    }
    report.update(chart_info)
    
    return report

def _process_verify_data(data: dict, date_str: str) -> dict:
    
    records = data.get("data", {}).get("records", [])
    
    summary = { "total_orders": len(records), "total_revenue": 0.0 }
    product_stats = {}
    details = []
    
    for record in records:
        # 1. 提取金额 (单位：分 -> 元)
        amount_info = record.get("amount", {})
        pay_amount_cents = amount_info.get("pay_amount", 0)
        pay_amount = pay_amount_cents / 100.0
        
        summary["total_revenue"] += pay_amount
        
        # 2. 提取商品信息
        sku_info = record.get("sku", {})
        product_name = sku_info.get("title", "Unknown")
        
        if product_name not in product_stats:
            product_stats[product_name] = {"count": 0, "revenue": 0.0}
        product_stats[product_name]["count"] += 1
        product_stats[product_name]["revenue"] += pay_amount
        
        # 3. 提取核销时间
        verify_time_ts = record.get("verify_time", 0)
        verify_time_str = datetime.fromtimestamp(verify_time_ts).strftime("%H:%M:%S")
        
        # 4. 构建详情项
        details.append({
            "time": verify_time_str,
            "product": product_name,
            "amount": pay_amount,
            "code": record.get("code"),
            "status": "Verified"
        })
    
    # 保留两位小数
    summary["total_revenue"] = round(summary["total_revenue"], 2)
    for p in product_stats.values():
        p["revenue"] = round(p["revenue"], 2)
    
    result = {
        "date": date_str,
        "summary": summary,
        "product_breakdown": product_stats,
        "details": details
    }
    
    # 打印清洗后的数据
    print(f"✅ [Douyin Verify Data] {date_str}: Revenue={summary['total_revenue']}, Orders={summary['total_orders']}")
    return result

# -------------------------------------------------------------------------
# Tool 3: 评价查询
# -------------------------------------------------------------------------
class CommentQueryInput(BaseModel):
    product_name: str = Field(..., description="商品名称，用于模糊匹配对应的抖音商品ID")

def _process_comment_data(data: dict, product_name: str) -> dict:
    """
    清洗评论数据
    """
    comments = data.get("data", {}).get("comments", [])
    
    total_score = 0
    valid_reviews = []
    
    for item in comments:
        info = item.get("comment_info", {})
        score = info.get("rate_score", 0)
        content = info.get("rate_text", "")
        create_time_ms = info.get("create_time", 0)
        
        total_score += score
        
        # 只保留有内容的评论
        if content:
            time_str = datetime.fromtimestamp(create_time_ms / 1000).strftime("%Y-%m-%d %H:%M")
            valid_reviews.append({
                "score": score,
                "content": content,
                "time": time_str
            })
            
    avg_score = round(total_score / len(comments), 1) if comments else 0
    
    result = {
        "product": product_name,
        "summary": {
            "total_comments": len(comments),
            "average_score": avg_score
        },
        "recent_reviews": valid_reviews
    }
    
    # 打印清洗后的数据
    print(f"✅ [Douyin Comment Data]:\n{json.dumps(result, indent=2, ensure_ascii=False)}")
    return result

from app.core.llm import get_embeddings_model

# ...

@tool("get_douyin_comments", args_schema=CommentQueryInput)
def get_douyin_comments(product_name: str) -> dict:
    """
    查询抖音店铺中特定商品的评价信息。
    支持查询最近90天的评论。
    """
    if not ACCOUNT_ID or not POI_ID:
        return {"error": "Missing ACCOUNT_ID, or POI_ID in .env"}
        
    if not db_engine:
        return {"error": "Database connection failed (DATABASE_URL missing)"}

    # 1. 查数据库获取 product_id (混合搜索：先向量，后模糊)
    product_id = None
    matched_name = None
    
    try:
        # 获取 Embedding
        embeddings_model = get_embeddings_model()
        query_vector = embeddings_model.embed_query(product_name)
        
        with db_engine.connect() as conn:
            # A. 尝试向量相似度匹配 (pgvector <-> 欧氏距离，<=> 余弦距离)
            # 只有当相似度足够高时才采用
            sql_vector = text("""
                SELECT product_id, name, (embedding <=> CAST(:query_vector AS vector)) as distance
                FROM products 
                ORDER BY distance ASC 
                LIMIT 1
            """)
            result = conn.execute(sql_vector, {"query_vector": query_vector}).fetchone()
            
            # 阈值判定 (距离 < 0.4 表示相似度 > 0.6)
            if result and result[2] < 0.4:
                product_id = result[0]
                matched_name = result[1]
                print(f"🎯 [Vector Match] '{product_name}' -> '{matched_name}' (Dist: {result[2]:.4f})")
            
            # B. 如果向量匹配失败，回退到 LIKE 模糊查询
            if not product_id:
                print(f"⚠️ [Vector Miss] '{product_name}' distance too high or no result. Fallback to LIKE.")
                sql_like = text("SELECT product_id, name FROM products WHERE name LIKE :p_name LIMIT 1")
                result = conn.execute(sql_like, {"p_name": f"%{product_name}%"}).fetchone()
                
                if result:
                    product_id = result[0]
                    matched_name = result[1]
                    print(f"🎯 [LIKE Match] '{product_name}' -> '{matched_name}'")
            
            if not product_id:
                return {"error": f"Product '{product_name}' not found in local database (both Vector and LIKE failed)."}
                
    except Exception as e:
        return {"error": f"Database/Embedding Error: {str(e)}"}

    # 2. 准备时间戳 (最近90天)
    end_ts = int(time.time())
    start_ts = int(time.time()) - (90 * 24 * 60 * 60)

    # 修正：将 POI_ID 转换为整数
    try:
        poi_id_int = int(POI_ID)
    except:
        return {"error": f"Invalid POI_ID format: {POI_ID}. Must be an integer."}

    url = 'https://open.douyin.com/goodlife/v1/akte/comment/query/'
    params = {
        'account_id': ACCOUNT_ID,
        'poi_id_list': [poi_id_int], # 确保是整数列表
        'product_id_list': [product_id], 
        'cursor': '0',
        'count': 100,
        'start_time': start_ts,
        'end_time': end_ts,
    }
    
    try:
        print(f"🚀 [Douyin] Querying comments for {matched_name} (ID: {product_id})...")
        # 获取 headers (包含动态获取的 token)
        headers = get_headers()
        if not headers.get('access-token'):
            return {"error": "Failed to obtain access_token (client_token). Check CLIENT_KEY/SECRET."}
            
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return {"error": f"API HTTP Error: {response.status_code}", "detail": response.text}
            
        data = response.json()
        
        # 数据清洗
        if data.get("data", {}).get("error_code") == 0:
            return _process_comment_data(data, matched_name)
        else:
            return {"error": "Douyin API Error", "raw": data}
        
    except Exception as e:
        return {"error": f"Request Failed: {str(e)}"}

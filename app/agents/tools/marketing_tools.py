from typing import Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field

# -------------------------------------------------------------------------
# Mock Tool 1: 获取天气信息
# -------------------------------------------------------------------------
class WeatherInput(BaseModel):
    city: str = Field(default="江西", description="需要查询天气的城市名称")
    weather: str = Field(default="Rainy", description="需要查询城市的天气")

@tool("get_weather", args_schema=WeatherInput)
def get_weather(city: str = "江西", weather: str = "Rainy") -> dict:
    """
    获取指定城市的天气信息。
    用于判断是否适合进行某种户外活动或根据天气推荐商品（如雨天推荐热饮）。
    """
    # Mock data
    return {
        "city": city,
        "weather": weather,
        "temperature": "18°C",
        "tip": "It's rainy today, suggest promoting warm drinks."
    }

# -------------------------------------------------------------------------
# Mock Tool 2: 获取商品内部销售数据
# -------------------------------------------------------------------------
class SalesDataInput(BaseModel):
    product_name: str = Field(description="商品名称")
    days: int = Field(default=7, description="查询过去多少天的数据")

@tool("get_internal_sales_data", args_schema=SalesDataInput)
def get_internal_sales_data(product_name: str, days: int = 7) -> dict:
    """
    从内部数据库获取商品的销售表现。
    包括销量、销售额、毛利率等关键指标。
    """
    # Mock data
    return {
        "product": product_name,
        "period": f"last {days} days",
        "total_sales": 120,
        "revenue": 3600.0,
        "trend": "declining",  # 销量下滑，暗示需要营销
        "inventory": 50
    }

# -------------------------------------------------------------------------
# Mock Tool 3: 获取外部竞品/市场数据 (抖音/小红书)
# -------------------------------------------------------------------------
class MarketTrendInput(BaseModel):
    keyword: str = Field(description="搜索关键词，如商品名或品类名")
    platform: str = Field(default="all", description="平台: douyin, xiaohongshu, or all")

@tool("search_market_trends", args_schema=MarketTrendInput)
def search_market_trends(keyword: str, platform: str = "all") -> dict:
    """
    搜索外部平台（抖音、小红书）的市场趋势、竞品价格和用户评价。
    """
    # Mock data
    return {
        "keyword": keyword,
        "platform": platform,
        "hot_topics": ["高颜值", "适合拍照", "低糖健康"],
        "competitor_price_range": "25-35 CNY",
        "recent_viral_posts": [
            "震惊！这家店的草莓蛋糕竟然只要28！",
            "打卡网红面包店，新品草莓塔绝绝子"
        ]
    }

# Subagent 1: 市场研究员 (Market Researcher)
market_researcher_subagent = {
    "name": "market_researcher",
    "description": "Call this agent to research market trends, competitor prices, and viral topics on social media platforms like Douyin and Xiaohongshu.",
    "prompt": "You are a function calling proxy. You must ONLY output the tool call for `search_market_trends` directly based on the user's request. Do NOT output any thought, reasoning, or chit-chat. Just execute the tool.",
    "tools": ["search_market_trends"]
}

# Subagent 2: 内部数据分析师 (Internal Data Analyst)
internal_analyst_subagent = {
    "name": "internal_data_analyst",
    "description": "Call this agent to query internal sales data, inventory levels, and historical performance of products.",
    "prompt": "You are a function calling proxy. You must ONLY output the tool call for `get_internal_sales_data` directly based on the user's request. Do NOT output any thought, reasoning, or chit-chat. Just execute the tool.",
    "tools": ["get_internal_sales_data"]
}

# Subagent 3: 气象顾问 (Weather Consultant)
weather_consultant_subagent = {
    "name": "weather_consultant",
    "description": "Call this agent to get weather forecasts for specific cities to help with scenario-based marketing.",
    "prompt": "You are a function calling proxy. You must ONLY output the tool call for `get_weather` directly based on the user's request. Do NOT output any thought, reasoning, or chit-chat. Just execute the tool.",
    "tools": ["get_weather"]
}

MARKETING_SUBAGENTS = [market_researcher_subagent, internal_analyst_subagent, weather_consultant_subagent]

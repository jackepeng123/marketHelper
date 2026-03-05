import requests
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from dotenv import load_dotenv, find_dotenv

_ = load_dotenv(find_dotenv())

AMAP_KEY = os.environ.get("AMAP_KEY")
QWEATHER_HOST = os.environ.get("QWEATHER_HOST")
QWEATHER_KEY = os.environ.get("QWEATHER_KEY")

# -------------------------------------------------------------------------
# 工具输入定义
# -------------------------------------------------------------------------
class ContextInput(BaseModel):
    city: Optional[str] = Field(default=None, description="用户提到的特定城市名称。")
    date: Optional[str] = Field(default=None, description="查询日期 (YYYY-MM-DD)。留空则默认今天。")
    forecast_days: Optional[str] = Field(default="7d", description="未来天气预报天数，可选：3d, 7d, 15d, 30d")

# -------------------------------------------------------------------------
# 内部辅助函数
# -------------------------------------------------------------------------
def _get_location(city: str = None) -> Dict[str, Any]:
    """
    获取经纬度与城市名。
    策略：
    1. 有 city -> 调高德地理编码 API
    2. 无 city -> 调高德 IP 定位 API
    返回: {"longitude": "116.41", "latitude": "39.92", "city": "北京市"}
    """
    try:
        if city:
            # 策略 1: 地理编码
            url = "https://restapi.amap.com/v3/geocode/geo"
            params = {"key": AMAP_KEY, "address": city}
            resp = requests.get(url, params=params, timeout=5).json()
            if resp.get("status") == "1" and resp.get("geocodes"):
                geo = resp["geocodes"][0]
                location = geo.get("location", "").split(",") # "116.480881,39.989410"
                if len(location) == 2:
                    return {
                        "longitude": f"{float(location[0]):.2f}",
                        "latitude": f"{float(location[1]):.2f}",
                        "city": geo.get("city") or city
                    }
        
        # 策略 2: IP 定位 (作为 fallback 或 默认)
        url = "https://restapi.amap.com/v3/ip"
        params = {"key": AMAP_KEY}
        resp = requests.get(url, params=params, timeout=5).json()
        if resp.get("status") == "1":
            # IP 定位返回的是 rectangle (矩形区域)，如 "116.40,39.90;116.42,39.92"
            # 我们取第一个点作为近似坐标
            rect = resp.get("rectangle", "")
            if rect:
                first_point = rect.split(";")[0].split(",")
                if len(first_point) == 2:
                    return {
                        "longitude": f"{float(first_point[0]):.2f}",
                        "latitude": f"{float(first_point[1]):.2f}",
                        "city": resp.get("city")
                    }
    except Exception as e:
        print(f"Location Error: {e}")
    
    # Fallback (如果都失败了，默认北京)
    return {"longitude": "116.40", "latitude": "39.90", "city": "北京市(Default)"}

def _lookup_city_id(lon: str, lat: str) -> Optional[str]:
    try:
        url = f"{QWEATHER_HOST}/geo/v2/city/lookup"
        # 注意：GeoAPI 的 key 和天气数据的 key 是通用的
        resp = requests.get(url, params={"key": QWEATHER_KEY, "location": f"{lon},{lat}"}, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "200" and data.get("location"):
                return data["location"][0]["id"]
    except Exception as e:
        print(f"City Lookup Error: {e}")
    return None

def _get_weather(lon: str, lat: str, date: str = None, forecast_days: str = "7d") -> Dict[str, Any]:
    """
    获取天气信息。
    """
    location = f"{lon},{lat}"
    result = {}
    
    # 默认值保护
    if not forecast_days:
        forecast_days = "7d"
        
    target_date = datetime.now()
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except:
            pass 
            
    today = datetime.now()
    diff_days = (target_date.date() - today.date()).days
    
    try:
        # 1. 查询历史天气 (如果是过去)
        if diff_days < 0:
            if diff_days < -10:
                result["note"] = "历史天气仅支持最近10天查询。"
            else:
                # 关键修复：历史天气必须使用 LocationID
                city_id = _lookup_city_id(lon, lat)
                if not city_id:
                     result["error"] = "Failed to lookup City ID for history weather."
                else:
                    date_str = target_date.strftime("%Y%m%d")
                    url_history = f"{QWEATHER_HOST}/v7/historical/weather"
                    # 增加请求检查
                    resp = requests.get(url_history, params={"key": QWEATHER_KEY, "location": city_id, "date": date_str}, timeout=5)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("code") == "200" and "weatherDaily" in data:
                            result["history_weather"] = data["weatherDaily"]
                        else:
                            result["error"] = f"History API Error: {data.get('code')}"
                    else:
                        result["error"] = f"History API HTTP Error: {resp.status_code}"
                
        # 2. 查询未来预报 (如果是今天或未来)
        else:
            url_forecast = f"{QWEATHER_HOST}/v7/weather/{forecast_days}"
            resp = requests.get(url_forecast, params={"key": QWEATHER_KEY, "location": location}, timeout=5)
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == "200":
                    target_str = target_date.strftime("%Y-%m-%d")
                    forecasts = data.get("daily", [])
                    result["forecast_list"] = forecasts
                    
                    if date:
                        found = next((f for f in forecasts if f["fxDate"] == target_str), None)
                        if found:
                            result["target_forecast"] = found
                        else:
                            result["note"] = f"Target date out of forecast range ({forecast_days})."
                else:
                    result["forecast_error"] = data.get("code")
            else:
                result["forecast_error"] = f"HTTP Error: {resp.status_code}"

    except Exception as e:
        print(f"Weather Error: {e}")
        result["error"] = str(e)
        
    return result

def _get_holiday(date: str = None) -> Dict[str, Any]:
    """
    获取节假日信息 (Timor API)
    """
    try:
        target_date = datetime.now()
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
            except:
                pass
                
        year = target_date.year
        date_str = target_date.strftime("%Y-%m-%d")
        
        # 直接构造带日期的 URL: https://timor.tech/api/holiday/info/2026-02-01
        url = f"https://timor.tech/api/holiday/info/{date_str}"
        
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=5)
        data = resp.json()
        
        if data.get("code") == 0:
            return {
                "date": date_str,
                "type": data.get("type", {}).get("name", "Unknown"), # 工作日/节假日/周末
                "holiday": data.get("holiday", None), # 具体节日信息
                "is_off_day": data.get("type", {}).get("type") in [1, 2, 3] # type: 0工作日 1周末 2节日 3调休
            }
            
    except Exception as e:
        print(f"Holiday Error: {e}")
        
    return {"status": "Holiday API Unavailable"}

# -------------------------------------------------------------------------
# 主工具定义
# -------------------------------------------------------------------------
def _simplify_weather(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    精简天气数据，只保留对营销分析有用的字段
    """
    simple = {}
    
    # 处理历史天气
    if "history_weather" in data:
        hw = data["history_weather"]
        simple["history"] = {
            "condition": hw.get("textDay"),
            "temp_max": hw.get("tempMax"),
            "temp_min": hw.get("tempMin")
        }
        
    # 处理预报
    if "forecast_list" in data:
        simple["forecast"] = []
        for f in data["forecast_list"]:
            simple["forecast"].append({
                "date": f["fxDate"],
                "condition": f["textDay"],
                "temp_range": f"{f['tempMin']}~{f['tempMax']}°C"
            })
    elif "forecast_3d" in data:
        simple["forecast"] = []
        for f in data["forecast_3d"]:
            simple["forecast"].append({
                "date": f["fxDate"],
                "condition": f["textDay"],
                "temp_range": f"{f['tempMin']}~{f['tempMax']}°C"
            })
            
    # 处理特定日期预报
    if "target_forecast" in data:
        tf = data["target_forecast"]
        simple["target_forecast"] = {
            "date": tf["fxDate"],
            "condition": tf["textDay"],
            "temp_range": f"{tf['tempMin']}~{tf['tempMax']}°C"
        }
        
    if "error" in data:
        simple["error"] = data["error"]
    if "note" in data:
        simple["note"] = data["note"]
        
    return simple

# ... (Previous code)

@tool("get_context_info", args_schema=ContextInput)
def get_context_info(city: str = None, date: str = None, forecast_days: str = "7d") -> dict:
    """
    获取环境上下文信息（地理、天气、节假日）。
    - city: 城市名 (可选)
    - date: 日期 YYYY-MM-DD (可选)
    - forecast_days: 预报天数 (3d/7d/15d/30d)
    """
    # 1. 定位
    loc_data = _get_location(city)
    
    # 2. 天气
    weather_raw = _get_weather(loc_data["longitude"], loc_data["latitude"], date, forecast_days)
    weather_simple = _simplify_weather(weather_raw)
    
    # 3. 节假日
    holiday_data = _get_holiday(date)
    
    return {
        "location": loc_data.get("city", "Unknown"),
        "weather": weather_simple,
        "holiday": holiday_data,
        "timestamp": datetime.now().strftime("%Y-%m-%d")
    }

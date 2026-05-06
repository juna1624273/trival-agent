"""Direct API fallback implementations.

When MCP services are not available, these functions call the underlying
REST APIs directly using httpx. This means you only need API keys —
no MCP servers to deploy.
"""

import json
import logging
from typing import Any, Dict

import httpx

from src.config.settings import settings

logger = logging.getLogger(__name__)

# Shared httpx client with timeout
_client = httpx.AsyncClient(timeout=httpx.Timeout(8.0))


# ============================================================
# Amap (高德地图) — Direct API
# ============================================================

AMAP_BASE = "https://restapi.amap.com/v3"


async def amap_geocode(address: str, city: str = "") -> Dict[str, Any]:
    """高德地理编码：地址 → 经纬度"""
    params = {"key": settings.amap_api_key, "address": address}
    if city:
        params["city"] = city
    resp = await _client.get(f"{AMAP_BASE}/geocode/geo", params=params)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "1" and data.get("geocodes"):
        geo = data["geocodes"][0]
        return {"location": geo["location"], "formatted_address": geo.get("formatted_address", address)}
    return {"error": data.get("info", "geocode failed"), "raw": data}


async def amap_search_poi(
    keywords: str, city: str = "", location: str = "", radius: int = 3000
) -> Dict[str, Any]:
    """高德POI搜索：周边酒店/景点/餐厅"""
    params = {
        "key": settings.amap_api_key,
        "keywords": keywords,
        "city": city,
        "radius": radius,
        "offset": 10,
    }
    if location:
        params["location"] = location
    resp = await _client.get(f"{AMAP_BASE}/place/text", params=params)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "1":
        pois = []
        for p in data.get("pois", []):
            pois.append({
                "name": p.get("name"),
                "address": p.get("address"),
                "location": p.get("location"),
                "rating": p.get("biz_ext", {}).get("rating", ""),
                "distance": p.get("distance", ""),
                "tel": p.get("tel", ""),
            })
        return {"pois": pois, "count": data.get("count", 0)}
    return {"error": data.get("info", "POI search failed"), "raw": data}


async def amap_direction(
    origin: str, destination: str, mode: str = "driving"
) -> Dict[str, Any]:
    """高德路径规划"""
    params = {
        "key": settings.amap_api_key,
        "origin": origin,
        "destination": destination,
    }
    if mode == "walking":
        resp = await _client.get(f"{AMAP_BASE}/direction/walking", params=params)
    elif mode == "transit":
        resp = await _client.get(f"{AMAP_BASE}/direction/transit/integrated", params=params)
    else:
        # 驾车路线
        params["extensions"] = "base"
        resp = await _client.get(f"{AMAP_BASE}/direction/driving", params=params)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "1":
        route = data.get("route", {})
        paths = route.get("paths", [])
        if paths:
            path = paths[0]
            return {
                "duration": str(path.get("duration", 0)),  # 秒
                "distance": str(path.get("distance", 0)),  # 米
                "mode": mode,
            }
    return {"error": data.get("info", "direction failed"), "raw": data}


# ============================================================
# OpenWeatherMap — Direct API
# 免费 API Key 在 https://openweathermap.org/api 注册
# ============================================================

WEATHER_BASE = "https://api.openweathermap.org/data/2.5"


_owm_dead_until: float = 0.0  # circuit breaker for OpenWeatherMap

async def weather_forecast(city: str, days: int = 7) -> Dict[str, Any]:
    """获取天气预报"""
    import time as _time
    global _owm_dead_until

    # Skip OpenWeatherMap if it recently failed
    if _time.time() < _owm_dead_until:
        return await _weather_via_free_api(city, days)

    if not settings.weather_api_key or settings.weather_api_key == "your-weather-api-key":
        return await _weather_via_free_api(city, days)

    try:
        params = {
            "q": city,
            "appid": settings.weather_api_key,
            "units": "metric",
            "lang": "zh_cn",
            "cnt": min(days, 16) * 8,  # 3-hour intervals
        }
        resp = await _client.get(f"{WEATHER_BASE}/forecast", params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("cod") == "200":
            forecasts = []
            for item in data.get("list", [])[::8]:  # one per day
                forecasts.append({
                    "date": item.get("dt_txt", ""),
                    "temp": item["main"]["temp"],
                    "temp_min": item["main"]["temp_min"],
                    "temp_max": item["main"]["temp_max"],
                    "humidity": item["main"]["humidity"],
                    "condition": item["weather"][0]["description"],
                    "wind_speed": item["wind"]["speed"],
                })
            return {"city": data["city"]["name"], "forecasts": forecasts[:days]}
        return {"error": data.get("message", "forecast failed"), "raw": data}
    except Exception as e:
        logger.warning(f"OpenWeatherMap failed, using wttr.in (OWM disabled for 5min): {e}")
        _owm_dead_until = _time.time() + 300
        return await _weather_via_free_api(city, days)


async def _weather_via_free_api(city: str, days: int) -> Dict[str, Any]:
    """Fallback: free weather API (wttr.in — no key needed)"""
    try:
        resp = await _client.get(f"https://wttr.in/{city}?format=j1&lang=zh")
        resp.raise_for_status()
        data = resp.json()
        forecasts = []
        for day_data in data.get("weather", [])[:days]:
            hourly = day_data.get("hourly", [])
            temps = [int(h["tempC"]) for h in hourly if h.get("tempC")]
            forecasts.append({
                "date": day_data.get("date", ""),
                "temp_min": min(temps) if temps else 0,
                "temp_max": max(temps) if temps else 0,
                "humidity": int(hourly[0].get("humidity", 0)) if hourly else 0,
                "condition": hourly[0]["weatherDesc"][0]["value"] if hourly else "",
                "wind_speed": hourly[0].get("windspeedKmph", 0) if hourly else 0,
            })
        return {"city": city, "forecasts": forecasts, "source": "wttr.in (free)"}
    except Exception as e:
        return {"error": str(e), "message": "天气服务不可用，请设置 WEATHER_API_KEY"}


# ============================================================
# Tavily Search — Direct API
# 免费 Key 在 https://tavily.com 注册（每月 1000 次）
# ============================================================

TAVILY_BASE = "https://api.tavily.com"


# Circuit breaker for Tavily — when it fails, skip it for a while
_tavily_dead_until: float = 0.0

async def tavily_search(query: str, num_results: int = 5) -> Dict[str, Any]:
    """Tavily 搜索 — 专为 AI Agent 优化"""
    import time as _time
    global _tavily_dead_until

    # Skip Tavily if it recently failed (circuit breaker, 5 min cooldown)
    if _time.time() < _tavily_dead_until:
        return await _search_via_duckduckgo(query, num_results)

    if not settings.search_api_key or settings.search_api_key == "your-search-api-key":
        return await _search_via_duckduckgo(query, num_results)

    try:
        resp = await _client.post(
            f"{TAVILY_BASE}/search",
            json={
                "api_key": settings.search_api_key,
                "query": query,
                "max_results": num_results,
                "search_depth": "basic",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for r in data.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0),
            })
        return {"results": results, "query": query}
    except Exception as e:
        logger.warning(f"Tavily search failed, using DuckDuckGo (Tavily disabled for 5min): {e}")
        _tavily_dead_until = _time.time() + 300  # 5-minute circuit breaker
        return await _search_via_duckduckgo(query, num_results)


async def _search_via_duckduckgo(query: str, num: int) -> Dict[str, Any]:
    """Fallback: DuckDuckGo instant answers (no key needed, but limited)"""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = []
            for r in ddgs.text(query, max_results=num):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "content": r.get("body", ""),
                })
            return {"results": results, "query": query, "source": "DuckDuckGo"}
    except ImportError:
        return {"results": [], "query": query, "error": "DuckDuckGo not available"}
    except Exception as e:
        return {"results": [], "query": query, "error": str(e)}


# ============================================================
# Transport / Hotel — Search-based aggregation
# ============================================================

async def search_transport(from_city: str, to_city: str, date: str) -> Dict[str, Any]:
    """Search for transport options (flights + trains) via web search."""
    query = f"{from_city} 到 {to_city} {date} 机票 火车票 价格 时刻表"
    return await tavily_search(query, num_results=5)


async def search_hotels(city: str, check_in: str, check_out: str) -> Dict[str, Any]:
    """Search for hotels via web search + Amap POI if available."""
    query = f"{city} 酒店 推荐 {check_in} 入住 {check_out} 退房 价格 评价"
    return await tavily_search(query, num_results=5)


# ============================================================
# Unified Tool Executor
# ============================================================


async def execute_tool(service_name: str, tool_name: str, args: Dict[str, Any]) -> str:
    """Execute a tool via direct API fallback. Returns JSON string result.

    This is used when MCP services are unavailable. It maps
    (service_name, tool_name) → direct API call.
    """
    try:
        result = await _dispatch(service_name, tool_name, args)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"API fallback failed: {service_name}.{tool_name}: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


async def _dispatch(service_name: str, tool_name: str, args: Dict[str, Any]) -> Any:
    """Route tool calls to the appropriate direct API."""
    svc = service_name
    tool = tool_name

    # ---- Amap ----
    if svc == "amap":
        if tool in ("geocode", "geocode_search"):
            return await amap_geocode(args.get("address", ""), args.get("city", ""))
        if tool in ("search_poi", "poi_search", "text_search"):
            return await amap_search_poi(
                args.get("keywords", args.get("query", "")),
                args.get("city", ""),
                args.get("location", ""),
                args.get("radius", 3000),
            )
        if tool in ("direction", "driving", "walking", "transit", "direction_planning"):
            return await amap_direction(
                args.get("origin", ""),
                args.get("destination", ""),
                args.get("mode", "driving"),
            )
        if tool in ("distance", "distance_search"):
            origin = args.get("origins", args.get("origin", ""))
            dest = args.get("destination", "")
            return await amap_direction(origin, dest, "driving")

    # ---- Weather ----
    if svc == "weather":
        if tool in ("get_forecast", "forecast", "get_weather_forecast"):
            days = int(args.get("days", args.get("cnt", 7)))
            return await weather_forecast(args.get("city", args.get("q", "")), days)
        if tool in ("get_current_weather", "current"):
            result = await weather_forecast(args.get("city", args.get("q", "")), 1)
            return result.get("forecasts", [{}])[0] if result.get("forecasts") else result

    # ---- Search ----
    if svc == "search":
        if tool in ("web_search", "search", "tavily_search"):
            return await tavily_search(
                args.get("query", args.get("q", "")),
                args.get("num_results", args.get("top_n", 5)),
            )
        if tool in ("search_attractions", "search_poi"):
            q = f"{args.get('city', '')} 热门景点 旅游攻略 {args.get('category', '')}"
            return await tavily_search(q, args.get("top_n", 10))
        if tool in ("search_restaurants", "search_food"):
            q = f"{args.get('city', '')} 美食 推荐 {args.get('cuisine_type', '')}"
            return await tavily_search(q, args.get("top_n", 10))
        if tool in ("get_travel_guide", "travel_guide"):
            q = f"{args.get('destination', '')} {args.get('duration', 3)}日游攻略"
            return await tavily_search(q, 5)
        if tool in ("search_local_info", "local_info"):
            q = f"{args.get('city', '')} {args.get('info_type', '')} 实用信息"
            return await tavily_search(q, 5)

    # ---- Railway ----
    if svc == "railway":
        query = f"{args.get('from_station', args.get('from', ''))} 到 {args.get('to_station', args.get('to', ''))} 火车票 {args.get('date', '')}"
        return await tavily_search(query, 5)

    # ---- Flight ----
    if svc == "flight":
        query = f"{args.get('from_city', args.get('from', ''))} 到 {args.get('to_city', args.get('to', ''))} 机票 {args.get('date', '')}"
        return await tavily_search(query, 5)

    # ---- Hotel ----
    if svc == "hotel":
        query = f"{args.get('city', '')} 酒店 {args.get('check_in', '')} 入住 {args.get('check_out', '')} 退房"
        return await tavily_search(query, 5)

    # Fallback: generic search
    query_parts = [f"{k}:{v}" for k, v in args.items() if v]
    if query_parts:
        query = " ".join(query_parts)
    else:
        query = f"{service_name} {tool_name}"
    return await tavily_search(query, 5)

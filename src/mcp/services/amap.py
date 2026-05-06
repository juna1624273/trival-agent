"""Amap (高德地图) MCP service configuration.

Provides: geocoding, reverse geocoding, POI search, direction planning, distance calculation.
"""

AMAP_SERVICE_CONFIG = {
    "name": "amap",
    "description": "高德地图 MCP 服务 — 地理编码、POI搜索、路径规划、距离计算",
    "tools": [
        {
            "name": "geocode",
            "description": "将地址转换为经纬度坐标",
            "parameters": {
                "address": {"type": "string", "description": "地址名称，如'北京市朝阳区'"},
                "city": {"type": "string", "description": "城市名称，可选"},
            },
        },
        {
            "name": "reverse_geocode",
            "description": "将经纬度坐标转换为地址",
            "parameters": {
                "location": {"type": "string", "description": "经纬度，格式'经度,纬度'"},
            },
        },
        {
            "name": "search_poi",
            "description": "搜索周边POI（兴趣点）",
            "parameters": {
                "keywords": {"type": "string", "description": "搜索关键词，如'酒店'、'餐厅'"},
                "city": {"type": "string", "description": "城市"},
                "location": {"type": "string", "description": "中心点坐标，可选"},
                "radius": {"type": "integer", "description": "搜索半径（米），默认3000"},
            },
        },
        {
            "name": "direction",
            "description": "路径规划 — 驾车/步行/公交",
            "parameters": {
                "origin": {"type": "string", "description": "起点坐标或地址"},
                "destination": {"type": "string", "description": "终点坐标或地址"},
                "mode": {"type": "string", "description": "出行方式：driving/walking/transit"},
            },
        },
        {
            "name": "distance",
            "description": "计算两点之间的距离",
            "parameters": {
                "origins": {"type": "string", "description": "起点坐标"},
                "destination": {"type": "string", "description": "终点坐标"},
            },
        },
    ],
}

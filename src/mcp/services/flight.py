"""Flight MCP service configuration.

Provides: flight search, price comparison, route analysis.
"""

FLIGHT_SERVICE_CONFIG = {
    "name": "flight",
    "description": "航班 MCP 服务 — 机票查询、价格比较、航线分析",
    "tools": [
        {
            "name": "search_airports",
            "description": "搜索机场信息",
            "parameters": {
                "city": {"type": "string", "description": "城市名称"},
            },
        },
        {
            "name": "query_flights",
            "description": "查询航班",
            "parameters": {
                "from_city": {"type": "string", "description": "出发城市"},
                "to_city": {"type": "string", "description": "到达城市"},
                "date": {"type": "string", "description": "出发日期，格式YYYY-MM-DD"},
                "passengers": {"type": "integer", "description": "乘客人数，默认1"},
                "cabin_class": {"type": "string", "description": "舱位：economy/business/first"},
            },
        },
        {
            "name": "compare_prices",
            "description": "比较多个航班的价格",
            "parameters": {
                "flight_numbers": {"type": "array", "description": "航班号列表"},
                "date": {"type": "string", "description": "日期"},
            },
        },
    ],
}

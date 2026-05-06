"""Weather MCP service configuration.

Provides: current weather, forecasts, alerts.
"""

WEATHER_SERVICE_CONFIG = {
    "name": "weather",
    "description": "天气 MCP 服务 — 实时天气、天气预报、气象预警",
    "tools": [
        {
            "name": "get_current_weather",
            "description": "获取实时天气",
            "parameters": {
                "city": {"type": "string", "description": "城市名称"},
                "location": {"type": "string", "description": "经纬度，可选"},
            },
        },
        {
            "name": "get_forecast",
            "description": "获取未来天气预报",
            "parameters": {
                "city": {"type": "string", "description": "城市名称"},
                "days": {"type": "integer", "description": "预报天数，1-15"},
            },
        },
        {
            "name": "check_alerts",
            "description": "检查气象预警",
            "parameters": {
                "city": {"type": "string", "description": "城市名称"},
            },
        },
        {
            "name": "get_travel_advice",
            "description": "获取出行天气建议",
            "parameters": {
                "city": {"type": "string", "description": "城市名称"},
                "date_range": {"type": "string", "description": "日期范围，如'2024-06-01..2024-06-03'"},
            },
        },
    ],
}

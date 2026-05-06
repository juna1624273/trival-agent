"""Hotel MCP service configuration.

Provides: hotel search, availability, price comparison.
"""

HOTEL_SERVICE_CONFIG = {
    "name": "hotel",
    "description": "酒店 MCP 服务 — 酒店搜索、房型查询、价格比较",
    "tools": [
        {
            "name": "search_hotels",
            "description": "搜索酒店",
            "parameters": {
                "city": {"type": "string", "description": "城市名称"},
                "check_in": {"type": "string", "description": "入住日期，格式YYYY-MM-DD"},
                "check_out": {"type": "string", "description": "退房日期，格式YYYY-MM-DD"},
                "guests": {"type": "integer", "description": "入住人数"},
                "price_min": {"type": "integer", "description": "最低价格"},
                "price_max": {"type": "integer", "description": "最高价格"},
                "star_rating": {"type": "integer", "description": "星级，3/4/5"},
            },
        },
        {
            "name": "get_hotel_detail",
            "description": "获取酒店详细信息",
            "parameters": {
                "hotel_id": {"type": "string", "description": "酒店ID"},
            },
        },
        {
            "name": "compare_hotels",
            "description": "比较多酒店",
            "parameters": {
                "hotel_ids": {"type": "array", "description": "酒店ID列表"},
            },
        },
        {
            "name": "search_nearby_hotels",
            "description": "搜索指定地点附近的酒店",
            "parameters": {
                "location": {"type": "string", "description": "经纬度或地址"},
                "radius": {"type": "integer", "description": "搜索半径（米）"},
                "check_in": {"type": "string", "description": "入住日期"},
                "check_out": {"type": "string", "description": "退房日期"},
            },
        },
    ],
}

"""Search MCP service configuration.

Provides: web search, attraction info, restaurant search, travel tips.
"""

SEARCH_SERVICE_CONFIG = {
    "name": "search",
    "description": "搜索 MCP 服务 — 景点信息、美食推荐、旅游攻略、综合搜索",
    "tools": [
        {
            "name": "web_search",
            "description": "通用网页搜索",
            "parameters": {
                "query": {"type": "string", "description": "搜索关键词"},
                "num_results": {"type": "integer", "description": "结果数量，默认5"},
            },
        },
        {
            "name": "search_attractions",
            "description": "搜索旅游景点",
            "parameters": {
                "city": {"type": "string", "description": "城市名称"},
                "category": {"type": "string", "description": "景点类型：自然风光/历史古迹/主题乐园/博物馆/购物"},
                "top_n": {"type": "integer", "description": "返回Top N结果，默认10"},
            },
        },
        {
            "name": "search_restaurants",
            "description": "搜索美食餐厅",
            "parameters": {
                "city": {"type": "string", "description": "城市名称"},
                "cuisine_type": {"type": "string", "description": "菜系：本地特色/川菜/粤菜/日料/西餐"},
                "price_level": {"type": "string", "description": "价位：人均低/中/高"},
            },
        },
        {
            "name": "get_travel_guide",
            "description": "获取旅游攻略",
            "parameters": {
                "destination": {"type": "string", "description": "目的地城市"},
                "duration": {"type": "integer", "description": "游玩天数"},
                "style": {"type": "string", "description": "旅行风格：休闲/紧凑/亲子/情侣"},
            },
        },
        {
            "name": "search_local_info",
            "description": "搜索当地实用信息",
            "parameters": {
                "city": {"type": "string", "description": "城市名称"},
                "info_type": {"type": "string", "description": "信息类型：交通/购物/文化/安全"},
            },
        },
    ],
}

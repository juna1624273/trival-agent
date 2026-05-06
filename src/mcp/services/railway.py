"""12306 Railway MCP service configuration.

Provides: train query, station search, ticket availability.
"""

RAILWAY_SERVICE_CONFIG = {
    "name": "railway",
    "description": "12306 铁路 MCP 服务 — 火车票查询、站点搜索、余票查询",
    "tools": [
        {
            "name": "search_stations",
            "description": "搜索火车站",
            "parameters": {
                "keyword": {"type": "string", "description": "站名关键词，如'北京'"},
            },
        },
        {
            "name": "query_trains",
            "description": "查询火车班次",
            "parameters": {
                "from_station": {"type": "string", "description": "出发站名或代码"},
                "to_station": {"type": "string", "description": "到达站名或代码"},
                "date": {"type": "string", "description": "出发日期，格式YYYY-MM-DD"},
                "train_type": {"type": "string", "description": "列车类型：G/D/Z/T/K，可选"},
            },
        },
        {
            "name": "check_tickets",
            "description": "查询余票信息",
            "parameters": {
                "train_no": {"type": "string", "description": "车次号"},
                "date": {"type": "string", "description": "日期，格式YYYY-MM-DD"},
                "from_station": {"type": "string", "description": "出发站"},
                "to_station": {"type": "string", "description": "到达站"},
            },
        },
    ],
}

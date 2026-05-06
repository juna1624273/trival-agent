"""Finalize Node — Assemble all results into final travel itinerary."""

import json
import logging
import time
from pathlib import Path
from typing import Dict, Any

from langgraph.types import RunnableConfig

from src.graph.state import TravelAgentState
from src.llm.provider import create_summarization_llm
from src.utils.json_parser import extract_json as _extract_json

logger = logging.getLogger(__name__)

FINALIZE_SYSTEM_PROMPT = """你是一个资深旅行攻略撰写专家，拥有10年以上旅游行业经验。请根据收集到的所有信息，生成一份**详尽、专业、可直接使用**的旅行攻略。

【核心要求】
- 每个章节内容必须充实，不要只给一两句话，要给出具体、可操作的信息
- 善用收集到的真实数据（交通班次、酒店详情、天气预报等），不要编造
- 如果某类信息在数据中确实缺失，请明确标注"暂未查询到"，不要留空
- 攻略应让一个初次到访的游客看完就能直接出发
- 【天气特别要求】天气是游客最关心的信息之一，必须详细：
  * 每天都要有独立的天气条目（覆盖全部行程日期）
  * 根据温度范围给出具体的穿衣建议（如"建议薄外套+短袖，早晚温差大需备一件夹克"），不要只说"注意保暖"这种空话
  * 降水概率根据天气状况合理推算（晴天0-10%，多云20-40%，阴天50-70%，雨天80-100%）
  * 紫外线强度根据天气和季节推算（晴天强，阴天弱）
  * 如果原始天气数据不足，基于温度数据合理推断以上信息

攻略必须严格按照以下 JSON 结构输出（字段名必须一致）：

{
  "overview": {
    "destination": "目的地城市全称",
    "duration": "行程天数（如'3天2晚'）",
    "departure_city": "出发城市",
    "travelers": 人数,
    "travel_dates": "出发~返回日期",
    "total_budget": "总预算（元）",
    "best_season": "最佳旅行季节及理由",
    "highlights": ["本次行程亮点1", "亮点2", "亮点3"]
  },
  "transport": [
    {
      "type": "去程/回程",
      "mode": "高铁/飞机/自驾",
      "from": "出发站/机场",
      "to": "到达站/机场",
      "departure_time": "出发具体时间",
      "arrival_time": "到达具体时间",
      "duration": "耗时",
      "company": "航空公司或车次号",
      "seat_class": "座位等级",
      "price": 价格数字,
      "booking_tips": "订票建议或注意事项"
    }
  ],
  "city_transport": {
    "airport_to_city": "机场/火车站到市区的交通方式和费用",
    "subway": "地铁线路及票价说明",
    "bus": "公交出行建议",
    "taxi": "打车费用参考",
    "recommended": "推荐的市内出行方式"
  },
  "weather": [
    {
      "date": "日期",
      "condition": "天气状况",
      "temp_min": 最低温度,
      "temp_max": 最高温度,
      "humidity": "湿度百分比",
      "wind": "风力描述",
      "uv_index": "紫外线强度",
      "rain_probability": "降水概率百分比",
      "clothing_advice": "穿衣建议"
    }
  ],
  "hotels": [
    {
      "name": "酒店全名",
      "stars": 星级,
      "tier": "经济型/舒适型/豪华型",
      "location": "详细地址",
      "nearby": "周边地标或交通站点",
      "distance_to_center": "距市中心距离",
      "facilities": ["设施1", "设施2"],
      "breakfast": "是否含早",
      "cancellation": "取消政策",
      "check_in_time": "入住时间",
      "price_per_night": 每晚价格,
      "total_price": 住宿总价,
      "booking_url_or_platform": "推荐预订平台",
      "pros": ["优点1", "优点2"],
      "cons": ["缺点1"]
    }
  ],
  "daily_schedule": [
    {
      "day": "第N天",
      "date": "日期",
      "theme": "当日主题（如'古都文化探索'）",
      "weather_summary": "当日天气简述",
      "items": [
        {
          "time": "时间段（如07:30-08:30）",
          "activity": "活动名称",
          "description": "详细描述，包括看点、注意事项",
          "transport": "如何到达",
          "duration": "建议停留时长",
          "cost": 费用,
          "tips": "实用小贴士"
        }
      ],
      "meals": [
        {"type": "早餐/午餐/晚餐", "recommendation": "推荐餐厅或食物", "estimated_cost": 费用}
      ]
    }
  ],
  "attractions": [
    {
      "name": "景点名称",
      "description": "详细介绍（50字以上），包括历史背景、看点、特色",
      "rating": "评分（如4.5）",
      "ticket_price": 门票价格,
      "opening_hours": "开放时间",
      "suggested_duration": "建议游览时长",
      "address": "详细地址",
      "how_to_get_there": "交通方式",
      "tips": "游览建议（最佳拍照点、避开人群时间等）",
      "must_see": "必看亮点"
    }
  ],
  "restaurants": [
    {
      "name": "餐厅名",
      "cuisine": "菜系类型",
      "description": "详细介绍（招牌菜、环境、历史）",
      "signature_dishes": ["招牌菜1", "招牌菜2"],
      "rating": 评分,
      "price_per_person": 人均价格,
      "address": "地址",
      "opening_hours": "营业时间",
      "reservation": "是否需要预约",
      "tips": "用餐建议"
    }
  ],
  "food_specialties": [
    {
      "name": "当地特色美食名",
      "description": "详细介绍",
      "where_to_try": "推荐品尝地点",
      "price_range": "价格区间"
    }
  ],
  "shopping": {
    "specialties": ["当地特产1", "特产2"],
    "shopping_areas": [
      {"name": "商圈名", "description": "特点介绍", "what_to_buy": "适合买什么"}
    ],
    "souvenir_tips": "购买纪念品建议"
  },
  "tips": [
    "实用贴士1（含具体信息，不要泛泛而谈）",
    "实用贴士2"
  ],
  "budget_estimate": {
    "total": 总预算数字,
    "transport": 交通费用,
    "accommodation": 住宿费用,
    "meals": 餐饮费用,
    "attractions": 景点门票,
    "shopping": 购物预算,
    "other": 其他（保险、通讯等）
  }
}

【详细度检查清单】
1. transport 必须包含去程和回程两段，每段有具体时间、车次/航班号、价格
2. daily_schedule 每天至少 4 个时间段的活动，包含具体的餐饮推荐
3. attractions 至少列出 3 个景点，每个景点描述不少于 50 字
4. restaurants 至少列出 3 家餐厅，每家标注人均价格和招牌菜
5. hotels 至少推荐 2 家不同档次的酒店
6. tips 至少 5 条，每条要有具体内容而非空洞建议
7. weather 如有数据覆盖全部行程日期
8. budget_estimate 各项费用累加应等于 total

只输出 JSON，不要包含 markdown 代码块标记或其他文字。"""


async def finalize_node(state: TravelAgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Generate the final travel itinerary from all collected data.

    Collects all tool results, synthesizes them into a structured itinerary.
    Optionally triggers the file agent to export the itinerary.
    """
    logger.info(f"[Finalize] Generating final itinerary for thread {state.get('thread_id', 'unknown')}")

    tool_results = state.get("tool_results", [])
    if not tool_results:
        return {
            "final_itinerary": {"error": "未收集到任何信息", "message": "请重新规划"},
            "current_phase": "done",
        }

    # Organize results by agent type
    organized = _organize_results(tool_results)

    # Generate final itinerary using LLM
    llm = create_summarization_llm(model=state.get("llm_model"))
    prompt = f"""请根据以下收集到的旅行信息，生成一份**详尽专业**的旅行攻略。

【原始数据 - 请充分挖掘其中信息】
{json.dumps(organized, ensure_ascii=False, indent=2)}

【用户需求】
{state.get('user_query', '')}

【用户偏好】
{json.dumps(state.get('user_profile', {}), ensure_ascii=False)}

【生成要求】
1. 不要只罗列数据，要对数据进行分析、归纳、对比，给出明确推荐
2. 行程安排要合理，每天景点不要太多（3-5个为宜），考虑地理位置就近原则
3. 餐饮要结合当地特色，推荐具体菜品而非泛泛的"当地美食"
4. 所有金额和数字信息优先使用原始数据中的真实值
5. 如果某些信息在数据中不存在，可以基于常识合理补充，但不要编造具体价格和班次
6. 攻略语言要生动有温度，像是朋友在帮你做攻略，而不是机器输出

请严格按照系统提示中的 JSON 结构生成，所有数组字段必须使用数组格式。只输出 JSON。"""

    try:
        response = await llm.ainvoke([
            {"role": "system", "content": FINALIZE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ])

        itinerary = _extract_json(response.content)
        itinerary["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        itinerary["thread_id"] = state.get("thread_id", "")

        logger.info(f"[Finalize] Itinerary generated successfully")
    except Exception as e:
        logger.error(f"[Finalize] Failed to generate itinerary: {e}")
        itinerary = {
            "summary": "旅行攻略",
            "sections": organized,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "note": "自动生成的攻略，可能需要进一步优化",
        }

    # Try to generate file artifact (if file agent is available)
    artifacts = []
    try:
        file_agent = config.get("configurable", {}).get("agents", {}).get("file")
        if file_agent:
            # Generate an Excel-like structured output
            artifact_path = f"itinerary_{state.get('thread_id', 'unknown')}.json"
            save_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "itineraries"
            save_dir.mkdir(parents=True, exist_ok=True)
            full_path = str(save_dir / artifact_path)
            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(itinerary, f, ensure_ascii=False, indent=2)
            artifacts.append(full_path)
            logger.info(f"[Finalize] Saved itinerary to {full_path}")
    except Exception as e:
        logger.warning(f"[Finalize] Failed to save file artifact: {e}")

    return {
        "final_itinerary": itinerary,
        "artifacts": artifacts,
        "current_phase": "done",
    }


def _organize_results(tool_results: list) -> Dict[str, Any]:
    """Organize tool results by agent type for synthesis."""
    organized = {}
    for tr in tool_results:
        agent_type = tr.get("agent_type", "unknown")
        if agent_type not in organized:
            organized[agent_type] = []
        organized[agent_type].append({
            "description": tr.get("description", ""),
            "data": tr.get("observation", ""),
            "complete": tr.get("complete", False),
        })
    return organized


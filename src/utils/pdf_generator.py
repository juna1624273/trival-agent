"""PDF generator for travel itineraries with Chinese font support.

Handles multiple LLM output formats by checking field name aliases.
Supports map embedding via Amap static map API and cover page generation.
"""

import asyncio
import logging
import os
from io import BytesIO
from typing import Dict, Any, List, Optional

import httpx
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image, PageBreak, KeepTogether,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

logger = logging.getLogger(__name__)

# ── Font ─────────────────────────────────────────────────────────────
_CJK_FONT_NAME = None


def _register_cjk_font():
    global _CJK_FONT_NAME
    if _CJK_FONT_NAME:
        return _CJK_FONT_NAME
    font_candidates = [
        ("MicrosoftYaHei", "C:/Windows/Fonts/msyh.ttc"),
        ("MicrosoftYaHei", "C:/Windows/Fonts/msyh.ttf"),
        ("SimHei", "C:/Windows/Fonts/simhei.ttf"),
        ("SimSun", "C:/Windows/Fonts/simsun.ttc"),
    ]
    for name, path in font_candidates:
        if os.path.exists(path):
            try:
                if path.endswith(".ttc"):
                    pdfmetrics.registerFont(TTFont(name, path, subfontIndex=0))
                else:
                    pdfmetrics.registerFont(TTFont(name, path))
                _CJK_FONT_NAME = name
                logger.info(f"PDF font registered: {name} ({path})")
                return name
            except Exception as e:
                logger.warning(f"Failed to register font {name}: {e}")
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        _CJK_FONT_NAME = "STSong-Light"
        logger.info("PDF font fallback: STSong-Light (CID)")
        return _CJK_FONT_NAME
    except Exception:
        _CJK_FONT_NAME = "Helvetica"
        logger.warning("NO CJK FONT FOUND. PDF will have encoding issues.")
        return _CJK_FONT_NAME


def _strip_emoji(text: str) -> str:
    """Remove emoji and special symbols that CJK fonts can't render."""
    if not isinstance(text, str):
        return str(text) if text else ""
    result = []
    for ch in text:
        cp = ord(ch)
        # Keep: ASCII printable, CJK, Latin extensions, common punctuation
        if (cp < 0x007F or                          # ASCII
            0x2000 <= cp <= 0x206F or                # General Punctuation
            0x2E80 <= cp <= 0x9FFF or                # CJK Radicals + Unified Ideographs
            0xA000 <= cp <= 0xA4CF or                # Yi
            0xF900 <= cp <= 0xFAFF or                # CJK Compatibility
            0xFE10 <= cp <= 0xFE6F or                # Vertical Forms + Small Form Variants
            0xFF00 <= cp <= 0xFFEF or                # Halfwidth/Fullwidth Forms
            0x20000 <= cp <= 0x2FFFF):               # CJK Extension B+
            result.append(ch)
        # Replace common emoji/symbols with text equivalents
        elif ch in "⭐":
            result.append("*")
        elif ch in "💰":
            result.append("")
        elif ch in "🎫🚇🚌✈️🚄🚅🚆🚗🚕🚙":
            result.append("")
        elif ch in "💡":
            result.append("[提示]")
        elif ch in "👍":
            result.append("[+]")
        elif ch in "👎":
            result.append("[-]")
        elif ch in "📅🕐⏱☀️🌧️🌤️⛅":
            result.append("")
        elif cp < 0x2000:
            result.append(ch)  # control chars etc
        # Otherwise skip the character (emoji, etc.)
    return "".join(result).strip()


def _get_font_name() -> str:
    return _register_cjk_font() or "Helvetica"


# ── Amap Static Map Helpers ────────────────────────────────────────────

def _amap_key() -> str:
    try:
        from src.config.settings import settings
        key = settings.amap_api_key
        if key:
            return key
    except Exception:
        pass
    return os.getenv("AMAP_API_KEY", "")


def _geocode_sync(address: str, city: str = "") -> Optional[tuple]:
    """Geocode an address to (lng, lat) via Amap API. Returns None on failure."""
    key = _amap_key()
    if not key or not address:
        return None
    try:
        resp = httpx.get(
            "https://restapi.amap.com/v3/geocode/geo",
            params={"key": key, "address": address, "city": city},
            timeout=5.0,
        )
        data = resp.json()
        if data.get("status") == "1" and data.get("geocodes"):
            loc = data["geocodes"][0]["location"]
            lng, lat = loc.split(",")
            return (float(lng), float(lat))
    except Exception as e:
        logger.warning(f"Geocode failed for '{address}': {e}")
    return None


def _fetch_static_map(center: tuple, markers: list, zoom: int = 12) -> Optional[BytesIO]:
    """Fetch a static map image from Amap. markers: list of (lng, lat, label)."""
    key = _amap_key()
    if not key or not center:
        return None

    params = {
        "key": key,
        "location": f"{center[0]},{center[1]}",
        "zoom": str(zoom),
        "size": "1024*600",
    }

    if markers:
        m_parts = []
        for i, (_lng, _lat, _label) in enumerate(markers):
            letter = chr(ord('A') + i) if i < 26 else str(i)
            m_parts.append(f"mid,,{letter}:{_lng},{_lat}")
        params["markers"] = "|".join(m_parts)

    try:
        resp = httpx.get(
            "https://restapi.amap.com/v3/staticmap",
            params=params, timeout=10.0,
        )
        if resp.status_code == 200:
            return BytesIO(resp.content)
    except Exception as e:
        logger.warning(f"Static map fetch failed: {e}")
    return None


# ── Colors ────────────────────────────────────────────────────────────
PRIMARY = HexColor("#1a73e8")
ACCENT = HexColor("#0d9488")
DARK = HexColor("#1e293b")
GRAY = HexColor("#64748b")
LIGHT_BG = HexColor("#f1f5f9")
BORDER = HexColor("#e2e8f0")


def _build_styles(font_name: str) -> dict:
    return {
        "title": ParagraphStyle("T", fontName=font_name, fontSize=26, leading=34,
                                alignment=TA_CENTER, textColor=DARK, spaceAfter=6 * mm),
        "subtitle": ParagraphStyle("ST", fontName=font_name, fontSize=11, leading=16,
                                   alignment=TA_CENTER, textColor=GRAY, spaceAfter=12 * mm),
        "h1": ParagraphStyle("H1", fontName=font_name, fontSize=18, leading=24,
                             textColor=PRIMARY, spaceBefore=10 * mm, spaceAfter=4 * mm),
        "h2": ParagraphStyle("H2", fontName=font_name, fontSize=14, leading=20,
                             textColor=ACCENT, spaceBefore=6 * mm, spaceAfter=3 * mm),
        "body": ParagraphStyle("B", fontName=font_name, fontSize=10, leading=17,
                               textColor=DARK, alignment=TA_JUSTIFY, spaceAfter=2 * mm),
        "small": ParagraphStyle("SM", fontName=font_name, fontSize=8, leading=12,
                                textColor=GRAY),
        "th": ParagraphStyle("TH", fontName=font_name, fontSize=10, leading=14, textColor=white),
        "td": ParagraphStyle("TD", fontName=font_name, fontSize=9, leading=14, textColor=DARK),
    }


# ── Adaptive field lookup ─────────────────────────────────────────────

def _get(d, *keys, default=None):
    """Try multiple keys until one returns a truthy value."""
    if not isinstance(d, dict):
        return default
    for k in keys:
        v = d.get(k)
        if v is not None and v != "" and v != [] and v != {}:
            return v
    return default


def _find_section(data: dict, *names):
    """Find a section by trying multiple top-level key names."""
    for n in names:
        v = data.get(n)
        if isinstance(v, (dict, list)) and v != {} and v != []:
            return v
    return None


# ── Helpers ───────────────────────────────────────────────────────────

def _section(text: str, styles: dict) -> list:
    return [Paragraph(text, styles["h1"]),
            HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceAfter=4 * mm)]


def _table(rows: list, styles: dict, col_widths: list = None) -> Table:
    if not rows or len(rows) < 2:
        return Spacer(1, 1 * mm)
    # Strip emoji from all cell values
    rows = [[_strip_emoji(str(cell)) for cell in row] for row in rows]
    t = Table(rows, colWidths=col_widths, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), styles["td"].fontName),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (-1, 0), styles["th"].fontName),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _pa(text, styles, style="body"):
    return Paragraph(_strip_emoji(text), styles[style])


# ── Section: Overview ─────────────────────────────────────────────────

def _build_overview(data: dict, styles: dict) -> list:
    overview = _find_section(data, "trip_overview", "overview", "行程概览",
                             "trip_summary", "summary")
    if not overview:
        return []

    elements = _section("行程概览", styles)
    fields = [
        ["项目", "详情"],
        ["目的地", _get(overview, "destination", "目的地") or ""],
        ["出发城市", _get(overview, "departure_city", "departure", "出发城市") or "-"],
        ["行程日期", _get(overview, "travel_dates", "dates", "date_range", "日期") or "-"],
        ["预算预估", _get(overview, "total_budget_estimate", "total_budget", "budget", "预算") or "-"],
    ]
    # Filter truly empty
    fields = [f for f in fields if f[1]]
    if len(fields) > 1:
        elements.append(_table(fields, styles, col_widths=[40 * mm, 120 * mm]))
        elements.append(Spacer(1, 4 * mm))

    # Budget breakdown inside overview
    budget = _get(overview, "budget_breakdown", "budget_estimate", "预算明细", "费用明细")
    if budget and isinstance(budget, dict):
        elements.append(_pa("<b>费用明细</b>", styles, "h2"))
        for k, v in budget.items():
            elements.append(_pa(f"• {k}：{v}", styles))
        elements.append(Spacer(1, 4 * mm))

    return elements


# ── Section: Transport ────────────────────────────────────────────────

def _build_transport(data: dict, styles: dict) -> list:
    """Render transport section. Supports list/dict formats and new city_transport."""
    transport = _find_section(data, "transportation", "transport", "交通方案", "交通")
    if not transport:
        return []

    elements = _section("交通方案", styles)

    def _render_leg(leg: dict):
        """Render a single transport leg (outbound/return or from/to pair)."""
        rows = [["项目", "详情"]]
        mode = _get(leg, "mode", "type", "方式") or ""
        dep = _get(leg, "departure_station", "from", "departure", "出发站") or ""
        arr = _get(leg, "arrival_station", "to", "arrival", "到达站") or ""
        date = _get(leg, "departure_time", "date", "日期") or ""
        arr_time = _get(leg, "arrival_time") or ""
        dur = _get(leg, "duration", "时长") or ""
        price = _get(leg, "price", "价格") or ""
        seat = _get(leg, "seat_class", "座位") or ""
        company = _get(leg, "company") or ""
        tips = _get(leg, "booking_tips", "tips", "提示") or ""

        if mode:
            rows.append(["方式", mode])
        if company:
            rows.append(["车次/航班", company])
        if dep and arr:
            rows.append(["区间", f"{dep} → {arr}"])
        if date:
            rows.append(["出发", date])
        if arr_time:
            rows.append(["到达", arr_time])
        if seat:
            rows.append(["座位", seat])
        if dur:
            rows.append(["时长", dur])
        if price:
            rows.append(["票价", f"{price}"])
        if len(rows) > 1:
            elements.append(_table(rows, styles, col_widths=[40 * mm, 120 * mm]))
        if tips:
            elements.append(_pa(f"[!] {tips}", styles, "small"))
        elements.append(Spacer(1, 3 * mm))

        # recommended_trains list
        trains = _get(leg, "recommended_trains", "example_trains") or []
        if trains:
            elements.append(Spacer(1, 2 * mm))
            elements.append(_pa("<b>推荐车次：</b>", styles))
            train_rows = [["车次", "出发", "到达", "时长", "票价"]]
            for tr in trains:
                if isinstance(tr, dict):
                    train_rows.append([
                        _get(tr, "train_number", "车次") or "",
                        _get(tr, "departure", "出发") or "",
                        _get(tr, "arrival", "到达") or "",
                        _get(tr, "duration", "时长") or "",
                        _get(tr, "price", "票价") or "",
                    ])
            elements.append(_table(train_rows, styles))

        elements.append(Spacer(1, 3 * mm))

    # Handle list format (new standardized format)
    if isinstance(transport, list):
        rows = [["方式", "路线", "时间", "价格"]]
        for t in transport:
            if isinstance(t, dict):
                rows.append([
                    _get(t, "type", "方式") or "",
                    _get(t, "route", "路线") or f"{_get(t, 'from', '') or ''} → {_get(t, 'to', '') or ''}",
                    _get(t, "departure_time", "时间") or "",
                    _get(t, "price", "价格") or "",
                ])
        elements.append(_table(rows, styles))

    # Handle dict formats (legacy / nested)
    elif isinstance(transport, dict):
        # Handle round_trip format (test-v2 style)
        round_trip = _get(transport, "round_trip", "往返交通")
        if round_trip and isinstance(round_trip, dict):
            rec = round_trip.get("recommended_mode", "")
            if rec:
                elements.append(_pa(f"推荐出行方式：<b>{rec}</b>", styles))
                elements.append(Spacer(1, 2 * mm))
            for key, leg in round_trip.items():
                if key == "recommended_mode":
                    continue
                if isinstance(leg, dict):
                    label = {"from_beijing_to_hangzhou": "去程", "from_hangzhou_to_beijing": "回程",
                             "outbound": "去程", "return": "回程"}.get(key, key)
                    elements.append(_pa(f"<b>{label}</b>", styles, "h2"))
                    _render_leg(leg)

        # Handle outbound/return format (test-prod style)
        else:
            out = _get(transport, "outbound", "out", "去程")
            ret = _get(transport, "return", "inbound", "回程")
            if out:
                elements.append(_pa("<b>去程</b>", styles, "h2"))
                _render_leg(out)
            if ret:
                elements.append(_pa("<b>回程</b>", styles, "h2"))
                _render_leg(ret)
            # If no outbound/return but has other keys, try to render them all
            if not out and not ret:
                for key, val in transport.items():
                    if isinstance(val, dict):
                        elements.append(_pa(f"<b>{key}</b>", styles, "h2"))
                        _render_leg(val)
                    elif isinstance(val, str) and key not in ("total_transport_cost",):
                        elements.append(_pa(f"• {key}：{val}", styles))

            total = _get(transport, "total_transport_cost", "total_cost")
            if total:
                elements.append(_pa(f"交通总费用：<b>{total}</b>", styles))

        # Local transport (inside dict)
        local = _get(transport, "local_transport", "市内交通", "city_transport")
        if local:
            elements.append(Spacer(1, 2 * mm))
            elements.append(_pa("<b>市内交通</b>", styles, "h2"))
            if isinstance(local, dict):
                for k, v in local.items():
                    elements.append(_pa(f"• {k}：{v}", styles))
            elif isinstance(local, str):
                for line in local.split("."):
                    line = line.strip()
                    if line:
                        elements.append(_pa(f"• {line}", styles))

    # Handle string
    elif isinstance(transport, str):
        elements.append(_pa(transport, styles))

    return elements


# ── Section: City Transport ───────────────────────────────────────────

def _build_city_transport(data: dict, styles: dict) -> list:
    ct = data.get("city_transport", {})
    if not ct or not isinstance(ct, dict):
        return []

    elements = _section("市内交通", styles)

    items = [
        ("机场/火车站→市区", ct.get("airport_to_city")),
        ("地铁", ct.get("subway")),
        ("公交", ct.get("bus")),
        ("打车", ct.get("taxi")),
    ]
    for label, val in items:
        if val:
            elements.append(_pa(f"<b>{label}：</b>{val}", styles))

    rec = ct.get("recommended")
    if rec:
        elements.append(Spacer(1, 2 * mm))
        elements.append(_pa(f"💡 <b>推荐：</b>{rec}", styles))

    return elements


# ── Section: Attractions ──────────────────────────────────────────────

def _build_attractions(data: dict, styles: dict) -> list:
    attrs = _find_section(data, "attractions", "景点推荐", "景点")
    if not attrs:
        return []

    elements = _section("景点推荐", styles)

    if isinstance(attrs, list):
        for a in attrs:
            if isinstance(a, dict):
                name = _get(a, "name", "景点名称") or ""
                desc = _get(a, "description", "简介", "介绍") or ""
                rating = _get(a, "rating", "评分") or ""
                price = _get(a, "ticket_price", "price", "门票") or ""
                hours = _get(a, "opening_hours", "开放时间") or ""
                duration = _get(a, "suggested_duration", "建议时长") or ""
                how_to = _get(a, "how_to_get_there", "交通") or ""
                tips = _get(a, "tips", "游览建议") or ""
                must_see = _get(a, "must_see", "必看") or ""

                title = f"• <b>{name}</b>"
                if rating:
                    title += f"  ⭐{rating}"
                elements.append(_pa(title, styles))
                if desc:
                    elements.append(_pa(f"  {desc}", styles, "small"))
                if price:
                    elements.append(_pa(f"  🎫 门票：{price}  |  🕐 {hours}  |  ⏱ 建议{hours if hours else duration}", styles, "small"))
                if how_to:
                    elements.append(_pa(f"  🚇 {how_to}", styles, "small"))
                if must_see:
                    elements.append(_pa(f"  ⭐ 必看：{must_see}", styles, "small"))
                if tips:
                    elements.append(_pa(f"  💡 {tips}", styles, "small"))
                elements.append(Spacer(1, 2 * mm))
            else:
                elements.append(_pa(f"• {a}", styles))

    return elements


# ── Section: Accommodation ────────────────────────────────────────────

def _build_hotel(data: dict, styles: dict) -> list:
    acc = _find_section(data, "accommodation", "hotel", "hotels", "住宿推荐", "住宿")
    if not acc:
        return []

    elements = _section("住宿推荐", styles)

    def _render_hotel_list(hotels, label):
        if not hotels:
            return
        elements.append(_pa(f"<b>{label}</b>", styles, "h2"))
        for h in hotels:
            if not isinstance(h, dict):
                elements.append(_pa(f"• {h}", styles))
                continue
            name = _get(h, "name", "酒店名称") or ""
            price = _get(h, "price_per_night", "price", "价格") or ""
            tier = _get(h, "tier") or ""
            loc = _get(h, "location", "位置") or ""
            nearby = _get(h, "nearby") or ""
            features = _get(h, "facilities", "设施") or ""
            rating = _get(h, "rating", "stars", "评分") or ""
            tips = _get(h, "tips") or ""
            breakfast = _get(h, "breakfast") or ""
            cancellation = _get(h, "cancellation") or ""
            pros = _get(h, "pros") or []
            cons = _get(h, "cons") or []

            line = f"• <b>{name}</b>"
            if tier:
                line += f"  [{tier}]"
            if rating:
                line += f"  ⭐{rating}"
            elements.append(_pa(line, styles))
            sub = []
            if price:
                sub.append(f"价格：{price}/晚")
            if loc:
                sub.append(f"位置：{loc}")
            if nearby:
                sub.append(f"周边：{nearby}")
            if sub:
                elements.append(_pa("  " + " | ".join(sub), styles, "small"))
            sub2 = []
            if breakfast:
                sub2.append(f"早餐：{breakfast}")
            if cancellation:
                sub2.append(f"取消：{cancellation}")
            if sub2:
                elements.append(_pa("  " + " | ".join(sub2), styles, "small"))
            if features:
                feat_text = features if isinstance(features, str) else "、".join(features)
                elements.append(_pa(f"  设施：{feat_text}", styles, "small"))
            if pros:
                elements.append(_pa(f"  👍 {'；'.join(pros)}", styles, "small"))
            if cons:
                elements.append(_pa(f"  👎 {'；'.join(cons)}", styles, "small"))
            if tips:
                elements.append(_pa(f"  💡 {tips}", styles, "small"))

    if isinstance(acc, dict):
        budget_opts = _get(acc, "budget_options", "经济型") or []
        mid_opts = _get(acc, "mid_range_options", "舒适型") or []
        luxury_opts = _get(acc, "luxury_options", "豪华型") or []
        all_opts = _get(acc, "options", "推荐列表") or []
        recommendation = _get(acc, "recommendation", "推荐") or ""

        if budget_opts:
            _render_hotel_list(budget_opts, "经济型")
        if mid_opts:
            _render_hotel_list(mid_opts, "舒适型")
        if luxury_opts:
            _render_hotel_list(luxury_opts, "豪华型")
        if all_opts:
            _render_hotel_list(all_opts, "推荐酒店")
        if recommendation:
            elements.append(Spacer(1, 2 * mm))
            elements.append(_pa(f"💡 推荐：{recommendation}", styles))
    elif isinstance(acc, list):
        _render_hotel_list(acc, "推荐酒店")
    elif isinstance(acc, str):
        elements.append(_pa(acc, styles))

    return elements


# ── Section: Weather ──────────────────────────────────────────────────

def _build_weather(data: dict, styles: dict) -> list:
    weather = _find_section(data, "weather", "天气情况", "天气")
    if not weather:
        return []

    elements = _section("天气情况", styles)

    if isinstance(weather, dict):
        forecast = _get(weather, "forecast", "预报")

        if forecast and isinstance(forecast, list):
            rows = [["日期", "天气", "温度", "湿度", "降水", "建议"]]
            for w in forecast:
                if isinstance(w, dict):
                    temp_min = w.get("temp_min", "")
                    temp_max = w.get("temp_max", "")
                    temp = f"{temp_min}°C ~ {temp_max}°C" if temp_min and temp_max else w.get("temp", "")
                    rain = w.get("rain_probability", "")
                    if rain:
                        rain = f"{rain}%"
                    rows.append([
                        w.get("date", ""),
                        w.get("condition", w.get("weather", "")),
                        temp,
                        str(w.get("humidity", "")) + "%" if w.get("humidity") else "",
                        rain,
                        w.get("clothing_advice", w.get("advice", "")),
                    ])
            elements.append(_table(rows, styles))

        # Handle forecast as string (test-prod: "由于数据源限制，无法提供...")
        elif forecast and isinstance(forecast, str):
            elements.append(_pa(forecast, styles))
            elements.append(Spacer(1, 2 * mm))

        # Suggestions array
        suggestions = _get(weather, "suggestions", "advice", "建议") or []
        if suggestions:
            if isinstance(suggestions, list):
                for s in suggestions:
                    elements.append(_pa(f"• {s}", styles))
            elif isinstance(suggestions, str):
                elements.append(_pa(f"💡 {suggestions}", styles))

        # General advice
        advice = _get(weather, "general_advice", "recommendation", "出行建议")
        if advice and advice != suggestions:
            elements.append(_pa(f"💡 {advice}", styles))

    elif isinstance(weather, list):
        if all(isinstance(w, str) for w in weather):
            for w in weather:
                elements.append(_pa(f"• {w}", styles))
        else:
            rows = [["日期", "天气", "温度", "建议"]]
            for w in weather:
                if isinstance(w, dict):
                    rows.append([
                        _get(w, "date", "日期") or "",
                        _get(w, "condition", "天气") or "",
                        _get(w, "temperature", "temp", "温度") or "",
                        _get(w, "advice", "建议") or "",
                    ])
            elements.append(_table(rows, styles))

    return elements


# ── Section: Daily Itinerary ──────────────────────────────────────────

def _build_schedule(data: dict, styles: dict) -> list:
    itin = _find_section(data, "daily_itinerary", "daily_schedule", "itinerary",
                         "每日行程", "行程安排", "schedule")
    if not itin:
        return []

    elements = _section("每日行程", styles)

    # LLM often outputs itinerary as dict with day1/day2/day3 keys
    if isinstance(itin, dict):
        # Sort day keys naturally (day1, day2, ...)
        day_keys = sorted(
            [k for k in itin if k.startswith("day") and isinstance(itin[k], dict)],
            key=lambda x: int("".join(filter(str.isdigit, x)) or 0)
        )
        for dk in day_keys:
            day = itin[dk]
            date = day.get("date", "")
            theme = day.get("theme", "")
            title = f"📅 {dk.upper()}：{date}  {theme}"
            elements.append(_pa(title, styles, "h2"))

            schedule = day.get("schedule", day.get("activities", day.get("活动", [])))
            if schedule:
                for act in schedule:
                    if isinstance(act, dict):
                        t = act.get("time", "")
                        a = act.get("activity", act.get("description", act.get("name", "")))
                        d = act.get("details", act.get("detail", act.get("note", "")))
                        line = f"<b>{t}</b>  {a}"
                        elements.append(_pa(line, styles))
                        if d:
                            elements.append(_pa(f"    {d}", styles, "small"))
                    else:
                        elements.append(_pa(f"• {act}", styles))

            attractions = day.get("attractions", day.get("sights", []))
            if attractions:
                elements.append(Spacer(1, 2 * mm))
                elements.append(_pa("<b>景点信息：</b>", styles))
                for attr in attractions:
                    if isinstance(attr, dict):
                        name = attr.get("name", "")
                        ticket = attr.get("ticket_price", attr.get("price", ""))
                        tip = attr.get("tips", "")
                        text = f"• {name}（门票：{ticket}）" if ticket else f"• {name}"
                        elements.append(_pa(text, styles))
                        if tip:
                            elements.append(_pa(f"    {tip}", styles, "small"))

            elements.append(Spacer(1, 3 * mm))

    # List format (if LLM outputs array)
    elif isinstance(itin, list):
        for i, day in enumerate(itin):
            if isinstance(day, dict):
                day_num = day.get("day", i + 1)
                date = day.get("date", "")
                theme = day.get("theme", "")
                # LLM may output "第1天" or a plain number; normalize
                if isinstance(day_num, int):
                    day_label = f"第{day_num}天"
                else:
                    day_label = str(day_num)
                title_parts = [f"📅 {day_label}"]
                if date:
                    title_parts.append(date)
                if theme:
                    title_parts.append(theme)
                elements.append(_pa("  ".join(title_parts), styles, "h2"))

                acts = day.get("schedule", day.get("activities", day.get("items", day.get("活动", []))))
                for act in acts:
                    if isinstance(act, dict):
                        t = act.get("time", act.get("时间", ""))
                        n = act.get("activity", act.get("name", act.get("description", act.get("活动名称", ""))))
                        note = act.get("note", act.get("detail", act.get("details", "")))
                        elements.append(_pa(f"<b>{t}</b>  {n}", styles))
                        if note:
                            elements.append(_pa(f"    {note}", styles, "small"))
                    else:
                        elements.append(_pa(f"• {act}", styles))
                elements.append(Spacer(1, 2 * mm))

    return elements


# ── Section: Food ─────────────────────────────────────────────────────

def _build_food(data: dict, styles: dict) -> list:
    food = _find_section(data, "food_recommendations", "food", "美食推荐", "美食",
                         "restaurants", "foods")
    if not food:
        return []

    elements = _section("美食推荐", styles)

    if isinstance(food, dict):
        # test-v2 style: local_specialties array
        specialties = (_get(food, "local_specialties", "specialties", "特色美食", "美食列表")
                       or [])
        # test-prod style: recommended_restaurants array
        restaurants = _get(food, "recommended_restaurants", "restaurants", "推荐餐厅") or []
        # Generic recommendations list
        recs = _get(food, "recommendations", "推荐") or []

        all_items = list(specialties) + list(restaurants) + list(recs)

        if all_items:
            for item in all_items:
                if isinstance(item, dict):
                    name = _get(item, "name", "名称", "美食名称") or ""
                    desc = _get(item, "description", "描述", "specialties") or ""
                    restaurant = _get(item, "recommended_restaurant", "where", "推荐餐厅",
                                       "address", "地址") or ""
                    price = _get(item, "price", "price_per_person", "价格") or ""
                    tips = _get(item, "tips", "提示") or ""

                    text = f"• <b>{name}</b>"
                    if price:
                        text += f"  人均 {price}"
                    if restaurant:
                        text += f"  — {restaurant}"
                    elements.append(_pa(text, styles))
                    if desc:
                        elements.append(_pa(f"    招牌：{desc}", styles, "small"))
                    if tips:
                        elements.append(_pa(f"    💡 {tips}", styles, "small"))
                else:
                    elements.append(_pa(f"• {item}", styles))

        # Budget tips for food
        tips = _get(food, "budget_tips", "tips", "建议")
        if tips:
            elements.append(Spacer(1, 2 * mm))
            elements.append(_pa(f"💰 {tips}", styles))

    elif isinstance(food, list):
        for item in food:
            if isinstance(item, dict):
                name = _get(item, "name", "名称") or ""
                desc = _get(item, "description", "描述", "specialties") or ""
                addr = _get(item, "address", "where", "地址") or ""
                text = f"• <b>{name}</b>"
                if addr:
                    text += f"  — {addr}"
                elements.append(_pa(text, styles))
                if desc:
                    elements.append(_pa(f"    {desc}", styles, "small"))
            else:
                elements.append(_pa(f"• {item}", styles))

    elif isinstance(food, str):
        elements.append(_pa(food, styles))

    return elements


# ── Section: Food Specialties ─────────────────────────────────────────

def _build_food_specialties(data: dict, styles: dict) -> list:
    specialties = _find_section(data, "food_specialties", "特色美食", "当地美食", "specialties")
    if not specialties:
        return []

    elements = _section("当地特色美食", styles)

    if isinstance(specialties, list):
        for item in specialties:
            if isinstance(item, dict):
                name = _get(item, "name", "美食名称") or ""
                desc = _get(item, "description", "介绍") or ""
                where = _get(item, "where_to_try", "推荐品尝地") or ""
                price = _get(item, "price_range", "价格") or ""

                text = f"• <b>{name}</b>"
                if price:
                    text += f"  {price}"
                elements.append(_pa(text, styles))
                if desc:
                    elements.append(_pa(f"  {desc}", styles, "small"))
                if where:
                    elements.append(_pa(f"  📍 {where}", styles, "small"))
                elements.append(Spacer(1, 1 * mm))
            else:
                elements.append(_pa(f"• {item}", styles))

    return elements


# ── Section: Shopping ─────────────────────────────────────────────────

def _build_shopping(data: dict, styles: dict) -> list:
    shopping = data.get("shopping", {})
    if not shopping or not isinstance(shopping, dict):
        return []

    elements = _section("购物指南", styles)

    specialties = shopping.get("specialties", [])
    if specialties:
        elements.append(_pa("<b>当地特产：</b>" + "、".join(specialties), styles))
        elements.append(Spacer(1, 2 * mm))

    areas = shopping.get("shopping_areas", [])
    if areas:
        elements.append(_pa("<b>购物商圈：</b>", styles))
        for area in areas:
            if isinstance(area, dict):
                name = area.get("name", "")
                desc = area.get("description", "")
                buy = area.get("what_to_buy", "")
                text = f"• <b>{name}</b>"
                if desc:
                    text += f" — {desc}"
                elements.append(_pa(text, styles))
                if buy:
                    elements.append(_pa(f"  可买：{buy}", styles, "small"))
            else:
                elements.append(_pa(f"• {area}", styles))

    tips = shopping.get("souvenir_tips")
    if tips:
        elements.append(Spacer(1, 2 * mm))
        elements.append(_pa(f"💡 {tips}", styles))

    return elements


# ── Section: Tips & Budget ────────────────────────────────────────────

def _build_tips(data: dict, styles: dict) -> list:
    tips = _find_section(data, "travel_tips", "tips", "出行贴士", "贴士", "notes")
    elements = []

    if tips:
        elements = _section("出行贴士", styles)
        if isinstance(tips, dict):
            for k, v in tips.items():
                label = str(k).replace("_", " ").title()
                if isinstance(v, list):
                    # Render list values as sub-bullets
                    elements.append(_pa(f"• <b>{label}</b>：", styles))
                    for item in v:
                        elements.append(_pa(f"    - {item}", styles, "small"))
                elif isinstance(v, str):
                    elements.append(_pa(f"• <b>{label}</b>：{v}", styles))
                else:
                    elements.append(_pa(f"• <b>{label}</b>：{v}", styles))
        elif isinstance(tips, list):
            for t in tips:
                if isinstance(t, str):
                    elements.append(_pa(f"• {t}", styles))
                elif isinstance(t, dict):
                    for k, v in t.items():
                        elements.append(_pa(f"• <b>{k}</b>：{v}", styles))
        elif isinstance(tips, str):
            for line in tips.split("\n"):
                line = line.strip()
                if line:
                    elements.append(_pa(f"• {line}", styles))

    # Budget — check both top-level and inside trip_overview
    budget = (data.get("budget_breakdown") or data.get("预算明细") or data.get("费用明细")
              or _get(data.get("trip_overview", {}), "budget_breakdown", "预算明细")
              or _get(data, "budget_estimate"))
    if budget:
        if not elements:
            elements = []
        elements.append(Spacer(1, 4 * mm))
        elements.append(_pa("<b>预算预估</b>", styles, "h2"))
        if isinstance(budget, dict):
            rows = [["项目", "预估费用"]]
            total = 0
            for k, v in budget.items():
                rows.append([str(k), str(v)])
                try:
                    val = float(str(v).replace("元", "").replace("¥", "").replace(",", "").replace("约", "").strip())
                    total += val
                except ValueError:
                    pass
            if total > 0:
                rows.append(["合计", f"约 {total:.0f} 元"])
            elements.append(_table(rows, styles, col_widths=[100 * mm, 60 * mm]))
        elif isinstance(budget, str):
            elements.append(_pa(budget, styles))
        elif isinstance(budget, list):
            for b in budget:
                if isinstance(b, dict):
                    elements.append(_pa(
                        f"• {b.get('category', b.get('项目', ''))}：{b.get('amount', b.get('费用', ''))}", styles))

    return elements


# ── Section: Cover Page ────────────────────────────────────────────────

def _build_cover(data: dict, styles: dict, font_name: str) -> list:
    """Build a styled cover page with destination title and trip summary."""
    overview = data.get("overview") or data.get("trip_overview") or {}
    dest = _get(overview, "destination", "目的地") or _get(data, "destination") or "旅行攻略"
    dep_city = _get(overview, "departure_city", "departure", "出发城市") or ""
    dates = _get(overview, "travel_dates", "dates", "日期") or ""
    duration = _get(overview, "duration") or ""
    budget = _get(overview, "total_budget") or ""
    highlights = _get(overview, "highlights") or []

    if not budget:
        budget_est = data.get("budget_estimate") or {}
        if isinstance(budget_est, dict):
            budget = budget_est.get("total", "")

    elements = []

    # Top colored banner
    banner = Table([[""]], colWidths=[160 * mm], rowHeights=[16 * mm])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
        ("LINEBELOW", (0, 0), (-1, -1), 0, white),
    ]))
    elements.append(banner)
    elements.append(Spacer(1, 14 * mm))

    # Destination title
    cover_title = ParagraphStyle(
        "CoverTitle", fontName=font_name, fontSize=30, leading=38,
        alignment=TA_CENTER, textColor=DARK,
    )
    elements.append(Paragraph(_strip_emoji(dest), cover_title))
    elements.append(Spacer(1, 5 * mm))

    # Subtitle line
    sub_parts = []
    if dep_city:
        sub_parts.append(f"{dep_city}出发")
    if dates:
        sub_parts.append(dates)
    if duration:
        sub_parts.append(duration)
    elements.append(_pa("  ·  ".join(sub_parts) if sub_parts else "AI 智能规划", styles, "subtitle"))
    elements.append(Spacer(1, 6 * mm))

    # Decorative divider
    elements.append(HRFlowable(width="50%", thickness=2, color=PRIMARY, spaceAfter=6 * mm))

    # Quick stats
    if budget:
        elements.append(_pa(f"预估预算：{budget}元", styles, "subtitle"))

    if highlights:
        elements.append(Spacer(1, 6 * mm))
        elements.append(_pa("<b>行程亮点</b>", styles, "h2"))
        for h in highlights if isinstance(highlights, list) else [highlights]:
            elements.append(_pa(f"  *  {h}", styles))

    elements.append(PageBreak())
    return elements


# ── Section: Destination Map ───────────────────────────────────────────

def _build_destination_map(data: dict, styles: dict) -> list:
    """Build a static map showing attraction and hotel locations via Amap API."""
    overview = data.get("overview") or data.get("trip_overview") or {}
    dest = _get(overview, "destination", "目的地") or ""
    if not dest:
        return []

    # Collect locations to plot
    locations = []  # list of (display_name, address_for_geocoding)

    # Attractions
    attrs = data.get("attractions") or []
    if isinstance(attrs, list):
        for a in attrs:
            if isinstance(a, dict):
                name = _get(a, "name", "景点名称") or ""
                addr = _get(a, "address") or _get(a, "how_to_get_there") or ""
                if name:
                    locations.append((name, addr or f"{dest}{name}"))

    # Hotels
    hotels = data.get("hotels") or data.get("accommodation") or []
    hotel_list = []
    if isinstance(hotels, list):
        hotel_list = hotels
    elif isinstance(hotels, dict):
        for k in ["options", "budget_options", "mid_range_options", "luxury_options"]:
            opts = hotels.get(k) or []
            if isinstance(opts, list):
                hotel_list.extend(opts)
    for h in hotel_list:
        if isinstance(h, dict):
            name = _get(h, "name", "酒店名称") or ""
            loc = _get(h, "location") or _get(h, "地址") or ""
            if name:
                locations.append((name, loc or f"{dest}{name}"))

    if len(locations) < 1:
        return []

    # Geocode destination center
    center = _geocode_sync(dest)
    if not center:
        return []

    # Geocode each location (limit to avoid excessive API calls)
    markers = []
    for name, search in locations[:12]:
        coord = _geocode_sync(search, dest)
        if coord:
            label = name[:10]
            markers.append((coord[0], coord[1], label))

    if len(markers) < 2:
        return []  # Need at least 2 markers for a meaningful map

    # Zoom based on mark count
    zoom = 11 if len(markers) >= 6 else 12 if len(markers) >= 3 else 13

    # Fetch map image
    img_data = _fetch_static_map(center, markers, zoom=zoom)
    if not img_data:
        return []

    elements = _section("目的地导览图", styles)
    img = Image(img_data, width=160 * mm, height=94 * mm)
    elements.append(img)
    elements.append(Spacer(1, 3 * mm))

    # Legend
    legend_rows = [["标记", "地点"]]
    for i, (_lng, _lat, label) in enumerate(markers):
        letter = chr(ord('A') + i) if i < 26 else str(i)
        legend_rows.append([f" {letter} ", label])
    if len(legend_rows) > 1:
        elements.append(_table(legend_rows, styles, col_widths=[14 * mm, 146 * mm]))

    return elements


# ── Fallback: raw tool results when LLM structured output is unavailable ─

SECTION_LABELS = {
    "transport": "交通查询结果", "weather": "天气查询结果",
    "hotel": "酒店查询结果", "search": "搜索查询结果",
    "maps": "地图查询结果", "file": "文件生成结果",
}


def _build_fallback_sections(sections: dict, note: str, styles: dict) -> list:
    """Render raw tool-result sections when the LLM failed to produce structured data."""
    elements = []
    if note:
        elements.append(_pa(f"[注意] {note}", styles))
        elements.append(Spacer(1, 4 * mm))

    for sec_name, results in sections.items():
        if not results:
            continue
        label = SECTION_LABELS.get(sec_name, sec_name)
        elements.extend(_section(label, styles))

        for r in results:
            desc = r.get("description", "") if isinstance(r, dict) else str(r)
            data_str = r.get("data", "") if isinstance(r, dict) else ""
            complete = r.get("complete", False) if isinstance(r, dict) else False
            status = "[完成]" if complete else "[未完成]"
            elements.append(_pa(f"<b>{status} {desc}</b>", styles))
            if data_str and isinstance(data_str, str):
                if len(data_str) > 800:
                    data_str = data_str[:800] + "..."
                elements.append(_pa(data_str, styles, "small"))
            elements.append(Spacer(1, 2 * mm))

    return elements


# ── Main ──────────────────────────────────────────────────────────────

def _flatten(data: dict) -> dict:
    """If the itinerary has sections nested under 'sections', flatten them."""
    if "sections" in data and isinstance(data["sections"], dict):
        merged = {**data}
        merged.update(data["sections"])
        return merged
    return data


async def generate_pdf(itinerary: Dict[str, Any], thread_id: str = "") -> BytesIO:
    font_name = _get_font_name()
    styles = _build_styles(font_name)
    data = _flatten(itinerary)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="旅行攻略" if font_name != "Helvetica" else "Travel Itinerary",
        author="AI 旅游规划助手",
    )

    elements = []

    # ── Cover Page ──
    try:
        elements.extend(_build_cover(data, styles, font_name))
    except Exception:
        logger.warning("Cover page generation failed, skipping", exc_info=True)

    # ── Title (not on its own page, follows cover) ──
    overview = _find_section(data, "trip_overview", "overview", "行程概览")
    dest = _get(overview or data, "destination", "目的地") or ""
    title = f"{dest}旅行攻略" if dest else "旅行攻略"
    elements.append(_pa(title, styles, "title"))

    subtitle_parts = []
    dep_city = _get(overview or data, "departure_city", "departure", "出发城市") or ""
    dates = _get(overview or data, "travel_dates", "dates", "日期") or ""
    gen_at = _get(data, "generated_at", "生成时间") or ""
    if dep_city:
        subtitle_parts.append(f"出发：{dep_city}")
    if dates:
        subtitle_parts.append(f"日期：{dates}")
    if gen_at:
        subtitle_parts.append(f"生成：{gen_at}")
    elements.append(_pa("  |  ".join(subtitle_parts) if subtitle_parts else "AI 智能规划", styles, "subtitle"))

    # ── Destination Map (attractions + hotels on Amap static map) ──
    try:
        map_section = _build_destination_map(data, styles)
        if map_section:
            elements.extend(map_section)
    except Exception:
        logger.warning("Destination map generation failed, skipping", exc_info=True)

    # Sections — each isolated so one bad section can't kill the whole PDF
    _section_builders = [
        (_build_overview, "overview"),
        (_build_transport, "transport"),
        (_build_city_transport, "city_transport"),
        (_build_weather, "weather"),
        (_build_attractions, "attractions"),
        (_build_hotel, "hotel"),
        (_build_schedule, "schedule"),
        (_build_food_specialties, "food_specialties"),
        (_build_food, "food"),
        (_build_shopping, "shopping"),
        (_build_tips, "tips"),
    ]
    rendered_any = False
    for _builder, _name in _section_builders:
        try:
            result = _builder(data, styles)
            if result:
                rendered_any = True
                elements.extend(result)
        except Exception:
            logger.warning(f"PDF section '{_name}' render failed, skipping", exc_info=True)

    # Fallback: if no structured section produced content, try raw tool results
    if not rendered_any:
        raw_sections = data.get("sections", {})
        if raw_sections:
            elements.extend(_build_fallback_sections(
                raw_sections, data.get("note", ""), styles))
    elements.append(Spacer(1, 10 * mm))

    # Footer
    elements.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=3 * mm))
    elements.append(_pa("本攻略由 AI 旅游规划助手自动生成，信息仅供参考，请以实际情况为准。", styles, "small"))

    doc.build(elements)
    buffer.seek(0)
    return buffer

"""
和风天气 API 封装。

提供:
  - get_weather(city) → dict

使用 HeWeather v7 API，返回当天天气概况。
"""

import logging
from typing import Any, Dict, Optional

import httpx

from app.config import config

logger = logging.getLogger("weather")


async def get_weather(city: Optional[str] = None) -> Dict[str, Any]:
    """
    获取指定城市的当天天气。

    参数:
        city: 城市名。为 None 时从 system_config.city 读取。

    返回:
        {
            "city": "深圳",
            "temp": "28",
            "text": "晴",
            "humidity": "65",
            "wind_dir": "东南风",
            "is_extreme": False,   # 是否极端天气（雨/雪/大风等）
            "raw": {...}
        }

        调用失败时返回 {"error": "..."}
    """
    if not config.heweather_api_key:
        return {"error": "未配置 HEWEATHER_API_KEY"}

    target_city = city or ""
    if not target_city:
        # 从 system_config 读
        from app.harness.l2_tools.system_tools import get_system_config
        sys_config = await get_system_config("city")
        target_city = sys_config.get("city", "")
        if not target_city:
            return {"error": "未配置城市，请先设置城市（/city 命令）"}

    try:
        # 1. 先获取城市 ID
        async with httpx.AsyncClient(timeout=10) as client:
            city_resp = await client.get(
                f"{config.heweather_base_url}/city/lookup",
                params={
                    "location": target_city,
                    "key": config.heweather_api_key,
                },
            )
            city_resp.raise_for_status()
            city_data = city_resp.json()

        if city_data.get("code") != "200" or not city_data.get("location"):
            return {"error": f"未找到城市: {target_city}"}

        location_id = city_data["location"][0]["id"]

        # 2. 获取天气
        async with httpx.AsyncClient(timeout=10) as client:
            weather_resp = await client.get(
                f"{config.heweather_base_url}/weather/now",
                params={
                    "location": location_id,
                    "key": config.heweather_api_key,
                },
            )
            weather_resp.raise_for_status()
            weather_data = weather_resp.json()

        if weather_data.get("code") != "200":
            return {"error": f"天气查询失败: {weather_data.get('code')}"}

        now = weather_data["now"]
        text = now.get("text", "")

        # 判断极端天气
        extreme_keywords = ["雨", "雪", "暴", "沙", "霾", "冰雹", "大风", "台风"]
        is_extreme = any(kw in text for kw in extreme_keywords)

        return {
            "city": target_city,
            "temp": now.get("temp", ""),
            "text": text,
            "humidity": now.get("humidity", ""),
            "wind_dir": now.get("windDir", ""),
            "is_extreme": is_extreme,
            "raw": now,
        }

    except httpx.HTTPError as e:
        logger.error(f"天气 API 调用失败: {e}")
        return {"error": f"天气服务暂时不可用: {e}"}

"""
天气工具 — L2 标准工具包装层。

将 services/weather.py 包装为工具函数，统一走 Pydantic schema 校验。
所有 Agent 通过工具白名单调用此函数，而非直接调 service。
"""

import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("l2_tools.weather")


class GetWeatherInput(BaseModel):
    city: Optional[str] = Field(None, description="城市名，为空则从 system_config 读取")


async def get_weather(city: Optional[str] = None) -> Dict[str, Any]:
    """
    获取指定城市的当天天气。

    L2 工具层标准包装，内部调用 services/weather.py。
    返回格式见 PRD 五节：{city, temp, text, humidity, wind_dir, is_extreme, raw}
    """
    try:
        from app.services.weather import get_weather as _svc_get_weather
        result = await _svc_get_weather(city)
        logger.info(f"天气查询: city={city or 'system_config'}")
        return result
    except Exception as e:
        logger.error(f"天气工具调用失败: {e}")
        return {"error": str(e)}

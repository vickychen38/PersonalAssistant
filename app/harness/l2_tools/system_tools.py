"""
系统配置工具 — 读写 system_config 表。

提供:
  - get_system_config(key=None) → dict | str
  - update_system_config(key, value) → dict
"""

import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.database import async_session_factory

logger = logging.getLogger("system_tools")

# ---- Pydantic Schemas ----

class GetSystemConfigInput(BaseModel):
    key: Optional[str] = None

class UpdateSystemConfigInput(BaseModel):
    key: str = Field(..., min_length=1, max_length=100)
    value: str


# ---- Tool Functions ----

async def get_system_config(key: Optional[str] = None) -> Dict[str, str]:
    """
    读取系统配置。

    参数:
        key: 配置键名。为 None 时返回全部配置。

    返回:
        {"key": "value", ...} 或 {"key": "value"}（单个）
    """
    async with async_session_factory() as session:
        if key:
            result = await session.execute(
                text("SELECT key, value FROM system_config WHERE key = :key"),
                {"key": key},
            )
            row = result.fetchone()
            if row is None:
                return {}
            return {row[0]: row[1]}
        else:
            result = await session.execute(
                text("SELECT key, value FROM system_config")
            )
            return {row[0]: row[1] for row in result.fetchall()}


async def update_system_config(key: str, value: str) -> Dict[str, Any]:
    """
    更新系统配置。

    参数:
        key: 配置键名
        value: 新值

    返回:
        {"key": key, "value": value, "updated": True}
    """
    async with async_session_factory() as session:
        await session.execute(
            text("""
                INSERT INTO system_config (key, value, updated_at)
                VALUES (:key, :value, NOW())
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value,
                    updated_at = NOW()
            """),
            {"key": key, "value": value},
        )
        await session.commit()
        logger.info(f"system_config 已更新: {key} = {value}")
        return {"key": key, "value": value, "updated": True}

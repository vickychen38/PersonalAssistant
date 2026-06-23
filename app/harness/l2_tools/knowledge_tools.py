"""
用户知识库工具 — 读写 user_knowledge 表。

提供:
  - get_user_knowledge(category=None)
  - upsert_user_knowledge(category, key, value, source_context=None)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.database import async_session_factory

logger = logging.getLogger("knowledge_tools")


# ---- Pydantic Schemas ----

class GetUserKnowledgeInput(BaseModel):
    category: Optional[str] = None

class UpsertUserKnowledgeInput(BaseModel):
    category: str = Field(..., min_length=1, max_length=100)
    key: str = Field(..., min_length=1, max_length=200)
    value: str = Field(..., min_length=1)
    source_context: Optional[str] = None


# ---- Tool Functions ----

async def get_user_knowledge(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    查询用户知识库。

    参数:
        category: 知识分类。为 None 时返回全部。

    返回:
        [{"id": 1, "category": "...", "key": "...", "value": "...", ...}, ...]
    """
    async with async_session_factory() as session:
        if category:
            result = await session.execute(
                text(
                    "SELECT id, category, key, value, source_context, "
                    "created_at, updated_at FROM user_knowledge "
                    "WHERE category = :category ORDER BY key"
                ),
                {"category": category},
            )
        else:
            result = await session.execute(
                text(
                    "SELECT id, category, key, value, source_context, "
                    "created_at, updated_at FROM user_knowledge ORDER BY category, key"
                ),
            )

        rows = result.fetchall()
        return [
            {
                "id": row[0],
                "category": row[1],
                "key": row[2],
                "value": row[3],
                "source_context": row[4],
                "created_at": str(row[5]),
                "updated_at": str(row[6]),
            }
            for row in rows
        ]


async def upsert_user_knowledge(
    category: str,
    key: str,
    value: str,
    source_context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    新增或更新用户知识。

    规则（见 PRD 第十节）：
      1. 不存在 → INSERT，返回 {"action": "created", ...}
      2. 存在且内容相同 → 不操作，返回 {"action": "unchanged", ...}
      3. 存在但内容不同 → UPDATE，返回 {"action": "updated", "old_value": ...}
      4. 明显矛盾 → 上层应在调用前确认，本函数只做静默更新

    返回:
        {"action": "created"|"unchanged"|"updated", "category": ..., ...}
    """
    async with async_session_factory() as session:
        # 先查是否存在
        result = await session.execute(
            text(
                "SELECT id, value FROM user_knowledge "
                "WHERE category = :category AND key = :key"
            ),
            {"category": category, "key": key},
        )
        existing = result.fetchone()

        if existing is None:
            # 不存在 → INSERT
            await session.execute(
                text(
                    "INSERT INTO user_knowledge (category, key, value, source_context) "
                    "VALUES (:category, :key, :value, :source_context)"
                ),
                {
                    "category": category,
                    "key": key,
                    "value": value,
                    "source_context": source_context,
                },
            )
            await session.commit()
            logger.info(f"user_knowledge 已创建: {category}/{key}")
            return {
                "action": "created",
                "category": category,
                "key": key,
                "value": value,
            }

        # 已存在
        old_value = existing[1]
        if old_value == value:
            # 内容相同 → 不操作
            return {
                "action": "unchanged",
                "category": category,
                "key": key,
                "value": value,
            }

        # 内容不同 → UPDATE
        await session.execute(
            text(
                "UPDATE user_knowledge SET value = :value, "
                "source_context = COALESCE(:source_context, source_context), "
                "updated_at = NOW() "
                "WHERE category = :category AND key = :key"
            ),
            {
                "category": category,
                "key": key,
                "value": value,
                "source_context": source_context,
            },
        )
        await session.commit()
        logger.info(f"user_knowledge 已更新: {category}/{key}")
        return {
            "action": "updated",
            "category": category,
            "key": key,
            "old_value": old_value,
            "value": value,
        }

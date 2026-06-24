"""
复盘 + 情绪工具集 — Retrospective Agent 的工具函数。

包含：
  - 情绪状态读写（daily_state）
  - 复盘 CRUD
  - Agent 操作日志查询
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.database import async_session_factory

logger = logging.getLogger("retrospective_tools")


def _parse_date(val: str | date | None) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    return date.fromisoformat(val)


# ---- Pydantic Schemas ----

class UpsertDailyStateInput(BaseModel):
    date: Optional[str] = None
    emotion_tags: Optional[List[str]] = None
    emotion_notes: Optional[str] = None
    energy_level: Optional[int] = Field(None, ge=1, le=5)

class CreateRetrospectiveInput(BaseModel):
    date: str
    type: str = Field(..., pattern="^(daily|weekly|monthly)$")
    content: str
    completion_rate: Optional[float] = None
    emotion_summary: Optional[List[str]] = None
    key_insights: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# ---- Read Tools ----

async def get_daily_state(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """查询情绪状态。默认近 7 天。"""
    if start_date is None:
        start_date = date.today().replace(day=1).isoformat()
    if end_date is None:
        end_date = date.today().isoformat()

    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                SELECT id, date, emotion_tags, emotion_notes, energy_level, created_at
                FROM daily_state
                WHERE date BETWEEN :start AND :end
                ORDER BY date
            """),
            {"start": _parse_date(start_date), "end": _parse_date(end_date)},
        )
        return [
            {
                "id": r[0],
                "date": str(r[1]),
                "emotion_tags": r[2] or [],
                "emotion_notes": r[3],
                "energy_level": r[4],
                "created_at": str(r[5]),
            }
            for r in result.fetchall()
        ]


async def get_retrospectives(
    retro_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """查询复盘记录。"""
    conditions = []
    params: dict = {}

    if retro_type:
        conditions.append("type = :rtype")
        params["rtype"] = retro_type
    if start_date:
        conditions.append("date >= :start")
        params["start"] = _parse_date(start_date)
    if end_date:
        conditions.append("date <= :end")
        params["end"] = _parse_date(end_date)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    async with async_session_factory() as session:
        result = await session.execute(
            text(f"""
                SELECT id, date, type, content, completion_rate,
                       emotion_summary, key_insights, metadata, created_at
                FROM retrospectives
                {where}
                ORDER BY date DESC, type
            """),
            params,
        )
        return [
            {
                "id": r[0],
                "date": str(r[1]),
                "type": r[2],
                "content": r[3],
                "completion_rate": float(r[4]) if r[4] else None,
                "emotion_summary": r[5] or [],
                "key_insights": r[6],
                "metadata": r[7] or {},
                "created_at": str(r[8]),
            }
            for r in result.fetchall()
        ]


# get_recent_agent_actions 已迁移至 harness/l2_tools/observation_tools.py
from app.harness.l2_tools.observation_tools import get_recent_agent_actions  # noqa: F401

# ---- Write Tools ----

async def upsert_daily_state(data: UpsertDailyStateInput) -> Dict[str, Any]:
    """写入或更新当日情绪状态。"""
    target_date = _parse_date(data.date) if data.date else date.today()

    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT id FROM daily_state WHERE date = :d"),
            {"d": target_date},
        )
        existing = result.fetchone()

        if existing:
            # UPDATE
            set_parts = []
            params: dict = {"id": existing[0]}
            if data.emotion_tags is not None:
                set_parts.append("emotion_tags = :tags")
                params["tags"] = data.emotion_tags
            if data.emotion_notes is not None:
                set_parts.append("emotion_notes = :notes")
                params["notes"] = data.emotion_notes
            if data.energy_level is not None:
                set_parts.append("energy_level = :energy")
                params["energy"] = data.energy_level

            if set_parts:
                await session.execute(
                    text(f"UPDATE daily_state SET {', '.join(set_parts)} WHERE id = :id"),
                    params,
                )
                await session.commit()
            return {"action": "updated", "date": target_date.isoformat()}
        else:
            # INSERT
            await session.execute(
                text("""
                    INSERT INTO daily_state (date, emotion_tags, emotion_notes, energy_level)
                    VALUES (:date, :tags, :notes, :energy)
                """),
                {
                    "date": target_date,
                    "tags": data.emotion_tags or [],
                    "notes": data.emotion_notes,
                    "energy": data.energy_level,
                },
            )
            await session.commit()
            return {"action": "created", "date": target_date.isoformat()}


async def create_retrospective(data: CreateRetrospectiveInput) -> Dict[str, Any]:
    """创建复盘记录。"""
    import json as _json
    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                INSERT INTO retrospectives
                    (date, type, content, completion_rate, emotion_summary,
                     key_insights, metadata)
                VALUES (:date, :type, :content, :completion_rate,
                        :emotion_summary, :key_insights, CAST(:metadata AS jsonb))
                ON CONFLICT (date, type) DO UPDATE
                SET content = EXCLUDED.content,
                    completion_rate = EXCLUDED.completion_rate,
                    emotion_summary = EXCLUDED.emotion_summary,
                    key_insights = EXCLUDED.key_insights,
                    metadata = EXCLUDED.metadata
                RETURNING id
            """),
            {
                "date": _parse_date(data.date),
                "type": data.type,
                "content": data.content,
                "completion_rate": data.completion_rate,
                "emotion_summary": data.emotion_summary or [],
                "key_insights": data.key_insights,
                "metadata": _json.dumps(data.metadata or {}, ensure_ascii=False),
            },
        )
        new_id = result.scalar()
        await session.commit()
        logger.info(f"复盘已创建: id={new_id} type={data.type} date={data.date}")
        return {"id": new_id, "type": data.type, "date": data.date}

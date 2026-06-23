"""
健康工具集 — Health Agent 的工具函数。
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.database import async_session_factory
from app.config import config

logger = logging.getLogger("health_tools")


# ---- Helpers ----

def _parse_date(val: str | date | None) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    return date.fromisoformat(val)


def _calc_bmi(weight: float) -> float:
    """BMI = weight / ((height_cm / 100) ** 2)，保留 1 位小数。"""
    return round(weight / ((config.user_height_cm / 100) ** 2), 1)


# ---- Pydantic Schemas ----

class RecordHealthDailyInput(BaseModel):
    date: Optional[str] = None  # YYYY-MM-DD，默认今天
    weight: Optional[float] = None
    body_fat_pct: Optional[float] = None

class RecordBodyMeasurementsInput(BaseModel):
    shoulder: Optional[float] = None
    chest: Optional[float] = None
    upper_arm: Optional[float] = None
    waist: Optional[float] = None
    hip: Optional[float] = None
    thigh: Optional[float] = None
    calf: Optional[float] = None
    notes: Optional[str] = None


# ---- Read Tools ----

async def get_health_daily(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """查询指定日期范围的每日健康数据。默认近 30 天。"""
    if start_date is None:
        start_date = date.today().replace(day=1).isoformat()
    if end_date is None:
        end_date = date.today().isoformat()

    sd = _parse_date(start_date)
    ed = _parse_date(end_date)

    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                SELECT id, date, weight, body_fat_pct, bmi, recorded_at
                FROM health_daily
                WHERE date BETWEEN :start AND :end
                ORDER BY date
            """),
            {"start": sd, "end": ed},
        )
        return [
            {
                "id": r[0],
                "date": str(r[1]),
                "weight": float(r[2]) if r[2] else None,
                "body_fat_pct": float(r[3]) if r[3] else None,
                "bmi": float(r[4]) if r[4] else None,
                "recorded_at": str(r[5]),
            }
            for r in result.fetchall()
        ]


async def get_body_measurements(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """查询围度记录。默认近 10 次。"""
    sd = _parse_date(start_date) if start_date else None
    ed = _parse_date(end_date) if end_date else None

    async with async_session_factory() as session:
        if sd and ed:
            result = await session.execute(
                text("""
                    SELECT * FROM body_measurements
                    WHERE recorded_at BETWEEN :start AND :end
                    ORDER BY recorded_at DESC
                """),
                {"start": sd, "end": ed},
            )
        else:
            result = await session.execute(
                text("SELECT * FROM body_measurements ORDER BY recorded_at DESC LIMIT 10")
            )
        rows = result.fetchall()
        return [
            {
                "id": r[0],
                "recorded_at": str(r[1]),
                "shoulder": float(r[2]) if r[2] else None,
                "chest": float(r[3]) if r[3] else None,
                "upper_arm": float(r[4]) if r[4] else None,
                "waist": float(r[5]) if r[5] else None,
                "hip": float(r[6]) if r[6] else None,
                "thigh": float(r[7]) if r[7] else None,
                "calf": float(r[8]) if r[8] else None,
                "notes": r[9],
            }
            for r in rows
        ]


# ---- Write Tools ----

async def record_health_daily(data: RecordHealthDailyInput) -> Dict[str, Any]:
    """记录体重/体脂。自动计算 BMI。有今日记录则 UPDATE，无则 INSERT。"""
    target_date = _parse_date(data.date) if data.date else date.today()

    if data.weight is None and data.body_fat_pct is None:
        return {"error": "至少需要提供 weight 或 body_fat_pct"}

    bmi = _calc_bmi(data.weight) if data.weight else None

    async with async_session_factory() as session:
        # 检查今天是否已有记录
        result = await session.execute(
            text("SELECT id, weight, body_fat_pct FROM health_daily WHERE date = :d"),
            {"d": target_date},
        )
        existing = result.fetchone()

        if existing:
            # UPDATE — 只更新本次提供的字段
            new_weight = data.weight if data.weight is not None else (
                float(existing[1]) if existing[1] else None
            )
            new_bmi = _calc_bmi(new_weight) if new_weight else (
                float(existing[2]) if existing[2] else None
            )
            await session.execute(
                text("""
                    UPDATE health_daily
                    SET weight = COALESCE(:weight, weight),
                        body_fat_pct = COALESCE(:body_fat_pct, body_fat_pct),
                        bmi = :bmi
                    WHERE id = :id
                """),
                {
                    "weight": data.weight,
                    "body_fat_pct": data.body_fat_pct,
                    "bmi": bmi,
                    "id": existing[0],
                },
            )
            await session.commit()
            return {
                "action": "updated",
                "date": target_date.isoformat(),
                "weight": data.weight,
                "body_fat_pct": data.body_fat_pct,
                "bmi": bmi,
            }
        else:
            # INSERT
            await session.execute(
                text("""
                    INSERT INTO health_daily (date, weight, body_fat_pct, bmi)
                    VALUES (:date, :weight, :body_fat_pct, :bmi)
                """),
                {
                    "date": target_date,
                    "weight": data.weight,
                    "body_fat_pct": data.body_fat_pct,
                    "bmi": bmi,
                },
            )
            await session.commit()
            return {
                "action": "created",
                "date": target_date.isoformat(),
                "weight": data.weight,
                "body_fat_pct": data.body_fat_pct,
                "bmi": bmi,
            }


async def record_body_measurements(data: RecordBodyMeasurementsInput) -> Dict[str, Any]:
    """记录围度数据。只写入用户提供的部位。"""
    fields = {
        "shoulder": data.shoulder,
        "chest": data.chest,
        "upper_arm": data.upper_arm,
        "waist": data.waist,
        "hip": data.hip,
        "thigh": data.thigh,
        "calf": data.calf,
        "notes": data.notes,
    }
    provided = {k: v for k, v in fields.items() if v is not None}
    if not provided:
        return {"error": "至少需要提供一个部位的围度数据"}

    columns = ", ".join(provided.keys())
    placeholders = ", ".join(f":{k}" for k in provided)

    async with async_session_factory() as session:
        result = await session.execute(
            text(f"INSERT INTO body_measurements ({columns}) VALUES ({placeholders}) RETURNING id"),
            provided,
        )
        new_id = result.scalar()
        await session.commit()
        logger.info(f"围度已记录: id={new_id}")
        return {"id": new_id, "recorded": list(provided.keys())}

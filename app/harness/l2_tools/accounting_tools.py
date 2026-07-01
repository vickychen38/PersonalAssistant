"""
记账工具集 — Accounting Agent 的工具函数。
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.database import async_session_factory

logger = logging.getLogger("accounting_tools")


# ---- Pydantic Schemas ----

class CreateAccountingEntryInput(BaseModel):
    amount: float
    category_id: Optional[int] = None
    description: Optional[str] = None
    source: str = "text"

class CreateBudgetCategoryInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    monthly_budget: Optional[float] = None
    alert_threshold: Optional[float] = 0.80

class UpdateBudgetCategoryInput(BaseModel):
    id: int
    monthly_budget: Optional[float] = None
    alert_threshold: Optional[float] = None


# ---- Read Tools ----

async def get_accounting_summary(month: Optional[str] = None) -> Dict[str, Any]:
    """查询指定月份的记账汇总。month 默认当前月 (YYYY-MM)。"""
    if month is None:
        today = date.today()
        month = today.strftime("%Y-%m")

    async with async_session_factory() as session:
        # 按类目汇总
        result = await session.execute(
            text("""
                SELECT bc.id, bc.name, bc.monthly_budget,
                       COALESCE(SUM(a.amount), 0) AS spent
                FROM budget_categories bc
                LEFT JOIN accounting a ON bc.id = a.category_id AND a.month = :month
                WHERE bc.month = :month
                GROUP BY bc.id, bc.name, bc.monthly_budget
                ORDER BY spent DESC
            """),
            {"month": month},
        )
        categories = [
            {
                "category_id": r[0],
                "name": r[1],
                "monthly_budget": float(r[2]) if r[2] else None,
                "spent": float(r[3]),
            }
            for r in result.fetchall()
        ]

        total = sum(c["spent"] for c in categories)
        return {"month": month, "total_spent": total, "categories": categories}


async def get_budget_status() -> List[Dict[str, Any]]:
    """查询所有类的本月预算使用状态。"""
    today = date.today()
    month = today.strftime("%Y-%m")

    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                SELECT bc.id, bc.name, bc.monthly_budget, bc.alert_threshold,
                       COALESCE(SUM(a.amount), 0) AS spent
                FROM budget_categories bc
                LEFT JOIN accounting a ON bc.id = a.category_id AND a.month = :month
                WHERE bc.month = :month
                GROUP BY bc.id
                ORDER BY spent DESC
            """),
            {"month": month},
        )
        alerts = []
        for r in result.fetchall():
            cat_id, name, budget, threshold, spent = r
            budget_f = float(budget) if budget else 0
            spent_f = float(spent)
            usage = spent_f / budget_f if budget_f > 0 else 0
            entry = {
                "category_id": cat_id,
                "name": name,
                "monthly_budget": budget_f,
                "alert_threshold": float(threshold) if threshold else 0.80,
                "spent": spent_f,
                "usage_pct": round(usage * 100, 1),
                "is_over_budget": usage >= 1.0,
                "is_near_limit": 0.80 <= usage < 1.0,
            }
            alerts.append(entry)
        return alerts


# ---- Write Tools ----

async def create_accounting_entry(data: CreateAccountingEntryInput) -> Dict[str, Any]:
    """创建记账记录。amount 正数=支出，负数=收入。"""
    today = date.today()
    month = today.strftime("%Y-%m")

    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                INSERT INTO accounting (amount, category_id, description, source, month)
                VALUES (:amount, :category_id, :description, :source, :month)
                RETURNING id
            """),
            {
                "amount": data.amount,
                "category_id": data.category_id,
                "description": data.description,
                "source": data.source,
                "month": month,
            },
        )
        new_id = result.scalar()
        await session.commit()
        logger.info(f"记账已记录: id={new_id} amount={data.amount}")
        return {"id": new_id, "amount": data.amount, "month": month}


async def create_budget_category(data: CreateBudgetCategoryInput) -> Dict[str, Any]:
    """创建预算类目。month 默认当前月 (YYYY-MM)。"""
    today = date.today()
    month = today.strftime("%Y-%m")

    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                INSERT INTO budget_categories (name, month, monthly_budget, alert_threshold)
                VALUES (:name, :month, :monthly_budget, :alert_threshold)
                RETURNING id
            """),
            {
                "name": data.name,
                "month": month,
                "monthly_budget": data.monthly_budget,
                "alert_threshold": data.alert_threshold or 0.80,
            },
        )
        new_id = result.scalar()
        await session.commit()
        return {"id": new_id, "name": data.name}


async def update_budget_category(cat_id: int, data: UpdateBudgetCategoryInput) -> Dict[str, Any]:
    """更新预算类目（中风险操作）。"""
    updates = []
    params: dict = {"id": cat_id}
    if data.monthly_budget is not None:
        updates.append("monthly_budget = :monthly_budget")
        params["monthly_budget"] = data.monthly_budget
    if data.alert_threshold is not None:
        updates.append("alert_threshold = :alert_threshold")
        params["alert_threshold"] = data.alert_threshold

    if not updates:
        return {"error": "没有要更新的字段"}

    async with async_session_factory() as session:
        await session.execute(
            text(f"UPDATE budget_categories SET {', '.join(updates)} WHERE id = :id"),
            params,
        )
        await session.commit()
        logger.info(f"预算类目已更新: id={cat_id}")
        return {"id": cat_id, "updated": True}

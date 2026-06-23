"""
Todo 工具集 — Todo Agent 的工具函数。

提供完整的 Todo / Goal / TodoInstance CRUD。
"""

import logging
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.database import async_session_factory

logger = logging.getLogger("todo_tools")


def _parse_date(val: Union[str, date, None]) -> Optional[date]:
    """将字符串或 date 对象统一转为 date，供 asyncpg 参数绑定使用。"""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    return date.fromisoformat(val)


def _parse_time(val: Union[str, time, None]) -> Optional[time]:
    """将字符串或 time 对象统一转为 time。"""
    if val is None:
        return None
    if isinstance(val, time):
        return val
    return time.fromisoformat(val)


# ============================================================
# Pydantic Schemas
# ============================================================

class CreateTodoInput(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    type: str = Field(..., pattern="^(one_time|recurring)$")
    goal_id: Optional[int] = None
    description: Optional[str] = None
    recurrence_rule: Optional[Dict[str, Any]] = None
    scheduled_date: Optional[str] = None  # YYYY-MM-DD
    scheduled_time: Optional[str] = None  # HH:MM
    duration_minutes: Optional[int] = None

class CreateGoalInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    category: Optional[str] = None
    target_date: Optional[str] = None  # YYYY-MM-DD

class UpdateTodoInstanceStatusInput(BaseModel):
    id: int
    status: str = Field(..., pattern="^(completed|cancelled|postponed)$")
    notes: Optional[str] = None
    postponed_to: Optional[str] = None  # YYYY-MM-DD
    completed_at: Optional[str] = None  # ISO datetime

class UpdateTodoRecurrenceInput(BaseModel):
    id: int
    new_rule: Dict[str, Any]

class CreateTodoInstanceInput(BaseModel):
    todo_id: int
    date: str  # YYYY-MM-DD
    scheduled_time: Optional[str] = None  # HH:MM


# ============================================================
# Read Tools
# ============================================================

async def get_todos_by_date(target_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    查询指定日期的 Todo 实例（含关联的 Todo 信息）。

    参数:
        target_date: YYYY-MM-DD 格式，默认今天

    返回:
        [{"id", "todo_id", "title", "type", "scheduled_time", "status",
          "goal_id", "goal_name", "notes", ...}, ...]
    """
    target = _parse_date(target_date) if target_date else date.today()

    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                SELECT
                    ti.id, ti.todo_id, ti.date, ti.scheduled_time,
                    ti.status, ti.completed_at, ti.postponed_to, ti.notes,
                    t.title, t.type, t.goal_id,
                    g.name AS goal_name
                FROM todo_instances ti
                JOIN todos t ON ti.todo_id = t.id
                LEFT JOIN goals g ON t.goal_id = g.id
                WHERE ti.date = :target_date
                ORDER BY ti.scheduled_time NULLS LAST, ti.id
            """),
            {"target_date": target},
        )
        rows = result.fetchall()
        return [
            {
                "id": r[0],
                "todo_id": r[1],
                "date": str(r[2]),
                "scheduled_time": str(r[3]) if r[3] else None,
                "status": r[4],
                "completed_at": str(r[5]) if r[5] else None,
                "postponed_to": str(r[6]) if r[6] else None,
                "notes": r[7],
                "title": r[8],
                "type": r[9],
                "goal_id": r[10],
                "goal_name": r[11],
            }
            for r in rows
        ]


async def get_goals(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    查询目标列表。

    参数:
        status: 筛选状态（active/paused/completed/abandoned），None 返回全部

    返回:
        [{"id", "name", "description", "category", "status", "target_date", ...}, ...]
    """
    async with async_session_factory() as session:
        if status:
            result = await session.execute(
                text("SELECT * FROM goals WHERE status = :status ORDER BY created_at DESC"),
                {"status": status},
            )
        else:
            result = await session.execute(
                text("SELECT * FROM goals ORDER BY created_at DESC")
            )
        rows = result.fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "description": r[2],
                "category": r[3],
                "status": r[4],
                "target_date": str(r[5]) if r[5] else None,
                "completed_at": str(r[6]) if r[6] else None,
                "created_at": str(r[7]),
            }
            for r in rows
        ]


# ============================================================
# Write Tools (Low Risk)
# ============================================================

async def create_todo(data: CreateTodoInput) -> Dict[str, Any]:
    """
    创建待办规则。

    返回:
        {"id": int, "title": str, "type": str, ...}
    """
    import json as _json
    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                INSERT INTO todos (goal_id, title, description, type,
                                   recurrence_rule, scheduled_date,
                                   scheduled_time, duration_minutes)
                VALUES (:goal_id, :title, :description, :type,
                        CAST(:recurrence_rule AS jsonb), :scheduled_date,
                        :scheduled_time, :duration_minutes)
                RETURNING id
            """),
            {
                "goal_id": data.goal_id,
                "title": data.title,
                "description": data.description,
                "type": data.type,
                "recurrence_rule": _json.dumps(data.recurrence_rule) if data.recurrence_rule else None,
                "scheduled_date": _parse_date(data.scheduled_date),
                "scheduled_time": _parse_time(data.scheduled_time),
                "duration_minutes": data.duration_minutes,
            },
        )
        new_id = result.scalar()
        await session.commit()
        logger.info(f"Todo 已创建: id={new_id}, title='{data.title}'")
        return {
            "id": new_id,
            "title": data.title,
            "type": data.type,
            "status": "active",
        }


async def create_todo_instance(data: CreateTodoInstanceInput) -> Dict[str, Any]:
    """
    手动创建待办实例（通常由调度器自动生成，也可手动创建）。

    返回:
        {"id": int, "todo_id": int, "date": str}
    """
    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                INSERT INTO todo_instances (todo_id, date, scheduled_time)
                VALUES (:todo_id, :date, :scheduled_time)
                RETURNING id
            """),
            {
                "todo_id": data.todo_id,
                "date": _parse_date(data.date),
                "scheduled_time": _parse_time(data.scheduled_time),
            },
        )
        new_id = result.scalar()
        await session.commit()
        return {
            "id": new_id,
            "todo_id": data.todo_id,
            "date": data.date,
            "status": "pending",
        }


async def update_todo_instance_status(
    instance_id: int,
    status: str,
    notes: Optional[str] = None,
    postponed_to: Optional[str] = None,
    completed_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    更新待办实例状态。

    参数:
        instance_id: 实例 ID
        status: completed / cancelled / postponed
        notes: 备注（感受、原因等）
        postponed_to: 推迟到的日期 YYYY-MM-DD
        completed_at: 完成时间 ISO 格式
    """
    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                UPDATE todo_instances
                SET status = :status,
                    notes = COALESCE(:notes, notes),
                    postponed_to = :postponed_to::date,
                    completed_at = :completed_at::timestamptz
                WHERE id = :id
                RETURNING id, todo_id, status, notes
            """),
            {
                "id": instance_id,
                "status": status,
                "notes": notes,
                "postponed_to": _parse_date(postponed_to),
                "completed_at": completed_at or (
                    datetime.now().isoformat() if status == "completed" else None
                ),
            },
        )
        row = result.fetchone()
        await session.commit()

        if row is None:
            return {"error": f"未找到实例 id={instance_id}"}

        logger.info(f"TodoInstance {instance_id}: status → {status}")
        return {
            "id": row[0],
            "todo_id": row[1],
            "status": row[2],
            "notes": row[3],
        }


async def create_goal(data: CreateGoalInput) -> Dict[str, Any]:
    """创建目标。"""
    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                INSERT INTO goals (name, description, category, target_date)
                VALUES (:name, :description, :category, :target_date)
                RETURNING id
            """),
            {
                "name": data.name,
                "description": data.description,
                "category": data.category,
                "target_date": data.target_date,
            },
        )
        new_id = result.scalar()
        await session.commit()
        logger.info(f"Goal 已创建: id={new_id}, name='{data.name}'")
        return {"id": new_id, "name": data.name, "status": "active"}


async def update_goal_status(goal_id: int, status: str) -> Dict[str, Any]:
    """
    更新目标状态。

    参数:
        goal_id: 目标 ID
        status: active / paused / completed / abandoned
    """
    async with async_session_factory() as session:
        set_clause = ["status = :status"]
        if status == "completed":
            set_clause.append("completed_at = NOW()")

        result = await session.execute(
            text(f"""
                UPDATE goals SET {', '.join(set_clause)}
                WHERE id = :id
                RETURNING id, name, status
            """),
            {"id": goal_id, "status": status},
        )
        row = result.fetchone()
        await session.commit()

        if row is None:
            return {"error": f"未找到目标 id={goal_id}"}

        logger.info(f"Goal {goal_id}: status → {status}")
        return {"id": row[0], "name": row[1], "status": row[2]}


# ============================================================
# Write Tools (Medium Risk — 需要 confirm_action)
# ============================================================

async def update_todo_recurrence_rule(todo_id: int, new_rule: Dict[str, Any]) -> Dict[str, Any]:
    """
    更新待办重复规则（中风险操作）。

    参数:
        todo_id: 待办规则 ID
        new_rule: 新的 recurrence_rule 字典
    """
    import json as _json
    async with async_session_factory() as session:
        # 先查旧规则
        result = await session.execute(
            text("SELECT id, title, recurrence_rule FROM todos WHERE id = :id"),
            {"id": todo_id},
        )
        row = result.fetchone()
        if row is None:
            return {"error": f"未找到待办 id={todo_id}"}

        old_rule = row[2]
        await session.execute(
            text("UPDATE todos SET recurrence_rule = CAST(:rule AS jsonb) WHERE id = :id"),
            {"id": todo_id, "rule": _json.dumps(new_rule)},
        )
        await session.commit()
        logger.info(f"Todo {todo_id} recurrence_rule 已更新: {old_rule} → {new_rule}")
        return {
            "id": todo_id,
            "title": row[1],
            "old_rule": old_rule,
            "new_rule": new_rule,
        }

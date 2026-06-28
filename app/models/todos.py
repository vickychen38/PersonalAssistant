"""Todo + TodoInstance ORM 模型 — 待办规则表和待办实例表。"""

from datetime import date, datetime, time
from typing import Optional, Dict, Any

from sqlalchemy import (
    String, Integer, Text, Date, Time, DateTime,
    ForeignKey, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Todo(Base):
    """待办规则表 — 定义待办模板和重复规则。"""

    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    goal_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("goals.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    # type: one_time / recurring

    recurrence_rule: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    # 示例: {"frequency":"daily"}
    #       {"frequency":"weekly","days":[2,4],"time":"12:00"}
    #       {"frequency":"every_n_days","n":2}

    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scheduled_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    # status: active / paused / completed / cancelled

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<Todo(id={self.id}, title='{self.title}', "
            f"type='{self.type}', status='{self.status}')>"
        )

    def is_active(self) -> bool:
        return self.status == "active"


class TodoInstance(Base):
    """待办实例表 — 每天由调度器从 Todo 规则生成的具体实例。"""

    __tablename__ = "todo_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    todo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("todos.id"), nullable=False
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    scheduled_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    # status: pending / completed / cancelled / postponed

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    postponed_to: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<TodoInstance(id={self.id}, todo_id={self.todo_id}, "
            f"scheduled_at={self.scheduled_at}, status='{self.status}')>"
        )

    @property
    def is_completed(self) -> bool:
        return self.status == "completed"

    @property
    def is_pending(self) -> bool:
        return self.status == "pending"

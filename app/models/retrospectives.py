"""情绪 + 复盘 ORM 模型 — 每日情绪状态 + 复盘。"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    String, Integer, SmallInteger, Text, Date, DateTime, Numeric, func,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DailyState(Base):
    """每日情绪状态表。"""

    __tablename__ = "daily_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    emotion_tags: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )
    emotion_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    energy_level: Mapped[Optional[int]] = mapped_column(
        SmallInteger, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<DailyState(id={self.id}, date={self.date}, "
            f"energy={self.energy_level})>"
        )


class Retrospective(Base):
    """复盘表 — 日复盘/周复盘/月复盘。"""

    __tablename__ = "retrospectives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    # type: daily / weekly / monthly

    content: Mapped[str] = mapped_column(Text, nullable=False)
    completion_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    emotion_summary: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )
    key_insights: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # "metadata" is a SQLAlchemy reserved name — use "meta" as Python attr
    meta: Mapped[Dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # 唯一约束：(date, type)
    __table_args__ = (
        UniqueConstraint("date", "type", name="retrospectives_date_type_key"),
    )

    def __repr__(self) -> str:
        return f"<Retrospective(id={self.id}, date={self.date}, type='{self.type}')>"

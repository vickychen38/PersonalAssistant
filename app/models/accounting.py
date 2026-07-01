"""记账模块 ORM 模型 — 预算类目 + 记账流水。"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    String, Integer, Text, DateTime, Numeric, ForeignKey, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BudgetCategory(Base):
    """预算类目表。"""

    __tablename__ = "budget_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    monthly_budget: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    alert_threshold: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, default=Decimal("0.80")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<BudgetCategory(id={self.id}, name='{self.name}')>"


class AccountingEntry(Base):
    """记账流水表 — amount 正数为支出，负数为收入。"""

    __tablename__ = "accounting"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("budget_categories.id"), nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="text"
    )
    # month 冗余字段 YYYY-MM，应用层计算写入
    month: Mapped[str] = mapped_column(String(7), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<AccountingEntry(id={self.id}, amount={self.amount}, "
            f"month='{self.month}')>"
        )

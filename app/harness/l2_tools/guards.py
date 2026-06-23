"""
机械化约束守卫 — 与模型无关的硬约束。

包含：
  - SQL 拦截守卫（拦截高风险 DDL/DML）
  - 工具权限守卫（按 Agent 白名单）
  - 中风险操作守卫（防止并发 pending_action）
"""

import logging
from typing import Dict, Any

from app.harness.l2_tools.registry import tool_permission_guard  # re-export

logger = logging.getLogger("guards")


# -----------------------------------------------------------
# SQL 拦截守卫
# -----------------------------------------------------------

# 禁止的关键词（代码层面永不实现这些操作）
FORBIDDEN_KEYWORDS = ["DROP", "ALTER", "TRUNCATE", "DELETE"]

# 禁止的 SQL 模式（更精细的拦截）
FORBIDDEN_PATTERNS = [
    # 任何形式的 ALTER
    "ALTER TABLE", "ALTER COLUMN",
    # 任何形式的 DROP
    "DROP TABLE", "DROP COLUMN", "DROP INDEX", "DROP SCHEMA",
    # 任何形式的 TRUNCATE
    "TRUNCATE TABLE", "TRUNCATE",
    # 任何形式的 DELETE
    "DELETE FROM",
]


class ForbiddenOperationError(Exception):
    """高风险操作被系统拦截。"""
    pass


def sql_guard(sql: str) -> None:
    """
    SQL 拦截守卫：检查 SQL 中是否包含禁止的关键词。

    所有执行原始 SQL 的地方都必须调用此函数。
    """
    sql_upper = sql.upper()

    # 关键词匹配
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in sql_upper:
            raise ForbiddenOperationError(
                f"高风险操作 [{keyword}] 被系统拦截"
            )

    # 模式匹配（更精确）
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.upper() in sql_upper:
            raise ForbiddenOperationError(
                f"高风险操作 [{pattern}] 被系统拦截"
            )

    logger.debug("sql_guard: 检查通过")


# -----------------------------------------------------------
# 中风险操作守卫
# -----------------------------------------------------------


class PendingConfirmationError(Exception):
    """有待确认的操作，不能同时发起新的中风险操作。"""
    pass


def medium_risk_guard(session_metadata: Dict[str, Any], tool_name: str) -> None:
    """
    中风险守卫：检查当前 session 是否有未处理的 pending_action。

    有 pending_action 时阻止发起新的中风险写操作。
    """
    if session_metadata.get("pending_action"):
        raise PendingConfirmationError(
            f"有待确认的操作 [{session_metadata['pending_action'].get('type')}]，"
            f"不能同时发起新的中风险操作 [{tool_name}]"
        )


# -----------------------------------------------------------
# 综合守卫入口
# -----------------------------------------------------------


def run_all_guards(
    agent_type: str,
    tool_name: str,
    sql: str = "",
    session_metadata: Dict[str, Any] | None = None,
    risk_level: str = "low",
) -> None:
    """
    对一次工具调用执行所有相关守卫。

    参数:
        agent_type: Agent 类型（router/todo/accounting/health/retrospective）
        tool_name: 工具函数名
        sql: 原始 SQL（如适用）
        session_metadata: 当前会话 metadata
        risk_level: 操作风险等级（low/medium/high）

    异常:
        PermissionError: 工具不在白名单
        ForbiddenOperationError: SQL 包含禁止关键词
        PendingConfirmationError: 有待确认操作
    """
    # 1. 工具权限检查
    tool_permission_guard(agent_type, tool_name)

    # 2. SQL 拦截（如有 SQL）
    if sql:
        sql_guard(sql)

    # 3. 中风险互斥
    if risk_level == "medium" and session_metadata:
        medium_risk_guard(session_metadata, tool_name)

    logger.debug(
        f"guards 全部通过: agent={agent_type} tool={tool_name} risk={risk_level}"
    )

"""
观测工具 — L5 自观测能力。

提供 Agent 自我查询工具调用历史的能力，用于自我修正和复盘参考。
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.database import async_session_factory

logger = logging.getLogger("observation_tools")


class GetRecentActionsInput(BaseModel):
    limit: int = Field(default=20, ge=1, le=200, description="返回记录数")
    agent_type: Optional[str] = Field(default=None, description="可选，按 Agent 类型筛选")


async def get_recent_agent_actions(
    limit: int = 20,
    agent_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    查询最近的 Agent 工具调用日志（L5 观测层）。

    参数:
        limit: 返回记录数（默认 20，最大 200）
        agent_type: 可选，按 Agent 类型筛选

    返回:
        [{"id", "session_id", "agent_type", "tool_name", "input",
          "output", "success", "error_msg", "duration_ms", "created_at"}, ...]
    """
    async with async_session_factory() as session:
        if agent_type:
            result = await session.execute(
                text("""
                    SELECT id, session_id, agent_type, tool_name,
                           input, output, success, error_msg, duration_ms, created_at
                    FROM agent_action_logs
                    WHERE agent_type = :agent_type
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {"agent_type": agent_type, "limit": limit},
            )
        else:
            result = await session.execute(
                text("""
                    SELECT id, session_id, agent_type, tool_name,
                           input, output, success, error_msg, duration_ms, created_at
                    FROM agent_action_logs
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {"limit": limit},
            )

        rows = result.fetchall()
        return [
            {
                "id": r[0],
                "session_id": r[1],
                "agent_type": r[2],
                "tool_name": r[3],
                "input": r[4],
                "output": r[5],
                "success": r[6],
                "error_msg": r[7],
                "duration_ms": r[8],
                "created_at": str(r[9]),
            }
            for r in rows
        ]

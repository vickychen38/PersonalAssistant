"""
L5 工具调用日志记录。

每次工具调用完成后自动记录到 agent_action_logs 表。
Agent 可通过 get_recent_agent_actions() 查询自己最近的操作。
"""

import json
import logging
import time
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.database import async_session_factory

logger = logging.getLogger("l5_logger")


async def log_tool_call(
    session_id: Optional[int],
    agent_type: str,
    tool_name: str,
    input_data: Dict[str, Any],
    output_data: Any,
    success: bool,
    error_msg: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> int:
    """
    记录一次工具调用。

    参数:
        session_id: 会话 ID（可为 None）
        agent_type: Agent 类型
        tool_name: 工具名称
        input_data: 输入参数
        output_data: 输出结果
        success: 是否成功
        error_msg: 错误信息
        duration_ms: 执行耗时（毫秒）

    返回:
        日志记录 ID
    """
    async with async_session_factory() as s:
        result = await s.execute(
            text("""
                INSERT INTO agent_action_logs
                    (session_id, agent_type, tool_name, input, output,
                     success, error_msg, duration_ms)
                VALUES
                    (:session_id, :agent_type, :tool_name,
                     CAST(:input AS jsonb), CAST(:output AS jsonb),
                     :success, :error_msg, :duration_ms)
                RETURNING id
            """),
            {
                "session_id": session_id,
                "agent_type": agent_type,
                "tool_name": tool_name,
                "input": json.dumps(input_data, ensure_ascii=False),
                "output": json.dumps(output_data, ensure_ascii=False, default=str),
                "success": success,
                "error_msg": error_msg,
                "duration_ms": duration_ms,
            },
        )
        new_id = result.scalar()
        await s.commit()
        return new_id


class ToolCallContext:
    """工具调用上下文管理器 — 自动记录开始/结束和耗时。"""

    def __init__(self, agent_type: str, session_id: Optional[int] = None):
        self.agent_type = agent_type
        self.session_id = session_id
        self._start_time: float = 0.0

    def start(self):
        self._start_time = time.monotonic()

    async def log(self, tool_name: str, input_data: Dict, output_data: Any,
                  success: bool = True, error_msg: str | None = None):
        duration = int((time.monotonic() - self._start_time) * 1000) if self._start_time else None
        try:
            return await log_tool_call(
                session_id=self.session_id,
                agent_type=self.agent_type,
                tool_name=tool_name,
                input_data=input_data,
                output_data=output_data,
                success=success,
                error_msg=error_msg,
                duration_ms=duration,
            )
        except Exception as e:
            logger.error(f"记录工具日志失败: {e}")
            return None

"""
BaseAgent 基类 — 所有子 Agent 继承此基类。

提供：
  - get_user_context() → 从 user_knowledge 读取相关上下文
  - run(user_message, session, triggered_by) → 执行 Agent 逻辑
  - confirm_action(description, action_type, params, session) → 中风险确认
"""

import logging
from typing import Any, Dict, List, Optional

from app.harness.l2_tools.knowledge_tools import get_user_knowledge

logger = logging.getLogger("agent.base")


class BaseAgent:
    """Agent 基类。"""

    agent_type: str = "base"

    # 可被子类覆盖
    relevant_knowledge_categories: List[str] = []

    async def get_user_context(self) -> str:
        """
        从 user_knowledge 读取此 Agent 相关的用户画像，
        格式化为提示词片段。

        返回:
            格式化后的用户画像文本，如 "用户习惯：..." 或空字符串
        """
        if not self.relevant_knowledge_categories:
            return ""

        lines = []
        for cat in self.relevant_knowledge_categories:
            items = await get_user_knowledge(category=cat)
            for item in items:
                lines.append(f"  - {item['key']}: {item['value']}")

        if not lines:
            return ""

        return "用户画像：\n" + "\n".join(lines)

    async def run(
        self,
        user_message: str,
        session: Optional[Dict[str, Any]] = None,
        triggered_by: str = "user",
    ) -> str:
        """
        执行 Agent 主逻辑。

        参数:
            user_message: 用户消息文本
            session: 当前会话数据（含 messages、metadata 等）
            triggered_by: 触发来源（"user" 或 "scheduler"）

        返回:
            Agent 回复文本
        """
        raise NotImplementedError("子类必须实现 run()")

    async def confirm_action(
        self,
        description: str,
        action_type: str,
        params: Dict[str, Any],
        session: Dict[str, Any],
    ) -> str:
        """
        中风险操作确认流程。

        发送确认消息，在 session.metadata 写入 pending_action，等待用户回复。

        参数:
            description: 人类可读的操作描述
            action_type: 操作类型（如 "update_todo_recurrence_rule"）
            params: 操作的完整参数
            session: 当前会话

        返回:
            提示用户确认的消息文本
        """
        import json
        from datetime import datetime, timezone

        pending_action = {
            "type": action_type,
            "params": params,
            "description": description,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # 写入 session.metadata
        if "metadata" not in session:
            session["metadata"] = {}
        session["metadata"]["pending_action"] = pending_action

        # 更新数据库中的 session
        from sqlalchemy import text
        from app.database import async_session_factory

        async with async_session_factory() as db_session:
            await db_session.execute(
                text("""
                    UPDATE conversation_sessions
                    SET metadata = :metadata::jsonb
                    WHERE id = :id
                """),
                {
                    "id": session.get("id"),
                    "metadata": json.dumps(session["metadata"], ensure_ascii=False),
                },
            )
            await db_session.commit()

        logger.info(f"pending_action 已创建: {action_type} - {description}")

        # 返回确认消息
        return f"{description}\n\n确认执行吗？（回复「好」确认，回复「取消」放弃）"

"""
中风险确认流程 — Agent 主动推断的写操作需先确认。

流程:
  1. Agent 调用 confirm_action() 发送确认消息
  2. 写入 session.metadata.pending_action
  3. 等待用户回复
  4. 用户肯定 → 执行，否定 → 取消
  5. 超过 30 分钟 → 自动清除（由 scheduler 处理）
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger("flows.confirmation")


async def create_confirmation(
    session: Dict[str, Any],
    description: str,
    action_type: str,
    params: Dict[str, Any],
) -> str:
    """
    发起中风险确认流程。

    参数:
        session: 当前会话
        description: 人类可读描述
        action_type: 操作类型
        params: 操作参数

    返回:
        确认消息文本
    """
    pending = {
        "type": action_type,
        "params": params,
        "description": description,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    from app.harness.l4_memory.session_manager import set_pending_action
    await set_pending_action(session["id"], pending)

    logger.info(f"pending_action 已创建: {action_type} - {description}")
    return f"{description}\n\n确认执行吗？（回复「好」确认，回复「取消」放弃）"


async def handle_confirmation_reply(
    user_text: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    """
    处理用户对确认消息的回复。

    返回:
        {
            "resolved": True/False,
            "action": "confirmed"/"cancelled"/"unclear",
            "reply": str,
        }
    """
    from app.harness.l4_memory.session_manager import (
        handle_pending_confirmation,
        check_confirmation,
    )

    result = await handle_pending_confirmation(user_text, session)

    if not result["handled"]:
        return {"resolved": False}

    if result["action"] == "confirmed":
        pending = result["pending"]
        success = await _execute_pending(pending, session.get("id"))
        if success:
            return {
                "resolved": True,
                "action": "confirmed",
                "reply": f"好的，{pending.get('description', '已执行')}。",
            }
        else:
            return {
                "resolved": True,
                "action": "confirmed",
                "reply": "抱歉，执行时遇到了问题。",
            }

    elif result["action"] == "cancelled":
        return {
            "resolved": True,
            "action": "cancelled",
            "reply": "好的，已取消。",
        }

    return {"resolved": True, "action": "unclear",
            "reply": "抱歉我没理解，请回复「好」确认或「取消」放弃。"}


async def _execute_pending(pending: Dict[str, Any], session_id: int) -> bool:
    """执行 pending_action。"""
    action_type = pending.get("type", "")
    params = pending.get("params", {})

    try:
        if action_type == "update_todo_recurrence_rule":
            from app.harness.l2_tools.todo_tools import update_todo_recurrence_rule
            result = await update_todo_recurrence_rule(
                todo_id=params["todo_id"],
                new_rule=params["new_rule"],
            )
            return "error" not in result

        elif action_type == "update_budget_category":
            from app.harness.l2_tools.accounting_tools import update_budget_category, UpdateBudgetCategoryInput
            await update_budget_category(params["id"], UpdateBudgetCategoryInput(**params))
            return True

        elif action_type == "create_recurring_todos_batch":
            from app.harness.l2_tools.todo_tools import create_todo, CreateTodoInput
            for td in params.get("todos", []):
                await create_todo(CreateTodoInput(**td))
            return True

        else:
            logger.warning(f"未知 pending_action type: {action_type}")
            return False

    except Exception as e:
        logger.error(f"执行 pending_action 失败: {e}")
        return False

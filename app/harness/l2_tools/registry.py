"""
工具注册表 — 按 Agent 类型定义工具白名单。

每个 Agent 只能调用白名单内的工具，调用白名单外的工具直接抛 PermissionError，
不进 AI 判断。
"""

from typing import Dict, List


# -----------------------------------------------------------
# 工具白名单
# -----------------------------------------------------------

AGENT_TOOL_WHITELIST: Dict[str, List[str]] = {
    "router": [
        "get_session_status",
        "get_system_config",
    ],
    "todo": [
        "get_todos_by_date",
        "get_goals",
        "create_todo",
        "create_todo_instance",
        "update_todo_instance_status",
        "update_todo_recurrence_rule",
        "create_goal",
        "update_goal_status",
        "upsert_user_knowledge",
        "get_user_knowledge",
        "get_weather",
        "generate_chart",
        "create_scheduled_task",
    ],
    "accounting": [
        "get_accounting_summary",
        "get_budget_status",
        "create_accounting_entry",
        "create_budget_category",
        "update_budget_category",
        "generate_chart",
        "upsert_user_knowledge",
    ],
    "health": [
        "get_health_daily",
        "get_body_measurements",
        "record_health_daily",
        "record_body_measurements",
        "generate_chart",
    ],
    "retrospective": [
        "get_todos_by_date",
        "get_daily_state",
        "get_retrospectives",
        "get_health_daily",
        "get_accounting_summary",
        "get_user_knowledge",
        "create_retrospective",
        "upsert_daily_state",
        "get_recent_agent_actions",
        "generate_chart",
    ],
}

# 叠加的系统级工具（所有 Agent 可用）
_SYSTEM_TOOLS: List[str] = [
    "send_message",
    "send_image",
]

# 完整工具清单
ALL_TOOLS: List[str] = sorted(set(
    tool for tools in AGENT_TOOL_WHITELIST.values()
    for tool in tools
) | set(_SYSTEM_TOOLS))


def get_agent_tools(agent_type: str) -> List[str]:
    """获取某 Agent 的完整工具列表（含系统级工具）。"""
    base = AGENT_TOOL_WHITELIST.get(agent_type, [])
    return sorted(set(base + _SYSTEM_TOOLS))


def tool_permission_guard(agent_type: str, tool_name: str) -> None:
    """
    工具权限守卫：检查 Agent 是否有权调用指定工具。
    无权时抛出 PermissionError。
    """
    allowed = set(AGENT_TOOL_WHITELIST.get(agent_type, [])) | set(_SYSTEM_TOOLS)
    if tool_name not in allowed:
        raise PermissionError(
            f"Agent [{agent_type}] 无权调用工具 [{tool_name}]"
        )

"""
Todo Agent — 待办、目标、晨报、跟进。

使用 DeepSeek V4 Flash（日常）和 V4 Pro（规划）。
"""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict

from app.agents.base import BaseAgent
from app.services.deepseek import chat_with_tools
from app.harness.l2_tools.registry import get_agent_tools

logger = logging.getLogger("agent.todo")

# 工具映射：工具名 → 实际函数
TOOL_MAP = {}

def _init_tool_map():
    """延迟初始化工具映射，避免循环导入。"""
    global TOOL_MAP
    if TOOL_MAP:
        return
    from app.harness.l2_tools import todo_tools, knowledge_tools, system_tools, weather as weather_l2
    from app.services.cconnect import send_text

    TOOL_MAP = {
        # Todo CRUD
        "get_todos_by_date": lambda args: todo_tools.get_todos_by_date(args.get("target_date")),
        "get_goals": lambda args: todo_tools.get_goals(args.get("status")),
        "create_todo": lambda args: todo_tools.create_todo(todo_tools.CreateTodoInput(**args)),
        "create_todo_instance": lambda args: todo_tools.create_todo_instance(todo_tools.CreateTodoInstanceInput(**args)),
        "update_todo_instance_status": lambda args: todo_tools.update_todo_instance_status(
            instance_id=args["id"],
            status=args["status"],
            notes=args.get("notes"),
            postponed_to=args.get("postponed_to"),
            completed_at=args.get("completed_at"),
        ),
        "update_todo_recurrence_rule": lambda args: todo_tools.update_todo_recurrence_rule(
            todo_id=args["id"],
            new_rule=args["new_rule"],
        ),
        "create_goal": lambda args: todo_tools.create_goal(todo_tools.CreateGoalInput(**args)),
        "update_goal_status": lambda args: todo_tools.update_goal_status(
            goal_id=args["id"],
            status=args["status"],
        ),
        # 知识库
        "upsert_user_knowledge": lambda args: knowledge_tools.upsert_user_knowledge(
            category=args["category"],
            key=args["key"],
            value=args["value"],
            source_context=args.get("source_context"),
        ),
        "get_user_knowledge": lambda args: knowledge_tools.get_user_knowledge(args.get("category")),
        # 天气
        "get_weather": lambda args: weather_l2.get_weather(args.get("city")),
        # 图表
        "generate_chart": lambda args: _chart_stub(args),
        # 计划任务
        "create_scheduled_task": _create_scheduled_task,
        # 系统
        "get_system_config": lambda args: system_tools.get_system_config(args.get("key")),
        "send_message": lambda args: send_text(args["content"]),
    }


async def _create_scheduled_task(args: Dict[str, Any]) -> Dict[str, Any]:
    """创建计划任务。"""
    from sqlalchemy import text
    from app.database import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                INSERT INTO scheduled_tasks (task_type, reference_id, scheduled_at, payload)
                VALUES (:task_type, :reference_id, :scheduled_at, :payload::jsonb)
                RETURNING id
            """),
            {
                "task_type": args["task_type"],
                "reference_id": args.get("reference_id"),
                "scheduled_at": args["scheduled_at"],
                "payload": json.dumps(args.get("payload", {})) if args.get("payload") else None,
            },
        )
        new_id = result.scalar()
        await session.commit()
        return {"id": new_id, "task_type": args["task_type"], "status": "pending"}


async def _chart_stub(args: Dict[str, Any]) -> Dict[str, Any]:
    """图表生成占位（后续阶段实现）。"""
    return {"error": "图表生成功能将在后续阶段实现", "requested": args.get("chart_type")}


# ---- System Prompt ----

def _load_prompt() -> str:
    """加载 Todo Agent 系统提示词。"""
    prompt_path = Path(__file__).parent / "prompts" / "todo.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return "你是个人助理，帮助用户管理待办和目标。用简洁友好的中文回复。"


# ---- Agent Class ----

class TodoAgent(BaseAgent):
    """Todo Agent — 管理待办、目标和日常规划。"""

    agent_type = "todo"
    relevant_knowledge_categories = ["运动习惯", "作息规律", "工作模式"]

    def __init__(self):
        _init_tool_map()

    async def run(
        self,
        user_message: str,
        session: Dict[str, Any] | None = None,
        triggered_by: str = "user",
    ) -> str:
        """执行 Todo Agent 主逻辑。"""
        # 构建对话历史
        messages = []
        if session and session.get("messages"):
            messages = session["messages"]
        messages.append({"role": "user", "content": user_message})

        # 加载系统提示词并注入用户画像
        system_prompt = _load_prompt()
        user_context = await self.get_user_context()
        if user_context:
            system_prompt += f"\n\n{user_context}"

        # 今天日期
        today = date.today()
        system_prompt += f"\n\n当前日期: {today.isoformat()}"

        # 获取允许的工具列表
        allowed_tools = get_agent_tools(self.agent_type) if self.agent_type != "base" else []

        # 构建工具 schema（简化版，正式阶段会从注册表生成）
        tool_schemas = _build_tool_schemas(allowed_tools)

        try:
            response = await chat_with_tools(
                system_prompt=system_prompt,
                messages=messages,
                tool_schemas=tool_schemas,
                tool_executor=self._execute_tool,
                model="flash",
            )
            return response.get("content", "抱歉，我暂时无法处理这个请求。")
        except Exception as e:
            logger.error(f"TodoAgent 执行失败: {e}")
            return "抱歉，处理任务时遇到了问题，请稍后再试。"

    async def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """执行工具调用。"""
        # 守卫检查
        from app.harness.l2_tools.guards import tool_permission_guard
        tool_permission_guard(self.agent_type, tool_name)

        func = TOOL_MAP.get(tool_name)
        if func is None:
            return json.dumps({"error": f"未知工具: {tool_name}"})

        try:
            result = await func(args)
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"工具 [{tool_name}] 执行失败: {e}")
            return json.dumps({"error": str(e)})


def _build_tool_schemas(tool_names: list[str]) -> list[dict]:
    """根据工具名列表构建 OpenAI 格式的 tool schemas。"""
    # 简化 schema — 后续阶段会用完整的 function 定义
    schemas = []
    for name in tool_names:
        schemas.append({
            "type": "function",
            "function": {
                "name": name,
                "description": f"Tool: {name}",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True,
                },
            },
        })
    return schemas

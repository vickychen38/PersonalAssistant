"""Health Agent — 体重、体脂、围度记录。使用 DeepSeek V4 Flash。"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

from app.agents.base import BaseAgent
from app.config import config
from app.services.deepseek import chat_with_tools
from app.harness.l2_tools.registry import get_agent_tools

logger = logging.getLogger("agent.health")

TOOL_MAP = {}

def _init_tool_map():
    global TOOL_MAP
    if TOOL_MAP:
        return
    from app.harness.l2_tools import health_tools, system_tools
    from app.harness.l2_tools.visualization import generate_chart_and_send
    from app.services.cconnect import send_text

    TOOL_MAP = {
        "get_health_daily": lambda args: health_tools.get_health_daily(
            args.get("start_date"), args.get("end_date")),
        "get_body_measurements": lambda args: health_tools.get_body_measurements(
            args.get("start_date"), args.get("end_date")),
        "record_health_daily": lambda args: health_tools.record_health_daily(
            health_tools.RecordHealthDailyInput(**args)),
        "record_body_measurements": lambda args: health_tools.record_body_measurements(
            health_tools.RecordBodyMeasurementsInput(**args)),
        "generate_chart": lambda args: generate_chart_and_send(args),
        "send_message": lambda args: send_text(args["content"]),
    }


def _load_prompt() -> str:
    p = Path(__file__).parent / "prompts" / "health.txt"
    return p.read_text(encoding="utf-8") if p.exists() else "你是健康助理。"


class HealthAgent(BaseAgent):
    agent_type = "health"
    relevant_knowledge_categories = ["健康目标", "运动习惯"]

    def __init__(self):
        _init_tool_map()

    async def run(self, user_message: str, session: Dict[str, Any] | None = None, triggered_by: str = "user") -> str:
        messages = []
        if session and session.get("messages"):
            messages = session["messages"]
        messages.append({"role": "user", "content": user_message})

        system_prompt = _load_prompt()
        ctx = await self.get_user_context()
        if ctx:
            system_prompt += f"\n\n{ctx}"
        system_prompt += f"\n用户身高: {config.user_height_cm}cm"

        allowed = get_agent_tools(self.agent_type)
        from app.harness.l2_tools.tool_schemas import build_tool_schemas
        tool_schemas = build_tool_schemas(allowed)

        try:
            resp = await chat_with_tools(system_prompt, messages, tool_schemas,
                                          lambda n, a: self._exec(n, a), model="flash",
                                          session_id=session.get("id") if session else None,
                                          agent_type=self.agent_type)
            return resp.get("content", "抱歉，健康数据处理遇到了问题。")
        except Exception as e:
            logger.error(f"HealthAgent 失败: {e}")
            return "抱歉，健康服务暂时不可用。"

    async def _exec(self, tool_name: str, args: Dict[str, Any]) -> str:
        from app.harness.l2_tools.guards import tool_permission_guard
        tool_permission_guard(self.agent_type, tool_name)
        func = TOOL_MAP.get(tool_name)
        if func is None:
            return json.dumps({"error": f"未知工具: {tool_name}"})
        try:
            return json.dumps(await func(args), ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

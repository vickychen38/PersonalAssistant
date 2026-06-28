"""Accounting Agent — 记账、预算检查、超支分析。使用 DeepSeek V4 Flash。"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

from app.agents.base import BaseAgent
from app.services.deepseek import chat_with_tools
from app.harness.l2_tools.registry import get_agent_tools

logger = logging.getLogger("agent.accounting")

TOOL_MAP = {}

def _init_tool_map():
    global TOOL_MAP
    if TOOL_MAP:
        return
    from app.harness.l2_tools import accounting_tools, knowledge_tools, system_tools
    from app.services.cconnect import send_text

    TOOL_MAP = {
        "get_accounting_summary": lambda args: accounting_tools.get_accounting_summary(args.get("month")),
        "get_budget_status": lambda args: accounting_tools.get_budget_status(),
        "create_accounting_entry": lambda args: accounting_tools.create_accounting_entry(
            accounting_tools.CreateAccountingEntryInput(**args)
        ),
        "create_budget_category": lambda args: accounting_tools.create_budget_category(
            accounting_tools.CreateBudgetCategoryInput(**args)
        ),
        "update_budget_category": lambda args: accounting_tools.update_budget_category(
            args["id"], accounting_tools.UpdateBudgetCategoryInput(**args)
        ),
        "upsert_user_knowledge": lambda args: knowledge_tools.upsert_user_knowledge(
            category=args["category"], key=args["key"],
            value=args["value"], source_context=args.get("source_context"),
        ),
        "generate_chart": lambda args: {"info": "chart stub"},
        "send_message": lambda args: send_text(args["content"]),
    }


def _load_prompt() -> str:
    p = Path(__file__).parent / "prompts" / "accounting.txt"
    return p.read_text(encoding="utf-8") if p.exists() else "你是记账助理。"


class AccountingAgent(BaseAgent):
    agent_type = "accounting"
    relevant_knowledge_categories = ["饮食习惯", "消费习惯"]

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

        allowed = get_agent_tools(self.agent_type)
        tool_schemas = [{"type": "function", "function": {"name": n, "description": f"Tool: {n}",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": True}}} for n in allowed]

        try:
            resp = await chat_with_tools(system_prompt, messages, tool_schemas,
                                          lambda n, a: self._exec(n, a), model="flash",
                                          session_id=session.get("id") if session else None,
                                          agent_type=self.agent_type)
            return resp.get("content", "抱歉，记账处理遇到了问题。")
        except Exception as e:
            logger.error(f"AccountingAgent 失败: {e}")
            return "抱歉，记账服务暂时不可用。"

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

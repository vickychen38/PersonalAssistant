"""
L3 主路由逻辑 — 消息分发入口。

优先级：
  1. 斜杠命令（规则路由，不调用 AI）
  2. 进行中 session 的 pending_action 确认
  3. 进行中 session 继续交给对应 Agent
  4. AI 意图判断 + 路由到子 Agent
"""

import logging
import re
from typing import Any, Dict, Optional

from app.config import config

logger = logging.getLogger("l3_router")

# Agent 映射：agent_type → Agent 类
AGENT_MAP = {}


def _init_agent_map():
    global AGENT_MAP
    if AGENT_MAP:
        return
    from app.agents import TodoAgent, AccountingAgent, HealthAgent, RetrospectiveAgent, ChatAgent
    AGENT_MAP = {
        "todo": TodoAgent,
        "accounting": AccountingAgent,
        "health": HealthAgent,
        "retrospective": RetrospectiveAgent,
        "chat": ChatAgent,
    }


# -----------------------------------------------------------
# 斜杠命令处理（规则路由，不调用 AI）
# -----------------------------------------------------------

SLASH_COMMANDS = {
    r"^/dnd\s+on$": ("dnd_on", "已开启勿扰模式"),
    r"^/dnd\s+off$": ("dnd_off", "已关闭勿扰模式"),
    r"^/city\s+(.+)$": ("city_set", "城市已设置为 {city}"),
    r"^/config\s+morning\s+(\d{1,2}:\d{2})$": ("config_morning", "晨报时间已设置为 {time}"),
    r"^/config\s+evening\s+(\d{1,2}:\d{2})$": ("config_evening", "晚间复盘时间已设置为 {time}"),
    r"^/log(\d*)$": ("view_log", ""),
}


async def _handle_slash_command(user_text: str) -> Optional[str]:
    """处理斜杠命令。返回回复文本，不匹配返回 None。"""
    for pattern, (cmd_type, reply_template) in SLASH_COMMANDS.items():
        match = re.match(pattern, user_text.strip(), re.IGNORECASE)
        if not match:
            continue

        if cmd_type == "dnd_on":
            from app.harness.l2_tools.system_tools import update_system_config
            await update_system_config("dnd_mode", "true")
            return "已开启勿扰模式。我会保持安静，只在必要时联系你。"

        elif cmd_type == "dnd_off":
            from app.harness.l2_tools.system_tools import update_system_config
            await update_system_config("dnd_mode", "false")
            return "已关闭勿扰模式。有什么需要随时找我！"

        elif cmd_type == "city_set":
            city = match.group(1).strip()
            from app.harness.l2_tools.system_tools import update_system_config
            await update_system_config("city", city)
            return f"城市已设置为 {city}，我会用这个城市查天气。"

        elif cmd_type == "config_morning":
            new_time = match.group(1)
            from app.harness.l2_tools.system_tools import update_system_config
            await update_system_config("morning_briefing_time", new_time)
            from app.scheduler.setup import reschedule_time_job
            await reschedule_time_job("morning_briefing", new_time)
            return f"晨报时间已更新为 {new_time}，明早按时推送。"

        elif cmd_type == "config_evening":
            new_time = match.group(1)
            from app.harness.l2_tools.system_tools import update_system_config
            await update_system_config("evening_review_time", new_time)
            from app.scheduler.setup import reschedule_time_job
            await reschedule_time_job("evening_review", new_time)
            return f"晚间复盘时间已更新为 {new_time}。"

        elif cmd_type == "view_log":
            n_str = match.group(1)
            n = int(n_str) if n_str else 10
            n = max(1, min(n, 500))
            return await _get_recent_logs(n)

    return None


# -----------------------------------------------------------
# AI 意图路由
# -----------------------------------------------------------

ROUTER_PROMPT = """你是意图路由助手。根据用户消息判断应该交给哪个 Agent 处理。

可用的 Agent:
- todo: 任务、待办、目标、计划相关
- accounting: 花钱、记账、预算、消费相关
- health: 体重、体脂、围度、健康数据相关
- retrospective: 明确要求写复盘/总结/回顾（如\"写复盘\"、\"总结一下\"）
- chat: 日常闲聊、问候、倾诉心情、上网查资料、问常识、聊八卦

规则:
- 只回复一个 Agent 名（todo / accounting / health / retrospective / chat）
- 多个意图时选最主要的那个
- 单纯倾诉心情、打招呼、闲聊 → chat
- 只有明确说\"写复盘\"/\"总结\"/\"回顾\"才走 retrospective
- 不解释，不加标点，只回复单词"""


async def _get_recent_logs(n: int) -> str:
    """读取最近 n 行日志，格式化为微信消息。"""
    from pathlib import Path

    # router.py 在 app/harness/l3_orchestration/ 下，项目根在 ../../../../
    log_path = Path(__file__).resolve().parent.parent.parent.parent / "logs" / "zhunian.log"
    if not log_path.exists():
        return "📭 暂无日志。"

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        recent = lines[-n:]

        # 只提取 trace、关键阶段和错误
        out = []
        for line in recent:
            stripped = line.rstrip()
            # 简化显示：只保留核心信息
            if "[trace=" in stripped:
                # 提取 trace=xxx 和后面的关键信息
                import re
                m = re.search(r'\[trace=(\w+)\]\s*\[(\w+)\]\s*(\S.*)', stripped)
                if m:
                    tid, stage, detail = m.group(1), m.group(2), m.group(3)
                    out.append(f"🔹 {stage}: {detail[:120]}")
                else:
                    out.append(stripped[-200:])
            elif "[ERROR]" in stripped or "[WARNING]" in stripped:
                out.append(f"⚠️ {stripped[-200:]}")
            elif "[l3_router]" in stripped or "Agent" in stripped:
                out.append(stripped[-200:])

        if not out:
            out = [l.rstrip()[-200:] for l in recent[-10:]]

        body = "\n".join(out)
        return f"📋 最近 {len(recent)} 行日志（关键节点）：\n\n{body}"
    except Exception as e:
        return f"读取日志失败: {e}"


async def ai_route(user_text: str, trace=None) -> str:
    """
    调用 DeepSeek Flash 判断意图，返回 Agent 名称。

    返回: "todo" | "accounting" | "health" | "retrospective" | "chat"
    """
    try:
        from app.services.deepseek import chat
        response = await chat(
            system_prompt=ROUTER_PROMPT,
            messages=[{"role": "user", "content": user_text}],
            model="flash",
            max_tokens=10000,
        )
        result = response.get("content", "").strip().lower()
        logger.info(f"AI 路由判定: input='{user_text[:60]}' → {result}")
        if result in ("todo", "accounting", "health", "retrospective", "chat"):
            return result
        return "chat"
    except Exception as e:
        logger.error(f"AI 路由失败: {e}")
        return "chat"


# -----------------------------------------------------------
# 主入口
# -----------------------------------------------------------


async def route_message(
    user_text: str,
    session: Optional[Dict[str, Any]] = None,
    trace=None,
) -> Dict[str, Any]:
    """
    消息路由主入口。

    返回:
        {
            "route_type": "slash_command" | "pending_confirm" | "session_continue" | "ai_route",
            "agent_type": str | None,
            "reply": str | None,
            "pending_action": dict | None,
        }
    """
    # 1. 斜杠命令
    cmd_reply = await _handle_slash_command(user_text)
    if cmd_reply is not None:
        if trace:
            trace.log("router", "斜杠命令匹配")
        return {"route_type": "slash_command", "agent_type": None, "reply": cmd_reply}

    logger.info(f"消息路由中: text='{user_text[:80]}'")

    # 2. 处理 pending_action 确认
    if session and session.get("metadata", {}).get("pending_action"):
        from app.harness.l4_memory.session_manager import handle_pending_confirmation
        result = await handle_pending_confirmation(user_text, session)
        if result["handled"] and result["action"] in ("confirmed", "cancelled"):
            pending = result["pending"]
            if result["action"] == "confirmed":
                reply = await _execute_pending_action(pending)
                logger.info(f"pending_action 已确认: {pending.get('type')}")
                return {"route_type": "pending_confirm", "agent_type": None, "reply": reply}
            else:
                logger.info("pending_action 已取消")
                return {"route_type": "pending_confirm", "agent_type": None, "reply": "好的，已取消。"}
        elif result["handled"] and result["action"] == "unclear":
            pass

    # 3. 进行中 session 继续
    if session and session.get("session_type") != "casual":
        session_type = session["session_type"]
        agent_map = {
            "evening_review": "retrospective",
            "retrospective_daily": "retrospective",
            "retrospective_weekly": "retrospective",
            "retrospective_monthly": "retrospective",
        }
        agent_type = agent_map.get(session_type, "todo")
        logger.info(f"session 继续路由: type={session_type} → agent={agent_type}")
        return {"route_type": "session_continue", "agent_type": agent_type, "reply": None}

    # 4. AI 意图路由
    agent_type = await ai_route(user_text)
    # chat 是兜底，任何不确定的都走闲聊
    logger.info(f"路由结果: → {agent_type}")
    return {"route_type": "ai_route", "agent_type": agent_type, "reply": None}


async def dispatch_to_agent(
    agent_type: str,
    user_text: str,
    session: Optional[Dict[str, Any]] = None,
    triggered_by: str = "user",
    trace=None,
) -> str:
    """
    将消息分发给对应 Agent 并返回回复。

    参数:
        agent_type: Agent 类型
        user_text: 用户消息
        session: 当前会话
        triggered_by: "user" | "scheduler"
        trace: 链路追踪对象

    返回:
        Agent 回复文本
    """
    _init_agent_map()
    agent_cls = AGENT_MAP.get(agent_type)
    if agent_cls is None:
        logger.warning(f"未知 Agent 类型: {agent_type}")
        return f"抱歉，我暂时不知道如何处理这类请求。"

    try:
        agent = agent_cls()
        logger.info(f"Agent [{agent_type}] 开始处理: text='{user_text[:80]}' trigger={triggered_by}")
        reply = await agent.run(user_text, session, triggered_by)
        logger.info(f"Agent [{agent_type}] 返回: reply='{reply[:80]}'")
        return reply
    except Exception as e:
        logger.error(f"Agent [{agent_type}] 执行失败: {e}", exc_info=True)
        return "抱歉，处理请求时遇到了问题，请稍后再试。"


async def _execute_pending_action(pending: Dict[str, Any]) -> str:
    """执行 confirmed pending_action。"""
    action_type = pending.get("type", "")
    params = pending.get("params", {})
    description = pending.get("description", "")

    try:
        if action_type == "update_todo_recurrence_rule":
            from app.harness.l2_tools.todo_tools import update_todo_recurrence_rule
            result = await update_todo_recurrence_rule(
                todo_id=params["todo_id"],
                new_rule=params["new_rule"],
            )
            if "error" not in result:
                return f"好的，已{description}。"
            return f"操作失败: {result['error']}"

        elif action_type == "update_budget_category":
            from app.harness.l2_tools.accounting_tools import update_budget_category, UpdateBudgetCategoryInput
            result = await update_budget_category(params["id"], UpdateBudgetCategoryInput(**params))
            return f"好的，已更新预算类目。"

        elif action_type == "create_recurring_todos_batch":
            from app.harness.l2_tools.todo_tools import create_todo, CreateTodoInput
            for todo_data in params.get("todos", []):
                await create_todo(CreateTodoInput(**todo_data))
            return f"好的，已创建 {len(params.get('todos', []))} 个任务。"

        else:
            logger.warning(f"未知 pending_action type: {action_type}")
            return f"已执行操作: {description}"

    except Exception as e:
        logger.error(f"执行 pending_action 失败: {e}")
        return f"抱歉，执行操作时出现了问题: {e}"

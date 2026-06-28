"""
L1 信息边界层 — 控制每次 DeepSeek 调用的上下文。

设计原则：渐进式披露，按需加载，不把全量信息塞进单次调用。

单次调用的上下文组成（按顺序拼接）：
  1. 角色定义（来自 prompts/ 对应文件）
  2. 用户画像快照（从 user_knowledge 筛选）
  3. 当前状态（时间、城市、勿扰模式）
  4. 对话历史（最近 20 条）
  5. 工具调用结果（本轮工具执行后的返回值）
"""

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import config

logger = logging.getLogger("l1_context")

# 各 Agent 的信息边界定义
AGENT_KNOWLEDGE_SCOPES = {
    "router": {
        "categories": [],
        "description": "只知道用户消息、当前是否有进行中的 session、勿扰状态",
    },
    "todo": {
        "categories": ["运动习惯", "作息规律", "工作模式"],
        "description": "知道今天的 todo_instances、相关 goals、作息习惯类知识",
    },
    "accounting": {
        "categories": ["消费习惯", "饮食习惯"],
        "description": "知道 budget_categories、本月 accounting 记录",
    },
    "health": {
        "categories": ["健康目标", "运动习惯"],
        "description": "知道近 30 天 health_daily、近 10 次 body_measurements",
    },
    "retrospective": {
        "categories": ["运动习惯", "作息规律", "健康目标", "工作模式", "饮食习惯"],
        "description": "知道当天全部 todo_instances、daily_state、当次会话 messages",
    },
}

# 上下文窗口控制
MAX_CONTEXT_MESSAGES = 20
CONTEXT_WINDOW_TARGET = 0.30  # 单次调用控制在窗口的 30% 以内


async def build_context(
    agent_type: str,
    session: Optional[Dict[str, Any]] = None,
    extra_context: Optional[str] = None,
) -> str:
    """
    构建 Agent 的完整系统提示词上下文。

    参数:
        agent_type: Agent 类型（router/todo/accounting/health/retrospective）
        session: 当前会话（含 messages、metadata 等）
        extra_context: 额外上下文（如当前日期、工具调用结果等）

    返回:
        完整的系统提示词字符串
    """
    parts = []

    # 1. 角色定义
    role_prompt = _load_role_prompt(agent_type)
    if role_prompt:
        parts.append(role_prompt)

    # 2. 用户画像快照
    profile = await _build_user_profile(agent_type)
    if profile:
        parts.append(profile)

    # 3. 当前状态
    state = await _build_current_state()
    parts.append(state)

    # 4. 额外上下文
    if extra_context:
        parts.append(extra_context)

    return "\n\n".join(parts)


def build_messages_for_api(
    session_messages: List[Dict[str, str]],
    max_messages: int = MAX_CONTEXT_MESSAGES,
) -> List[Dict[str, str]]:
    """
    从会话消息中提取最近 N 条用于 API 调用。

    返回:
        最近 max_messages 条消息
    """
    return session_messages[-max_messages:]


def _load_role_prompt(agent_type: str) -> str:
    """从 prompts/ 目录加载角色定义。"""
    prompts_dir = Path(__file__).parent.parent / "agents" / "prompts"
    prompt_file = prompts_dir / f"{agent_type}.txt"

    if prompt_file.exists():
        content = prompt_file.read_text(encoding="utf-8").strip()
        if content:
            return content

    # Fallback
    defaults = {
        "router": "你是意图路由助手，判断用户消息应交给哪个 Agent 处理。",
        "todo": "你是待办管理助手。",
        "accounting": "你是记账助手。",
        "health": "你是健康管理助手。",
        "retrospective": "你是复盘与成长助手。",
    }
    return defaults.get(agent_type, "你是个人AI助理。")


async def _build_user_profile(agent_type: str) -> str:
    """构建用户画像快照。"""
    scope = AGENT_KNOWLEDGE_SCOPES.get(agent_type, {})
    categories = scope.get("categories", [])
    if not categories:
        return ""

    try:
        from app.harness.l2_tools.knowledge_tools import get_user_knowledge
        lines = []
        for cat in categories:
            items = await get_user_knowledge(category=cat)
            for item in items:
                lines.append(f"  - {item['key']}: {item['value']}")

        if lines:
            return "用户画像：\n" + "\n".join(lines)
    except Exception as e:
        logger.warning(f"加载用户画像失败: {e}")

    return ""


async def _build_current_state() -> str:
    """构建当前状态上下文。"""
    today = date.today()
    weekday_names = ["一", "二", "三", "四", "五", "六", "日"]

    lines = [
        f"当前日期: {today.isoformat()} (星期{weekday_names[today.weekday()]})",
    ]

    try:
        from app.harness.l2_tools.system_tools import get_system_config
        cfg = await get_system_config()
        city = cfg.get("city", "")
        dnd = cfg.get("dnd_mode", "false")

        if city:
            lines.append(f"用户城市: {city}")
        lines.append(f"勿扰模式: {'开启' if dnd == 'true' else '关闭'}")
    except Exception as e:
        logger.warning(f"加载系统上下文失败: {e}")

    return "\n".join(lines)

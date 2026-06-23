"""
日复盘流程状态机 — PRD L3 标准流程。

状态流转:
  IDLE → REVIEWING → DEEP_CHAT_CONFIRM → (DEEP_CHATTING →) GENERATING
  → VALIDATING → (SENT | REGENERATING → VALIDATING)
"""

import logging
from typing import Any, Dict

logger = logging.getLogger("flows.retrospective")


async def start_evening_flow() -> Dict[str, Any]:
    """
    晚间复盘流程入口 — 由 scheduler 触发。

    1. 查询今日 todo_instances
    2. 计算完成率
    3. 创建 session（flow_state=REVIEWING）
    4. 发送摘要消息

    返回:
        {"session_id": int, "message": str, "flow_state": "REVIEWING"}
    """
    from app.harness.l4_memory.session_manager import create_session
    from app.harness.l2_tools.todo_tools import get_todos_by_date

    session = await create_session(session_type="evening_review", flow_state="REVIEWING")
    instances = await get_todos_by_date()

    total = len(instances)
    completed = sum(1 for i in instances if i["status"] == "completed")
    rate = round(completed / total * 100, 1) if total > 0 else 0

    if instances:
        parts = [
            f"🌙 晚间复盘 — 今日任务：完成 {completed}/{total} 项（{rate}%）",
            "",
        ]
        unfinished = [i for i in instances if i["status"] != "completed"]
        if unfinished:
            parts.append("未完成：")
            for u in unfinished:
                parts.append(f"  • {u['title']}")
        parts.append("")
        parts.append("聊聊今天吧，有什么想记录的？或者直接说「写复盘」。")
        message = "\n".join(parts)
    else:
        message = "🌙 今天没有安排任务。有什么想聊的吗？或者直接说「写复盘」。"

    return {
        "session_id": session["id"],
        "message": message,
        "flow_state": "REVIEWING",
    }


async def handle_reviewing_reply(user_text: str, session: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理 REVIEWING 状态的用户回复。

    判断:
      - 用户说"好了"/"写吧" → 转换到 DEEP_CHAT_CONFIRM
      - 其他 → 继续对话，追问或引导

    返回:
        {"next_state": str, "reply": str}
    """
    end_keywords = ["好了", "差不多了", "写吧", "直接写", "开始写", "生成复盘"]
    if any(kw in user_text for kw in end_keywords):
        # → DEEP_CHAT_CONFIRM
        from app.harness.l4_memory.session_manager import (
            create_session, end_session, append_message,
        )
        await append_message(session["id"], "user", user_text)
        await append_message(session["id"], "assistant",
            "好的，我先收集数据生成复盘。要聊聊再写吗，还是直接生成？")
        return {
            "next_state": "DEEP_CHAT_CONFIRM",
            "reply": "要聊聊今天再写复盘吗，还是直接生成？",
        }

    # 根据回复长度决定是否追问
    from app.agents.retrospective import RetrospectiveAgent
    agent = RetrospectiveAgent()
    reply = await agent.run(user_text, session, triggered_by="user")
    return {"next_state": "REVIEWING", "reply": reply}


async def handle_deep_chat_confirm(user_text: str, session: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理 DEEP_CHAT_CONFIRM 状态的用户回复。

    判断:
      - 用户选"聊聊" → DEEP_CHATTING
      - 用户选"直接写" → GENERATING
    """
    chat_keywords = ["聊聊", "聊一下", "谈谈", "好的", "可以", "行"]
    write_keywords = ["直接写", "写吧", "生成", "直接生成"]

    if any(kw in user_text for kw in chat_keywords):
        return {
            "next_state": "DEEP_CHATTING",
            "reply": ("好的！那我们聊聊今天。今天哪些事让你最有感觉？"
                      "有什么特别想记录的吗？"),
        }
    else:
        return {"next_state": "GENERATING", "reply": None}


async def handle_deep_chatting(user_text: str, session: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理 DEEP_CHATTING 深度对话。

    根据回复长度决定继续追问还是进入生成：
      - 回复 > 30 字 → 追问
      - 回复 < 10 字 → 进入 GENERATING
      - 说"好了"/"写吧" → 进入 GENERATING
    """
    end_keywords = ["好了", "差不多了", "写吧", "直接写"]
    if any(kw in user_text for kw in end_keywords) or len(user_text) < 10:
        return {"next_state": "GENERATING", "reply": None}

    from app.agents.retrospective import RetrospectiveAgent
    agent = RetrospectiveAgent()
    reply = await agent.run(user_text, session, triggered_by="user")
    return {"next_state": "DEEP_CHATTING", "reply": reply}


async def generate_retrospective(session: Dict[str, Any]) -> Dict[str, Any]:
    """
    生成日复盘 — 数据收集 + Pro 模型生成。

    返回:
        {"content": str, "session_id": int}
    """
    from datetime import date
    from app.harness.l2_tools.todo_tools import get_todos_by_date
    from app.harness.l2_tools.retrospective_tools import get_daily_state, create_retrospective, CreateRetrospectiveInput
    from app.agents.retrospective import RetrospectiveAgent

    today = date.today()

    # 数据收集
    instances = await get_todos_by_date()
    emotions = await get_daily_state(start_date=today.isoformat(), end_date=today.isoformat())

    total = len(instances)
    completed = sum(1 for i in instances if i["status"] == "completed")
    rate = round(completed / total * 100, 1) if total > 0 else 0
    emotion_data = emotions[0] if emotions else None

    # 构建生成 prompt
    data_summary = f"""今日数据:
- 任务: {total} 项, 完成 {completed} 项 ({rate}%)
- 已完成: {', '.join(i['title'] for i in instances if i['status'] == 'completed')}
- 未完成: {', '.join(i['title'] for i in instances if i['status'] != 'completed')}
- 情绪: {emotion_data.get('emotion_tags', []) if emotion_data else '无记录'}"""

    agent = RetrospectiveAgent()
    gen_prompt = f"""请基于以下数据生成日复盘（Markdown格式）：

{data_summary}

格式要求:
## {today.isoformat()} 日复盘
### 今日任务
### 今日状态
### Agent 观察
### 目标进展"""

    messages = [{"role": "user", "content": gen_prompt}]
    from app.services.deepseek import chat
    response = await chat(
        system_prompt="你是复盘生成器。基于数据生成简洁客观的日复盘。用中文。",
        messages=messages,
        model="pro",
        max_tokens=2000,
    )

    content = response.get("content", "")

    # 质量检查
    from app.harness.l5_evaluation.checkers import check_with_retry
    uncompleted = [i for i in instances if i["status"] != "completed"]
    completed_list = [i for i in instances if i["status"] == "completed"]
    result = await check_with_retry(
        content, uncompleted, completed_list, emotion_data,
        regenerate_fn=lambda c, issues: _regenerate(c, issues, agent, data_summary),
    )

    # 保存
    try:
        await create_retrospective(CreateRetrospectiveInput(
            date=today.isoformat(),
            type="daily",
            content=result["content"],
            completion_rate=rate,
            emotion_summary=emotion_data.get("emotion_tags", []) if emotion_data else [],
            key_insights=result["content"][:200],
        ))
    except Exception as e:
        logger.error(f"保存复盘失败: {e}")

    return {
        "content": result["content"],
        "session_id": session["id"],
        "flow_state": "SENT",
    }


async def _regenerate(content: str, issues: str, agent, data_summary: str) -> str:
    """修补/重新生成复盘。"""
    from app.services.deepseek import chat
    response = await chat(
        system_prompt="你是复盘生成器。修补以下问题后重新生成。",
        messages=[
            {"role": "user", "content": f"原始内容:\n{content}\n\n问题: {issues}\n\n数据:\n{data_summary}"},
        ],
        model="pro",
        max_tokens=2000,
    )
    return response.get("content", content)

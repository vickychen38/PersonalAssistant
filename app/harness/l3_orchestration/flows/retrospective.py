"""
复盘生成工具 — 数据收集 + Pro 模型生成 + L5 质量检查。

复盘流程的实际编排由 jobs.py（晚间触发）和 RetrospectiveAgent（对话交互）
直接处理，不经过独立的状态机。此模块仅提供生成能力。
"""

import logging
from typing import Any, Dict

logger = logging.getLogger("flows.retrospective")


async def generate_retrospective(session: Dict[str, Any]) -> Dict[str, Any]:
    """
    生成日复盘 — 收集今日数据 → DeepSeek Pro 生成 → L5 检查 → 保存。

    供 RetrospectiveAgent 或 scheduler 直接调用。
    """
    from datetime import date
    from app.harness.l2_tools.todo_tools import get_todos_by_date
    from app.harness.l2_tools.retrospective_tools import (
        get_daily_state, create_retrospective, CreateRetrospectiveInput,
    )

    today = date.today()
    instances = await get_todos_by_date()
    emotions = await get_daily_state(start_date=today.isoformat(), end_date=today.isoformat())

    total = len(instances)
    completed = sum(1 for i in instances if i["status"] == "completed")
    rate = round(completed / total * 100, 1) if total > 0 else 0
    emotion_data = emotions[0] if emotions else None

    data_summary = (
        f"今日数据:\n"
        f"- 任务: {total} 项, 完成 {completed} 项 ({rate}%)\n"
        f"- 已完成: {', '.join(i['title'] for i in instances if i['status'] == 'completed')}\n"
        f"- 未完成: {', '.join(i['title'] for i in instances if i['status'] != 'completed')}\n"
        f"- 情绪: {emotion_data.get('emotion_tags', []) if emotion_data else '无记录'}"
    )

    gen_prompt = (
        f"请基于以下数据生成日复盘（Markdown 格式）：\n\n{data_summary}\n\n"
        f"格式要求:\n## {today.isoformat()} 日复盘\n"
        "### 今日任务\n### 今日状态\n### Agent 观察\n### 目标进展"
    )

    from app.services.deepseek import chat
    response = await chat(
        system_prompt="你是复盘生成器。基于数据生成简洁客观的日复盘。用中文。",
        messages=[{"role": "user", "content": gen_prompt}],
        model="pro",
        max_tokens=2000,
    )
    content = response.get("content", "")

    # L5 质量检查
    from app.harness.l5_evaluation.checkers import check_with_retry
    uncompleted = [i for i in instances if i["status"] != "completed"]
    completed_list = [i for i in instances if i["status"] == "completed"]
    result = await check_with_retry(
        content, uncompleted, completed_list, emotion_data,
        regenerate_fn=lambda c, issues: _regenerate(c, issues, data_summary),
    )

    # 保存
    try:
        await create_retrospective(CreateRetrospectiveInput(
            date=today.isoformat(), type="daily", content=result["content"],
            completion_rate=rate,
            emotion_summary=emotion_data.get("emotion_tags", []) if emotion_data else [],
            key_insights=result["content"][:200],
        ))
    except Exception as e:
        logger.error(f"保存复盘失败: {e}")

    return {"content": result["content"], "session_id": session["id"], "flow_state": "SENT"}


async def _regenerate(content: str, issues: str, data_summary: str) -> str:
    """修补/重新生成复盘。"""
    from app.services.deepseek import chat
    response = await chat(
        system_prompt="你是复盘生成器。修补以下问题后重新生成。",
        messages=[{"role": "user", "content": f"原始:\n{content}\n\n问题: {issues}\n\n数据:\n{data_summary}"}],
        model="pro", max_tokens=2000,
    )
    return response.get("content", content)

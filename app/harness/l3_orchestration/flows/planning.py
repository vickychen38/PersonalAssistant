"""
模糊想法 → 结构化计划流程状态机。

状态流转:
  DETECTED → CLARIFYING → PLANNING → CONFIRMING → CREATING → DONE
                                             → (PLANNING 修改)
                                             → (CANCELLED)
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger("flows.planning")


async def detect_and_clarify(user_text: str) -> Dict[str, Any]:
    """
    检测模糊目标意图 → 生成澄清问题。

    用 Flash 判断是否为模糊想法，如果是则生成 2-3 个澄清问题。

    返回:
        {"is_fuzzy_goal": bool, "questions": [...], "reply": str}
    """
    # 模糊意图关键词检测
    fuzzy_keywords = ["我想开始", "想养成", "计划", "打算", "要开始", "尝试", "想学", "想坚持"]
    is_fuzzy = any(kw in user_text for kw in fuzzy_keywords)

    if not is_fuzzy:
        return {"is_fuzzy_goal": False}

    prompt = f"""用户说: "{user_text}"
请生成 2-3 个澄清问题，帮助了解用户的具体情况。用 JSON 格式:
{{"questions": ["问题1", "问题2", "问题3"], "category": "目标分类"}}
只输出 JSON。"""

    try:
        import json
        from app.services.deepseek import chat
        response = await chat(
            system_prompt="你是目标澄清助手。",
            messages=[{"role": "user", "content": prompt}],
            model="flash",
            max_tokens=400,
        )
        raw = response.get("content", "{}").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].split("```")[0]
        data = json.loads(raw)

        questions = data.get("questions", [])
        reply = "听起来你想" + user_text.split("，")[0].split("。")[0][:30] + "。想多了解一点：\n\n"
        for i, q in enumerate(questions[:3], 1):
            reply += f"{i}. {q}\n"

        return {"is_fuzzy_goal": True, "questions": questions, "reply": reply}
    except Exception as e:
        logger.warning(f"Clarify 失败: {e}")
        return {"is_fuzzy_goal": False}


async def generate_plan(
    user_text: str,
    questions_answers: List[Dict[str, str]],
    existing_todo_count: int = 0,
) -> Dict[str, Any]:
    """
    基于澄清信息生成结构化计划（Pro 模型）。

    返回:
        {"goals": [...], "todos": [...], "suggestions": str, "reply": str}
    """
    context = f"用户目标: {user_text}\n"
    for qa in questions_answers:
        context += f"问: {qa['q']}\n答: {qa['a']}\n"
    context += f"\n用户当前每天约有 {existing_todo_count} 项任务。"

    prompt = f"""{context}

请生成具体的计划，JSON 格式:
{{
  "goals": [{{"name": "目标名", "category": "分类", "description": "描述"}}],
  "todos": [
    {{"title": "任务名", "type": "recurring", "recurrence_rule": {{"frequency": "daily|weekly|every_n_days", ...}},
       "scheduled_time": "HH:MM", "duration_minutes": 30}}
  ],
  "suggestions": "给你的建议"
}}

规则:
- 每天任务总数不超过 8 个
- 新任务避开现有任务的时间
- 从低频率开始，逐步增加
- 只输出 JSON"""

    try:
        import json
        from app.services.deepseek import chat
        response = await chat(
            system_prompt="你是目标规划师。",
            messages=[{"role": "user", "content": prompt}],
            model="pro",
            max_tokens=2000,
        )
        raw = response.get("content", "{}").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].split("```")[0]
        plan = json.loads(raw)

        # L5 规划检查
        from app.harness.l5_evaluation.checkers import check_plan_conflicts
        check_result = check_plan_conflicts(
            plan.get("todos", []),
            [],  # 新计划，无已有任务
        )

        suggestions = plan.get("suggestions", "")
        if check_result["suggestions"]:
            suggestions += "\n\n⚠️ 自动调整建议:\n" + "\n".join(check_result["suggestions"])

        reply = "这是我根据你的情况定制的计划：\n\n"
        for goal in plan.get("goals", []):
            reply += f"🎯 {goal['name']}: {goal.get('description', '')}\n"

        reply += "\n📋 任务安排：\n"
        for todo in plan.get("todos", []):
            freq = todo.get("recurrence_rule", {})
            freq_desc = freq.get("frequency", "一次性")
            reply += f"  • {todo['title']} ({freq_desc}"
            if todo.get("scheduled_time"):
                reply += f", {todo['scheduled_time']}"
            reply += ")\n"

        reply += f"\n💡 {suggestions}"
        reply += "\n\n确认这个计划吗？（回复「好」确认，「修改」调整，「取消」放弃）"

        return {
            "goals": plan.get("goals", []),
            "todos": plan.get("todos", []),
            "suggestions": suggestions,
            "reply": reply,
        }
    except Exception as e:
        logger.error(f"生成计划失败: {e}")
        return {"error": str(e)}


async def execute_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    执行计划：创建 goals 和 todos。

    返回:
        {"created_goals": int, "created_todos": int}
    """
    from app.harness.l2_tools.todo_tools import create_goal, create_todo, CreateGoalInput, CreateTodoInput

    created_goals = 0
    for g in plan.get("goals", []):
        try:
            await create_goal(CreateGoalInput(
                name=g["name"],
                description=g.get("description"),
                category=g.get("category"),
            ))
        except Exception as e:
            logger.error(f"创建 goal 失败: {e}")

    created_todos = 0
    for t in plan.get("todos", []):
        try:
            await create_todo(CreateTodoInput(
                title=t["title"],
                type=t.get("type", "recurring"),
                recurrence_rule=t.get("recurrence_rule"),
                scheduled_time=t.get("scheduled_time"),
                duration_minutes=t.get("duration_minutes"),
            ))
            created_todos += 1
        except Exception as e:
            logger.error(f"创建 todo 失败: {e}")

    return {"created_goals": created_goals, "created_todos": created_todos}

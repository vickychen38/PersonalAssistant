"""
L5 独立质量检查器。

提供:
  - 复盘质量检查（生成后、发送前执行，使用 Pro 模型 + 专用 checker 提示词）
  - 规划质量检查（规则校验，不调用 AI）

检查项目:
  - 是否覆盖所有未完成任务
  - 是否提及情绪状态
  - 内容是否与数据库数据一致（不能捏造）
  - 长度是否合理
"""

import json
import logging
from typing import Any, Dict, List

from app.config import config

logger = logging.getLogger("l5_checkers")

# 最大重试次数
MAX_RETRIES = 2


# -----------------------------------------------------------
# 复盘质量检查
# -----------------------------------------------------------

CHECKER_PROMPT = """你是复盘质量检查器。请评估以下生成的复盘内容。

检查标准:
1. 是否覆盖了所有未完成的任务（在 data 中 status=uncompleted 的任务必须提到）
2. 是否提及了用户的情绪状态（如果 data 中有 emotion 信息）
3. 内容是否与 data 中的客观数据一致（检查数字、日期、任务名是否捏造）
4. 内容长度是否合理（不能过短，必须超过 100 字）

输入格式:
{
  "content": "生成的复盘文本",
  "data": {
    "uncompleted": [...],
    "completed": [...],
    "emotion": {...}
  }
}

输出 JSON:
{
  "pass": true/false,
  "issues": ["问题描述1", "问题描述2"],
  "score": 1-10
}
只输出 JSON。"""


async def check_retrospective(
    content: str,
    uncompleted: List[Dict],
    completed: List[Dict],
    emotion: Dict | None = None,
) -> Dict[str, Any]:
    """
    检查日复盘质量。

    参数:
        content: 生成的复盘文本
        uncompleted: 未完成任务列表
        completed: 已完成任务列表
        emotion: 情绪数据

    返回:
        {"pass": bool, "issues": [...], "score": int}
    """
    # 规则检查（不调用 AI）: 长度
    if len(content) < 100:
        return {"pass": False, "issues": ["内容过短（<100字）"], "score": 3}

    # 规则检查：未完成任务覆盖
    unchecked = []
    for task in uncompleted:
        title = task.get("title", "")
        if title and title not in content:
            unchecked.append(title)

    if unchecked:
        return {
            "pass": False,
            "issues": [f"未提及以下未完成任务: {', '.join(unchecked)}"],
            "score": 5,
        }

    # AI 检查（仅在生产环境）
    try:
        from app.services.deepseek import chat

        data = {
            "uncompleted": [{"title": t.get("title", "")} for t in uncompleted],
            "completed": [{"title": t.get("title", "")} for t in completed],
            "emotion": emotion or {},
        }

        response = await chat(
            system_prompt=CHECKER_PROMPT,
            messages=[{"role": "user", "content": json.dumps({
                "content": content,
                "data": data,
            }, ensure_ascii=False)}],
            model="pro",
            max_tokens=400,
        )

        raw = response.get("content", "{}").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]

        result = json.loads(raw)
        logger.info(f"L5 质量检查: pass={result.get('pass')} score={result.get('score')}")
        return result

    except Exception as e:
        logger.warning(f"L5 AI 检查失败，退回规则检查结果: {e}")
        # Fallback: 规则检查通过即可
        return {"pass": True, "issues": [], "score": 7}


async def check_with_retry(
    content: str,
    uncompleted: List[Dict],
    completed: List[Dict],
    emotion: Dict | None = None,
    regenerate_fn=None,
) -> Dict[str, Any]:
    """
    质量检查 + 重试循环。

    检查不过 → 调用 regenerate_fn 修补/重新生成，最多重试 MAX_RETRIES 次。
    2 次后仍不过 → 记录日志，返回原始版本。
    """
    for attempt in range(1, MAX_RETRIES + 1):
        result = await check_retrospective(content, uncompleted, completed, emotion)
        if result["pass"]:
            return {"content": content, "passed": True, "attempts": attempt}

        logger.warning(f"L5 检查未通过 (第 {attempt}/{MAX_RETRIES} 次): {result['issues']}")

        if regenerate_fn and attempt < MAX_RETRIES:
            issues_text = "; ".join(result["issues"])
            try:
                content = await regenerate_fn(content, issues_text)
            except Exception as e:
                logger.error(f"再生失败: {e}")
                break

    logger.warning(f"L5 检查重试 {MAX_RETRIES} 次后仍未通过，使用原始版本")
    return {"content": content, "passed": False, "attempts": MAX_RETRIES}


# -----------------------------------------------------------
# 规划质量检查（规则校验，不调用 AI）
# -----------------------------------------------------------


def check_plan_conflicts(
    new_todos: List[Dict],
    existing_todos: List[Dict],
    knowledge: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """
    规划质量检查 — 自动规则校验。

    检查:
      1. 新 todo 的时间段是否与已有 todo 冲突
      2. 每天任务总数是否会超过 8 个
      3. 计划频率是否在用户知识库记录的可用时间内

    返回:
        {"pass": bool, "issues": [...], "suggestions": [...]}
    """
    issues = []
    suggestions = []

    # 检查时间冲突（简化：同一天同时段 ≤ 1 个任务）
    time_slots = {}
    for t in existing_todos:
        ts = t.get("scheduled_time")
        if ts:
            time_slots[str(ts)] = t.get("title", "")

    for t in new_todos:
        ts = t.get("scheduled_time")
        if ts and str(ts) in time_slots:
            issues.append(
                f"「{t.get('title', '')}」({ts}) 与已有任务「{time_slots[str(ts)]}」时间冲突"
            )
            suggestions.append(
                f"「{t.get('title', '')}」建议改到其他时间，避开 {ts}"
            )

    # 检查任务总数
    today_count = len([t for t in existing_todos if t.get("type") == "today"]) + len(new_todos)
    if today_count > 8:
        issues.append(f"今日任务总数将达 {today_count} 个，超过建议的 8 个上限")
        suggestions.append("考虑将部分任务分配到其他日期")

    # 检查可用时间
    if knowledge:
        bed_time = knowledge.get("通常入睡时间", "")
        if bed_time:
            try:
                bt = int(bed_time.replace("点", "").replace("左右", "").strip())
                for t in new_todos:
                    ts = t.get("scheduled_time", "")
                    if ts:
                        t_hour = int(ts.split(":")[0]) if isinstance(ts, str) else ts.hour
                        if t_hour >= bt - 1:
                            suggestions.append(
                                f"「{t.get('title', '')}」安排在 {ts}，太接近入睡时间 ({bed_time})，建议提前"
                            )
            except (ValueError, AttributeError):
                pass

    return {
        "pass": len(issues) == 0,
        "issues": issues,
        "suggestions": suggestions,
    }

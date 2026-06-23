"""
L5 用户反馈闭环处理。

处理:
  - 用户纠正 Agent 说法 → 自动提取正确信息，更新知识库
  - 用户对复盘提出异议 → 触发重新生成，记录日志
"""

import logging
from typing import Any, Dict, Tuple

logger = logging.getLogger("l5_feedback")


# 纠正模式: 否定词 + 正确信息
CORRECTION_PATTERNS = [
    # (否定词, 提取策略): 当用户说 "不对，XXX" 时提取 XXX 作为正确信息
    ("不对", "after"),   # 否定词后的内容
    ("不是", "after"),
    ("错了", "after"),
    ("说错了", "after"),
    ("纠正", "after"),
    ("其实是", "after"),
    ("应该是", "after"),
]


def detect_correction(user_text: str) -> Tuple[bool, str | None, str | None]:
    """
    检测用户是否在纠正 Agent。

    返回:
        (is_correction, wrong_info, correct_info)
    """
    for keyword, strategy in CORRECTION_PATTERNS:
        if keyword in user_text:
            idx = user_text.find(keyword)
            after = user_text[idx + len(keyword):].strip().lstrip("，,").strip()
            if after:
                before = user_text[:idx].strip().rstrip("，,").strip()
                return True, before if before else None, after

    return False, None, None


async def handle_user_correction(
    user_text: str,
    agent_last_message: str,
) -> Dict[str, Any]:
    """
    处理用户纠正。

    流程:
      1. 检测纠正模式
      2. 提取正确信息
      3. 更新知识库
      4. 告知用户

    返回:
        {"handled": bool, "feedback_msg": str, "knowledge_updated": bool}
    """
    is_correction, wrong_info, correct_info = detect_correction(user_text)

    if not is_correction:
        return {"handled": False}

    logger.info(f"检测到用户纠正: wrong={wrong_info} correct={correct_info}")

    if correct_info:
        try:
            # 尝试将纠正内容存入知识库
            from app.harness.l4_memory.knowledge_manager import learn

            # 从 Agent 上一条消息中提取 category（简化: 用消息前 50 字作为上下文）
            context = agent_last_message[:200] if agent_last_message else ""

            result = await learn(
                category="用户反馈",
                key=f"纠正_{__import__('datetime').datetime.now().strftime('%Y%m%d%H%M')}",
                value=f"原来说: {wrong_info or '?'}, 纠正为: {correct_info}",
                source_context=context,
                silent=True,
            )

            return {
                "handled": True,
                "feedback_msg": "好的，我记住了，已更新。" if result["action"] != "conflict" else result["notification_text"],
                "knowledge_updated": result["action"] in ("created", "updated"),
            }
        except Exception as e:
            logger.error(f"处理用户纠正失败: {e}")

    return {"handled": True, "feedback_msg": "好的，已记录。"}


async def handle_retrospective_objection(
    session_id: int,
    user_text: str,
    retrospective_content: str,
) -> Dict[str, Any]:
    """
    处理用户对复盘的异议。

    触发条件: 用户在复盘发送后表达不满/指出错误。

    返回:
        {"should_regenerate": bool, "reason": str}
    """
    objection_keywords = ["不对", "不准", "错了", "有问题", "不是这样", "我不觉得"]
    is_objection = any(kw in user_text for kw in objection_keywords)

    if not is_objection:
        return {"should_regenerate": False}

    logger.info(f"检测到复盘异议: {user_text[:100]}")

    # 记录日志
    try:
        from app.harness.l5_evaluation.logger import log_tool_call
        await log_tool_call(
            session_id=session_id,
            agent_type="retrospective",
            tool_name="create_retrospective",
            input_data={"content": retrospective_content[:200]},
            output_data={"user_objection": user_text[:200]},
            success=False,
            error_msg="用户对复盘内容提出异议",
        )
    except Exception as e:
        logger.warning(f"记录复盘异议失败: {e}")

    return {
        "should_regenerate": True,
        "reason": f"用户表示: {user_text[:200]}",
    }

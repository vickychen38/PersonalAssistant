"""
L4 用户知识管理器 — 知识库写操作的语义封装。

封装 PRD 第十节中的写入规则：
  1. 不存在 → INSERT，告知用户 "我记一下：[内容]"
  2. 存在且相同 → 不操作
  3. 存在但不同 → UPDATE，静默更新
  4. 明显矛盾 → 发消息确认后再更新
"""

import logging
from typing import Any, Dict, Optional

from app.harness.l2_tools.knowledge_tools import get_user_knowledge, upsert_user_knowledge

logger = logging.getLogger("l4_knowledge")


async def learn(
    category: str,
    key: str,
    value: str,
    source_context: Optional[str] = None,
    silent: bool = False,
) -> Dict[str, Any]:
    """
    学习新知识 — 包含写入规则和通知逻辑。

    返回:
        {
            "action": "created"|"updated"|"unchanged"|"conflict",
            "notify_user": bool,      # 是否需要告知用户
            "notification_text": str, # 告知用户的消息
        }
    """
    # 先查是否已存在
    existing = await get_user_knowledge(category=category)
    existing_match = None
    for item in existing:
        if item["key"] == key:
            existing_match = item
            break

    if existing_match is None:
        # 规则 1: 不存在 → INSERT，告知用户
        await upsert_user_knowledge(category, key, value, source_context)
        return {
            "action": "created",
            "notify_user": True,
            "notification_text": f"我记一下：{value}",
        }

    old_value = existing_match["value"]
    if old_value == value:
        # 规则 2: 存在且相同 → 不操作
        return {
            "action": "unchanged",
            "notify_user": False,
            "notification_text": "",
        }

    # 规则 4: 检查是否明显矛盾
    if _is_contradictory(old_value, value):
        return {
            "action": "conflict",
            "notify_user": True,
            "notification_text": f"上次你说{old_value}，现在是{value}，我更新一下吗？",
            "old_value": old_value,
            "new_value": value,
        }

    # 规则 3: 存在但不同 → 静默更新
    result = await upsert_user_knowledge(category, key, value, source_context)
    logger.info(f"知识已静默更新: {category}/{key}")
    return {
        "action": "updated",
        "notify_user": silent is False,
        "notification_text": "" if silent else f"好的，已更新。",
        "old_value": old_value,
    }


async def confirm_learn(
    category: str,
    key: str,
    value: str,
    source_context: Optional[str] = None,
) -> Dict[str, Any]:
    """用户确认后执行写入（用于解决矛盾的场景）。"""
    result = await upsert_user_knowledge(category, key, value, source_context)
    return {
        "action": "confirmed",
        "notify_user": True,
        "notification_text": "好的，我记住了，已更新。",
    }


def _is_contradictory(old: str, new: str) -> bool:
    """
    判断新旧值是否明显矛盾。
    简单的启发式规则：较短且差异大，或用词完全相反。
    """
    if len(old) < 3 or len(new) < 3:
        return False
    # 数字差异超过 50%
    try:
        old_num = float(old.replace("约", "").replace("左右", "").strip())
        new_num = float(new.replace("约", "").replace("左右", "").strip())
        if max(old_num, new_num) > 0:
            change = abs(new_num - old_num) / max(old_num, new_num)
            if change > 0.5:
                return True
    except ValueError:
        pass
    # 包含对立词
    opposites = [
        ("每天", "每周"), ("早上", "晚上"), ("经常", "偶尔"),
        ("喜欢", "不喜欢"),
    ]
    for a, b in opposites:
        if (a in old and b in new) or (b in old and a in new):
            return True
    return False

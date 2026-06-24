"""
L4 会话生命周期管理。

职责:
  - 创建/结束/查询会话
  - 消息追加与压缩触发
  - pending_action 管理
  - 会话过期自动关闭（由调度器触发）
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.database import async_session_factory

logger = logging.getLogger("l4_session")

# 确认词/否定词（PRD L3）
AFFIRMATIVE_WORDS = {"好", "可以", "行", "是", "确认", "ok", "OK", "好的", "没问题",
                      "是的", "对", "嗯", "同意", "执行", "来吧"}
NEGATIVE_WORDS = {"不", "不用", "算了", "取消", "不要", "不行", "否", "别", "放弃",
                   "不需要", "不对", "拒绝"}


def check_confirmation(user_text: str) -> Optional[bool]:
    """
    判断用户回复是肯定还是否定。

    返回:
        True = 肯定, False = 否定, None = 无法判断
    """
    cleaned = user_text.strip().lower()
    # 否定词优先
    for nw in sorted(NEGATIVE_WORDS, key=len, reverse=True):
        if nw in cleaned:
            return False
    for aw in sorted(AFFIRMATIVE_WORDS, key=len, reverse=True):
        if aw in cleaned:
            return True
    return None


async def get_active_session() -> Optional[Dict[str, Any]]:
    """获取当前进行中的会话（ended_at IS NULL，最近一个）。"""
    async with async_session_factory() as s:
        result = await s.execute(
            text("""
                SELECT id, session_type, started_at, messages, metadata
                FROM conversation_sessions
                WHERE ended_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
            """),
        )
        row = result.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "session_type": row[1],
            "started_at": str(row[2]),
            "messages": row[3] if isinstance(row[3], list) else json.loads(row[3] or "[]"),
            "metadata": row[4] if isinstance(row[4], dict) else json.loads(row[4] or "{}"),
        }


async def create_session(session_type: str, flow_state: str = "IDLE") -> Dict[str, Any]:
    """创建新会话。"""
    meta = json.dumps({"flow_state": flow_state})
    async with async_session_factory() as s:
        result = await s.execute(
            text("""
                INSERT INTO conversation_sessions (session_type, messages, metadata)
                VALUES (:stype, CAST('[]' AS jsonb), CAST(:meta AS jsonb))
                RETURNING id
            """),
            {"stype": session_type, "meta": meta},
        )
        new_id = result.scalar()
        await s.commit()
        logger.info(f"创建会话: id={new_id} type={session_type}")
        return {"id": new_id, "session_type": session_type, "messages": [], "metadata": {"flow_state": flow_state}}


async def end_session(session_id: int) -> None:
    """结束会话。"""
    async with async_session_factory() as s:
        await s.execute(
            text("UPDATE conversation_sessions SET ended_at = NOW() WHERE id = :id"),
            {"id": session_id},
        )
        await s.commit()
        logger.info(f"会话已结束: id={session_id}")


async def append_message(
    session_id: int,
    role: str,
    content: str,
    compress: bool = True,
) -> List[Dict[str, str]]:
    """
    向会话追加一条消息，并在超过阈值时触发压缩。

    返回:
        更新后的消息列表（压缩后可能不同）
    """
    async with async_session_factory() as s:
        # 读取当前消息
        result = await s.execute(
            text("SELECT messages FROM conversation_sessions WHERE id = :id FOR UPDATE"),
            {"id": session_id},
        )
        row = result.fetchone()
        if row is None:
            logger.warning(f"append_message: session {session_id} 不存在")
            return []

        msgs = row[0] if isinstance(row[0], list) else json.loads(row[0] or "[]")
        msgs.append({
            "role": role,
            "content": content,
            "ts": datetime.now(timezone.utc).isoformat(),
        })

        # 超过 30 条触发压缩
        if compress and len(msgs) > 30:
            from app.harness.l4_memory.compressor import compress_messages
            msgs = await compress_messages(msgs)

        # 最多保留 50 条
        if len(msgs) > 50:
            msgs = msgs[-50:]

        # 写回
        await s.execute(
            text("UPDATE conversation_sessions SET messages = CAST(:msgs AS jsonb) WHERE id = :id"),
            {"id": session_id, "msgs": json.dumps(msgs, ensure_ascii=False)},
        )
        await s.commit()

        return msgs


async def set_pending_action(session_id: int, pending: Dict[str, Any]) -> None:
    """在 session.metadata 中写入 pending_action。"""
    async with async_session_factory() as s:
        result = await s.execute(
            text("SELECT metadata FROM conversation_sessions WHERE id = :id"),
            {"id": session_id},
        )
        row = result.fetchone()
        if row is None:
            return
        meta = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
        meta["pending_action"] = pending
        await s.execute(
            text("UPDATE conversation_sessions SET metadata = CAST(:meta AS jsonb) WHERE id = :id"),
            {"id": session_id, "meta": json.dumps(meta, ensure_ascii=False)},
        )
        await s.commit()


async def clear_pending_action(session_id: int) -> Optional[Dict[str, Any]]:
    """清除 pending_action 并返回被清除的内容。"""
    async with async_session_factory() as s:
        result = await s.execute(
            text("SELECT metadata FROM conversation_sessions WHERE id = :id"),
            {"id": session_id},
        )
        row = result.fetchone()
        if row is None:
            return None
        meta = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
        cleared = meta.pop("pending_action", None)
        await s.execute(
            text("UPDATE conversation_sessions SET metadata = CAST(:meta AS jsonb) WHERE id = :id"),
            {"id": session_id, "meta": json.dumps(meta, ensure_ascii=False)},
        )
        await s.commit()
        return cleared


async def handle_pending_confirmation(user_text: str, session: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理用户对 pending_action 的回复。

    返回:
        {"handled": True/False, "action": "confirmed"/"cancelled"/"unclear", "pending": ...}
    """
    pending = session.get("metadata", {}).get("pending_action")
    if not pending:
        return {"handled": False}

    result = check_confirmation(user_text)
    session_id = session["id"]

    if result is True:
        await clear_pending_action(session_id)
        logger.info(f"pending_action 已确认: {pending.get('type')}")
        return {"handled": True, "action": "confirmed", "pending": pending}
    elif result is False:
        await clear_pending_action(session_id)
        logger.info(f"pending_action 已取消: {pending.get('type')}")
        return {"handled": True, "action": "cancelled", "pending": pending}
    else:
        return {"handled": True, "action": "unclear", "pending": pending}

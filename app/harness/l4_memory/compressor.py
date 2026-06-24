"""
L4 上下文压缩机制 — 防止上下文窗口溢出。

触发条件: session.messages 数量超过 COMPRESS_THRESHOLD (30 条)
执行步骤:
  1. 取前 20 条消息
  2. 调用 DeepSeek Pro 生成结构化摘要
  3. 将摘要作为 role=system 消息插入 messages 头部
  4. 删除被压缩的 20 条原始消息

Context Reset: 当 token 预估值超窗口 60% 时触发，生成交接文档，开新 session。
"""

import json
import logging
from typing import Any, Dict, List, Optional

from app.config import config

logger = logging.getLogger("l4_compressor")

# 触发压缩的消息数阈值
COMPRESS_THRESHOLD = 30
# 每次压缩的消息数量
COMPRESS_BATCH_SIZE = 20
# 单次调用 token 预估值超 60% 触发 Context Reset
CONTEXT_RESET_RATIO = 0.6


# -----------------------------------------------------------
# Prompt
# -----------------------------------------------------------

COMPRESS_PROMPT = """你是上下文摘要生成器。请阅读以下对话片段，生成一个结构化摘要。

输出必须是合法的 JSON 对象，包含以下字段:
{
  "key_decisions": ["用户做出的重要决定列表"],
  "pending_items": ["尚未完成或待处理的事项"],
  "user_emotions": ["用户表现出的情绪状态"],
  "context_summary": "对话内容的一段话概括"
}

只输出 JSON，不要包含其他文字。"""


# -----------------------------------------------------------
# 压缩逻辑
# -----------------------------------------------------------


def _should_compress(messages: List[Dict[str, str]]) -> bool:
    """判断是否需要触发压缩。"""
    return len(messages) > COMPRESS_THRESHOLD


def _get_encoder():
    """获取 tiktoken 编码器，失败返回 None 走 fallback。"""
    try:
        import tiktoken
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def _estimate_tokens(messages: List[Dict[str, str]], system_prompt: str = "") -> int:
    """用 tiktoken 精确估算消息 token 数，失败时回退到字符数估算。"""
    enc = _get_encoder()
    if enc is None:
        total_chars = len(system_prompt)
        for msg in messages:
            total_chars += len(json.dumps(msg, ensure_ascii=False))
        return int(total_chars / 1.5)
    total_text = system_prompt
    for msg in messages:
        total_text += json.dumps(msg, ensure_ascii=False)
    return len(enc.encode(total_text))


def _token_ratio(messages: List[Dict[str, str]], system_prompt: str = "") -> float:
    """计算 token 相对上下文窗口的比例。DeepSeek 128k，保守基线 64k。"""
    estimated = _estimate_tokens(messages, system_prompt)
    return estimated / 64_000


async def compress_messages(
    messages: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """
    压缩消息历史：取前 COMPRESS_BATCH_SIZE 条生成摘要，替换为 system 消息。

    参数:
        messages: 完整消息列表

    返回:
        压缩后的消息列表
    """
    if not _should_compress(messages):
        return messages

    logger.info(f"触发 L4 压缩: {len(messages)} 条消息")

    # 取前 20 条
    batch = messages[:COMPRESS_BATCH_SIZE]

    try:
        from app.services.deepseek import chat

        # 构造对话文本
        conversation_text = ""
        for m in batch:
            role = m.get("role", "user")
            content = m.get("content", "")[:500]  # 每条截取 500 字符
            conversation_text += f"[{role}] {content}\n"

        # 调用 Pro 生成摘要
        response = await chat(
            system_prompt=COMPRESS_PROMPT,
            messages=[{"role": "user", "content": conversation_text}],
            model="pro",
            max_tokens=800,
        )

        raw = response.get("content", "{}").strip()
        # 去掉可能的 markdown 代码块包裹
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]

        summary = json.loads(raw)
        logger.info(f"L4 压缩完成: decisions={len(summary.get('key_decisions', []))}, "
                     f"pending={len(summary.get('pending_items', []))}")

    except Exception as e:
        logger.warning(f"L4 压缩失败，使用纯文本 fallback: {e}")
        # Fallback: 简单截取
        summary = {
            "key_decisions": [],
            "pending_items": [],
            "user_emotions": [],
            "context_summary": batch[-1].get("content", "")[:200] if batch else "",
        }

    # 构建摘要消息
    summary_text = (
        f"[历史摘要] key_decisions: {json.dumps(summary.get('key_decisions', []), ensure_ascii=False)}\n"
        f"pending_items: {json.dumps(summary.get('pending_items', []), ensure_ascii=False)}\n"
        f"user_emotions: {json.dumps(summary.get('user_emotions', []), ensure_ascii=False)}\n"
        f"context: {summary.get('context_summary', '')}"
    )

    # 插入摘要，删除前 20 条
    compressed = [{"role": "system", "content": summary_text}] + messages[COMPRESS_BATCH_SIZE:]

    logger.info(f"压缩完成: {len(messages)} → {len(compressed)} 条消息")
    return compressed


async def context_reset(
    session_id: int,
    messages: List[Dict[str, str]],
    system_prompt: str = "",
) -> Dict[str, Any]:
    """
    Context Reset：生成会话交接文档，开新 session。

    触发条件：token 预估超窗口 60%。

    返回:
        {"should_reset": bool, "handoff": dict | None, "new_session_messages": list}
    """
    ratio = _token_ratio(messages, system_prompt)
    if ratio < CONTEXT_RESET_RATIO:
        return {"should_reset": False}

    logger.warning(f"触发 Context Reset: token ratio={ratio:.1%}")

    try:
        from app.services.deepseek import chat

        conversation_text = ""
        for m in messages[-40:]:  # 取最近 40 条
            role = m.get("role", "user")
            content = m.get("content", "")[:300]
            conversation_text += f"[{role}] {content}\n"

        handoff_prompt = """请为这个对话生成会话交接文档。输出 JSON:
{
  "date_range": "会话起止时间描述",
  "key_insights": ["关键观察 1", "关键观察 2"],
  "user_stated_plans": ["用户明确说的计划"],
  "emotional_arc": "用户情绪走向简述",
  "unresolved_items": ["未解决的事项"]
}
只输出 JSON。"""

        response = await chat(
            system_prompt=handoff_prompt,
            messages=[{"role": "user", "content": conversation_text}],
            model="pro",
            max_tokens=600,
        )

        raw = response.get("content", "{}").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]

        handoff = json.loads(raw)

        # 保存交接文档到 database
        from sqlalchemy import text
        from app.database import async_session_factory

        async with async_session_factory() as s:
            # 关闭当前 session
            await s.execute(
                text("UPDATE conversation_sessions SET ended_at = NOW() WHERE id = :id"),
                {"id": session_id},
            )
            # 创建新 session 并写入交接文档
            meta = json.dumps({"handoff": handoff, "previous_session_id": session_id})
            result = await s.execute(
                text("""
                    INSERT INTO conversation_sessions (session_type, messages, metadata)
                    VALUES ('casual', CAST('[]' AS jsonb), CAST(:meta AS jsonb))
                    RETURNING id
                """),
                {"meta": meta},
            )
            new_id = result.scalar()
            await s.commit()
            logger.info(f"Context Reset: session {session_id} → {new_id}")

        # 新的初始消息
        handoff_text = (
            f"[会话交接] 上一轮对话概要：\n"
            f"关键观察: {json.dumps(handoff.get('key_insights', []), ensure_ascii=False)}\n"
            f"用户计划: {json.dumps(handoff.get('user_stated_plans', []), ensure_ascii=False)}\n"
            f"情绪走向: {handoff.get('emotional_arc', '')}\n"
            f"未解决: {json.dumps(handoff.get('unresolved_items', []), ensure_ascii=False)}"
        )

        return {
            "should_reset": True,
            "handoff": handoff,
            "new_session_id": new_id,
            "new_messages": [{"role": "system", "content": handoff_text}],
        }

    except Exception as e:
        logger.error(f"Context Reset 失败: {e}")
        return {"should_reset": False}

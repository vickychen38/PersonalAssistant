"""
会话上下文存储 — 保存最近一次 webhook 的会话信息，供调度器主动推送使用。

WeChat 平台限制：服务端只能在用户最近互动后的有限窗口内推送消息。
此模块保存最新 webhook 上下文以最大化主动推送成功率。
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("context_store")

# 持久化文件路径
STORE_PATH = Path(__file__).parent.parent.parent / ".context_store.json"


def _read_store() -> dict:
    """读取持久化上下文。"""
    try:
        if STORE_PATH.exists():
            return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"context_store 读取失败: {e}")
    return {}


def _write_store(data: dict) -> None:
    """写入持久化上下文。"""
    try:
        STORE_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning(f"context_store 写入失败: {e}")


def save_webhook_context(
    session_key: str = "",
    project: str = "",
    from_user: str = "",
    context_token: str = "",
) -> None:
    """
    保存最近一次 webhook 消息的会话上下文。

    每次收到用户消息时调用，用于调度器后续主动推送。
    context_token 是 WeChat 平台会话令牌，cc-connect 需要它来推送消息。

    兼容 ACP relay agent 的 payload 格式（session_id / from_user 字段可能缺失）。
    """
    # ACP relay agent 的 payload 不含传统 cc-connect 字段，放宽 guard：
    # 只要有 session_key 或 session_id 就保存
    if not session_key and not from_user:
        # 静默返回，不写空数据
        return

    current = _read_store()
    if session_key:
        current["last_session_key"] = session_key
    if project:
        current["last_project"] = project
    if from_user:
        current["last_from_user"] = from_user
    if context_token:
        current["last_context_token"] = context_token

    _write_store(current)
    logger.debug(f"上下文已保存: session_key={session_key[:20]}..., token={'有' if context_token else '无'}")


def get_last_context() -> dict:
    """
    获取最近保存的会话上下文。

    返回:
        {"session_key": str, "project": str, "from_user": str}
    """
    data = _read_store()
    return {
        "session_key": data.get("last_session_key", ""),
        "project": data.get("last_project", ""),
        "from_user": data.get("last_from_user", ""),
        "context_token": data.get("last_context_token", ""),
    }

"""
cc-connect webhook 消息接收与分发。

POST /webhook/message
"""

import asyncio
import logging
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks

from app.config import config

logger = logging.getLogger("webhook")
router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/message")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    """接收 cc-connect 消息 webhook。

    处理步骤：
    1. 验证 X-CC-Secret 请求头
    2. 立即返回 200
    3. 异步处理消息（BackgroundTasks）
    """
    # 验证 webhook secret
    secret = request.headers.get("X-CC-Secret", "")
    if config.cc_connect_webhook_secret and secret != config.cc_connect_webhook_secret:
        logger.warning("webhook secret 验证失败")
        raise HTTPException(status_code=401, detail="Unauthorized")

    # 解析请求体
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    logger.info(f"收到消息: message_id={body.get('message_id')} from={body.get('from_user')}")

    # 异步处理
    background_tasks.add_task(_handle_message, body)

    return {"status": "ok"}


async def _handle_message(body: dict):
    """实际的消息处理逻辑。"""
    try:
        user_text = body.get("content", "").strip()
        if not user_text:
            return

        # 获取或创建 session
        from app.harness.l4_memory.session_manager import get_active_session, create_session
        session = await get_active_session()

        # 路由消息
        from app.harness.l3_orchestration.router import route_message, dispatch_to_agent
        route_result = await route_message(user_text, session)

        # 如果路由已返回回复（斜杠命令等），直接发送
        if route_result.get("reply"):
            from app.services.cconnect import send_text
            await send_text(route_result["reply"])
            return

        # 获取 Agent 回复
        agent_type = route_result.get("agent_type")
        if agent_type:
            reply = await dispatch_to_agent(agent_type, user_text, session)

            # 更新会话消息
            if session:
                from app.harness.l4_memory.session_manager import append_message
                await append_message(session["id"], "user", user_text)
                await append_message(session["id"], "assistant", reply)
            else:
                # 创建新会话
                session = await create_session(session_type="casual")
                from app.harness.l4_memory.session_manager import append_message
                await append_message(session["id"], "user", user_text)
                await append_message(session["id"], "assistant", reply)

            # 发送回复
            from app.services.cconnect import send_text
            await send_text(reply)

    except Exception as e:
        logger.error(f"消息处理失败: {e}", exc_info=True)
        # 尝试发送错误回复
        try:
            from app.services.cconnect import send_text
            await send_text("抱歉，处理消息时遇到了问题，请稍后再试。")
        except Exception:
            pass

"""
cc-connect webhook 消息接收与分发。

POST /webhook/message
  - ?sync=1: 同步处理，直接在 HTTP 响应中返回 AI 回复（给 ACP Agent 用）
  - 默认: 异步处理，立即返回 200，通过 Unix socket /send 发回复（给 Hooks 用）
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
    1. 验证 X-CC-Secret 请求头（或 ?secret= query 参数）
    2. 同步模式（?sync=1）：阻塞处理，返回 AI 回复文本
    3. 异步模式（默认）：立即返回 200，后台处理
    """
    # 验证 webhook secret（支持 Header 或 Query 参数两种方式）
    header_secret = request.headers.get("X-CC-Secret", "")
    query_secret = request.query_params.get("secret", "")
    secret = header_secret or query_secret
    if config.cc_connect_webhook_secret and secret != config.cc_connect_webhook_secret:
        logger.warning("webhook secret 验证失败")
        raise HTTPException(status_code=401, detail="Unauthorized")

    # 解析请求体
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    logger.info(f"收到消息: message_id={body.get('message_id')} from={body.get('from_user')}")

    # 判断是否同步模式（ACP Agent 调用，需要等待回复）
    is_sync = request.query_params.get("sync") == "1"

    if is_sync:
        # 同步处理：直接返回 AI 回复
        reply_text = await _handle_message(body, send_via_cc=False)
        return {"status": "ok", "reply": reply_text}
    else:
        # 异步处理：后台任务 + Unix socket /send
        background_tasks.add_task(_handle_message_async, body)
        return {"status": "ok"}


async def _handle_message_async(body: dict):
    """异步处理消息（通过 Unix socket /send 发回复）。"""
    await _handle_message(body, send_via_cc=True)


async def _handle_message(body: dict, send_via_cc: bool = False) -> str:
    """实际的消息处理逻辑。

    参数:
        body: webhook 请求体
        send_via_cc: True=通过 Unix socket 发送回复, False=返回回复文本

    返回:
        当 send_via_cc=False 时，返回 AI 回复文本
    """
    from app.services.trace import Trace

    msg_id = body.get("message_id", "")
    trace = Trace(message_id=msg_id)

    try:
        user_text = body.get("content", "").strip()
        if not user_text:
            user_text = body.get("text", "").strip()
        if not user_text:
            logger.warning(f"[trace={trace.trace_id}] 收到空消息")
            return ""

        session_key = body.get("session_key", "")
        project = body.get("project", "")
        from_user = body.get("from_user", "")
        context_token = body.get("context_token", "")

        trace.log("webhook", f"收到消息", user=from_user, text=user_text[:80], sync=str(send_via_cc))

        # 保存 webhook 上下文（含 context_token），供调度器主动推送使用
        from app.services.context_store import save_webhook_context
        save_webhook_context(
            session_key=session_key,
            project=project,
            from_user=from_user,
            context_token=context_token,
        )

        # 获取或创建 session
        from app.harness.l4_memory.session_manager import get_active_session, create_session
        session = await get_active_session()
        if session:
            trace.log("session", f"复用会话", session_id=session["id"])
        else:
            trace.log("session", "无活跃会话，将新建")

        # 路由消息
        from app.harness.l3_orchestration.router import route_message, dispatch_to_agent
        route_result = await route_message(user_text, session, trace=trace)

        # 如果路由已返回回复（斜杠命令等）
        if route_result.get("reply"):
            reply = route_result["reply"]
            trace.log("router", "斜杠命令直接回复", reply=reply[:60])
            if send_via_cc:
                from app.services.cconnect import send_text
                ok = await send_text(reply, session_key=session_key, project=project)
                trace.log("cconnect", "发送回复", success=str(ok))
            trace.done("斜杠命令处理完成")
            return reply

        # 获取 Agent 回复
        agent_type = route_result.get("agent_type")
        if agent_type:
            trace.log("router", f"路由到 Agent", agent=agent_type)

            from app.harness.l3_orchestration.router import dispatch_to_agent
            reply = await dispatch_to_agent(agent_type, user_text, session, trace=trace)

            trace.log("agent", "Agent 回复", reply=reply[:60], agent=agent_type)

            # 更新会话消息
            if session:
                from app.harness.l4_memory.session_manager import append_message
                await append_message(session["id"], "user", user_text)
                await append_message(session["id"], "assistant", reply)
            else:
                session = await create_session(session_type="casual")
                trace.log("session", "新建会话", session_id=session["id"])
                from app.harness.l4_memory.session_manager import append_message
                await append_message(session["id"], "user", user_text)
                await append_message(session["id"], "assistant", reply)

            if send_via_cc:
                from app.services.cconnect import send_text
                ok = await send_text(reply, session_key=session_key, project=project)
                trace.log("cconnect", "发送回复", success=str(ok))
            trace.done(f"回复已{'发送' if send_via_cc else '返回'}")
            return reply

        trace.log("router", "无法路由", text=user_text[:60])
        trace.done("无 Agent 匹配，丢弃")
        return ""

    except Exception as e:
        logger.error(f"[trace={trace.trace_id}] 消息处理失败: {e}", exc_info=True)
        error_msg = "抱歉，处理消息时遇到了问题，请稍后再试。"
        if send_via_cc:
            try:
                from app.services.cconnect import send_text
                await send_text(error_msg, session_key=body.get("session_key", ""), project=body.get("project", ""))
            except Exception:
                pass
        trace.done(f"异常: {e}")
        return error_msg

"""
cc-connect 推送客户端。

cc-connect 通过 Unix socket 暴露 /send API（默认路径 ~/.cc-connect/run/api.sock）。
同时支持 TCP HTTP 模式（如通过 socat 转发）。

API 格式参考: https://github.com/chenhg5/cc-connect
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import httpx

from app.config import config

logger = logging.getLogger("cconnect")

# cc-connect 默认 Unix socket 路径
DEFAULT_SOCK_PATH = str(Path.home() / ".cc-connect" / "run" / "api.sock")

# 发送重试配置
SEND_RETRIES = 3
SEND_RETRY_DELAY = 10  # 秒


def _build_send_payload(
    text: str = "",
    images: list[str] | None = None,
    files: list[str] | None = None,
    tts_text: str = "",
    project: str = "",
    session_key: str = "",
    context_token: str = "",
    to_user: str = "",
) -> dict:
    """构建 cc-connect /send 请求体。

    参数:
        text: 文本消息内容
        images: 图片文件路径列表
        files: 文件路径列表
        tts_text: TTS 语音文本
        project: 项目名称
        session_key: 会话标识
        context_token: WeChat 平台会话令牌（用于回复）
        to_user: 接收者微信用户 ID（用于主动推送）
    """
    payload: dict = {
        "project": project,
        "session_key": session_key,
        "message": text,
    }

    if to_user:
        payload["to_user"] = to_user

    if context_token:
        payload["context_token"] = context_token

    if images:
        payload["images"] = [
            {"path": p} for p in images
        ]

    if files:
        payload["files"] = [
            {"path": p} for p in files
        ]

    if tts_text:
        payload["tts_text"] = tts_text

    return payload


def _get_transport() -> httpx.AsyncBaseTransport | str:
    """根据配置决定使用 Unix socket 还是 TCP 传输。

    如果 CC_CONNECT_API_URL 指向 Unix socket 路径（如 /path/to/sock），
    使用 httpx Unix socket transport。
    否则使用标准 HTTP TCP 传输。
    """
    api_url = config.cc_connect_api_url

    # Unix socket 模式
    if api_url.startswith("unix://"):
        uds_path = api_url[len("unix://"):]
        return httpx.AsyncHTTPTransport(uds=uds_path)

    # 检查是否是本地 socket 路径
    if os.path.exists(api_url) or api_url.startswith("/"):
        return httpx.AsyncHTTPTransport(uds=api_url)

    # 默认：HTTP TCP 模式
    return api_url


async def _post_to_cc(payload: dict, timeout: int = 30) -> bool:
    """向 cc-connect 发送请求。

    优先使用 Unix socket（如果存在），否则使用 TCP HTTP。
    """
    transport = _get_transport()

    for attempt in range(1, SEND_RETRIES + 1):
        try:
            if isinstance(transport, httpx.AsyncBaseTransport):
                # Unix socket 模式
                async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
                    resp = await client.post("http://localhost/send", json=payload)
                    resp.raise_for_status()
            else:
                # TCP HTTP 模式
                url = f"{transport}/send"
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()

            text = payload.get("message", "")
            session_key = payload.get("session_key", "")
            logger.info(f"cc-connect 发送成功: text='{text[:60]}' session_key={session_key[:20] if session_key else '无'}...")
            return True

        except httpx.HTTPError as e:
            text = payload.get("message", "")
            logger.warning(
                f"cc-connect 发送失败 (第 {attempt}/{SEND_RETRIES} 次): {type(e).__name__} | text='{text[:60]}'"
            )
            if attempt < SEND_RETRIES:
                await asyncio.sleep(SEND_RETRY_DELAY)

    logger.error(f"cc-connect 发送全部 {SEND_RETRIES} 次均失败")
    return False


async def send_text(
    content: str,
    to_user: str = "",
    project: str = "",
    session_key: str = "",
    context_token: str = "",
) -> bool:
    """
    发送文本消息到微信。

    参数:
        content: 消息文本
        to_user: 接收者微信用户 ID（调度器主动推送必填，webhook 回复时省略）
        project: 项目名称
        session_key: 会话标识
        context_token: WeChat 平台会话令牌（用于回复，主动推送时省略）

    返回:
        True 成功，False 失败
    """
    if not content:
        logger.warning("send_text: content 为空，跳过")
        return False

    payload = _build_send_payload(
        text=content,
        project=project,
        session_key=session_key,
        context_token=context_token,
        to_user=to_user or "",
    )

    return await _post_to_cc(payload)


async def send_image(
    image_path: str,
    to_user: str = "",
    project: str = "",
    session_key: str = "",
) -> bool:
    """
    发送图片到微信。

    参数:
        image_path: 图片文件路径
        to_user: 接收者微信用户 ID（主动推送时传入）
        project: 项目名称
        session_key: 会话标识

    返回:
        True 成功，False 失败
    """
    if not os.path.exists(image_path):
        logger.error(f"send_image: 文件不存在 {image_path}")
        return False

    payload = _build_send_payload(
        images=[image_path],
        to_user=to_user,
        project=project,
        session_key=session_key,
    )

    return await _post_to_cc(payload)


async def send_tts(
    tts_text: str,
    to_user: str = "",
    project: str = "",
    session_key: str = "",
) -> bool:
    """
    发送 TTS 语音消息。

    参数:
        tts_text: 要朗读的文本
        to_user: 接收者微信用户 ID（主动推送时传入）
        project: 项目名称
        session_key: 会话标识

    返回:
        True 成功，False 失败
    """
    if not tts_text:
        logger.warning("send_tts: tts_text 为空，跳过")
        return False

    payload = _build_send_payload(
        tts_text=tts_text,
        to_user=to_user,
        project=project,
        session_key=session_key,
    )

    return await _post_to_cc(payload)

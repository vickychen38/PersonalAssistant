"""
FastAPI 入口 — 逐念个人 AI 助理系统。

注册路由、启动事件、webhook 端点。
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

# 配置日志格式：[LEVEL] [timestamp] [module] message
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] [%(asctime)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    # ---- 启动阶段 ----
    logger.info("逐念启动中...")

    # 数据库连通性检查
    from app.database import check_db_connection

    db_ok = await check_db_connection()
    if db_ok:
        logger.info("数据库连接成功")
    else:
        logger.warning("数据库连接失败，部分功能不可用")

    # 启动调度器
    from app.scheduler.setup import start_scheduler, refresh_schedule_from_config

    try:
        start_scheduler()
        await refresh_schedule_from_config()
        logger.info("调度器已启动")
    except Exception as e:
        logger.warning(f"调度器启动失败: {e}")

    # 检查 Onboarding 状态
    from app.config import config

    if not config.wechat_user_id:
        logger.warning("WECHAT_USER_ID 未配置，消息功能不可用")

    logger.info(f"逐念已就绪，端口 {config.app_port}")

    yield  # 应用运行中

    # ---- 关闭阶段 ----
    logger.info("逐念正在关闭...")

    from app.scheduler.setup import stop_scheduler

    try:
        stop_scheduler()
        logger.info("调度器已停止")
    except Exception as e:
        logger.warning(f"调度器停止失败: {e}")

    # 关闭数据库引擎
    from app.database import engine
    await engine.dispose()
    logger.info("数据库连接已释放")
    logger.info("逐念已关闭")


app = FastAPI(
    title="逐念",
    description="个人 AI 助理系统 — 微信接入，管理待办、记账、健康数据与成长复盘",
    version="1.0.0",
    lifespan=lifespan,
)


# ---- 健康检查 ----
@app.get("/health", tags=["system"])
async def health_check():
    """健康检查端点。"""
    return {"status": "ok", "service": "逐念"}


# ---- Webhook 路由 ----
from app.webhook import router as webhook_router

app.include_router(webhook_router)

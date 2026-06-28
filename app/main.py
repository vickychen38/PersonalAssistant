"""
FastAPI 入口 — 逐念个人 AI 助理系统。

注册路由、启动事件、webhook 端点。
"""

import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timezone, timedelta
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query

# 日志目录
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE = LOGS_DIR / "zhunian.log"

# 配置日志：[LEVEL] [timestamp] [module] message
# 同时输出到控制台 + 按天滚动的日志文件
file_handler = TimedRotatingFileHandler(
    str(LOG_FILE), when="midnight", backupCount=30, encoding="utf-8"
)
class _MillisFormatter(logging.Formatter):
    """自定义 Formatter：时间精确到毫秒（Python logging 的 datefmt 不支持 %f）。"""
    def formatTime(self, record, datefmt=None):
        from datetime import datetime, timezone
        ct = datetime.fromtimestamp(record.created, tz=timezone(timedelta(hours=8)))
        return ct.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ct.microsecond // 1000:03d}"

LOG_FMT = "[%(levelname)s] [%(asctime)s] [%(name)s] %(message)s"

file_handler.setFormatter(_MillisFormatter(LOG_FMT))

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FMT,
    handlers=[logging.StreamHandler(_MillisFormatter(LOG_FMT)), file_handler],
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


# ---- 日志查看 ----
@app.get("/logs", tags=["system"])
async def view_logs(lines: int = Query(default=50, le=500), trace: str = ""):
    """查看最近日志。

    - lines: 返回行数（默认 50，最多 500）
    - trace: 按 trace_id 过滤（可选）
    """
    if not LOG_FILE.exists():
        return {"error": "日志文件不存在", "path": str(LOG_FILE)}

    # 读取日志文件（可能较大，限制行数）
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        all_lines = f.readlines()

    # 按 trace 过滤
    if trace:
        all_lines = [l for l in all_lines if trace in l]

    recent = all_lines[-lines:]

    return {
        "path": str(LOG_FILE),
        "total_lines": len(all_lines),
        "returned": len(recent),
        "trace": trace or None,
        "lines": [l.rstrip("\n") for l in recent],
    }


# ---- Webhook 路由 ----
from app.webhook import router as webhook_router

app.include_router(webhook_router)

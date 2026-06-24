"""
APScheduler 初始化与生命周期管理。

在 FastAPI startup 事件中启动，shutdown 事件中停止。
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import config
from app.database import async_session_factory
from app.scheduler import jobs
from app.harness.l2_tools.system_tools import get_system_config

logger = logging.getLogger("scheduler")

# 全局调度器实例
scheduler = AsyncIOScheduler()


async def _load_schedule_times() -> tuple[str, str]:
    """从 system_config 读取晨报和复盘时间。"""
    try:
        cfg = await get_system_config()
        morning = cfg.get("morning_briefing_time", "07:30")
        evening = cfg.get("evening_review_time", "22:00")
        return morning, evening
    except Exception:
        logger.warning("无法读取调度配置，使用默认值")
        return "07:30", "22:00"


def start_scheduler():
    """
    启动调度器，注册所有定时任务。

    注册任务：
      daily_todo_gen          每天 0:00
      morning_briefing        from system_config
      evening_review          from system_config（占位）
      todo_followup_scanner   每分钟
      chart_cleanup           每天 3:00
      pending_action_cleaner  每 5 分钟
      session_cleaner         每 10 分钟
    """
    # 晨报和复盘时间从数据库读取（需要在 event loop 中初始化）
    # 这里先注册静态任务，动态任务在 FastAPI startup 中更新

    # 每天 0:00 — 生成待办实例
    scheduler.add_job(
        jobs.daily_todo_gen,
        trigger=CronTrigger(hour=0, minute=0),
        id="daily_todo_gen",
        name="每日待办实例生成",
        replace_existing=True,
    )

    # 晨报 — 先用默认时间，后续在 startup 事件中更新
    scheduler.add_job(
        jobs.morning_briefing,
        trigger=CronTrigger(hour=7, minute=30),
        id="morning_briefing",
        name="晨报",
        replace_existing=True,
    )

    # 每分钟 — Todo 跟进扫描
    scheduler.add_job(
        jobs.todo_followup_scanner,
        trigger=IntervalTrigger(minutes=1),
        id="todo_followup_scanner",
        name="待办跟进扫描",
        replace_existing=True,
    )

    # 每天 3:00 — 清理旧图表
    scheduler.add_job(
        _chart_cleanup,
        trigger=CronTrigger(hour=3, minute=0),
        id="chart_cleanup",
        name="图表清理",
        replace_existing=True,
    )

    # 每 5 分钟 — pending_action 清理
    scheduler.add_job(
        _pending_action_cleaner,
        trigger=IntervalTrigger(minutes=5),
        id="pending_action_cleaner",
        name="待确认操作清理",
        replace_existing=True,
    )

    # 每 10 分钟 — 过期 session 清理
    scheduler.add_job(
        _session_cleaner,
        trigger=IntervalTrigger(minutes=10),
        id="session_cleaner",
        name="会话清理",
        replace_existing=True,
    )

    # 晚间复盘 — 默认 22:00，startup 时从 DB 更新
    scheduler.add_job(
        jobs.evening_review,
        trigger=CronTrigger(hour=22, minute=0),
        id="evening_review",
        name="晚间复盘",
        replace_existing=True,
    )

    # 周复盘 — 随晚间复盘触发（内部检查是否为周日）
    scheduler.add_job(
        jobs.weekly_retro_check,
        trigger=CronTrigger(hour=22, minute=5),
        id="weekly_retro_check",
        name="周复盘检查",
        replace_existing=True,
    )

    # 月复盘 — 随晚间复盘触发（内部检查是否为月末）
    scheduler.add_job(
        jobs.monthly_retro_check,
        trigger=CronTrigger(hour=22, minute=10),
        id="monthly_retro_check",
        name="月复盘检查",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("调度器已启动（9 个任务已注册）")


def stop_scheduler():
    """停止调度器。"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("调度器已停止")


async def reschedule_time_job(job_id: str, new_time: str):
    """
    根据新时间更新调度任务的 trigger。

    参数:
        job_id: "morning_briefing" 或 "evening_review"
        new_time: "HH:MM" 格式
    """
    try:
        hour, minute = new_time.split(":")
        trigger = CronTrigger(hour=int(hour), minute=int(minute))
        scheduler.reschedule_job(job_id, trigger=trigger)
        logger.info(f"调度任务 [{job_id}] 已更新为 {new_time}")
    except Exception as e:
        logger.error(f"更新调度任务 [{job_id}] 失败: {e}")


async def refresh_schedule_from_config():
    """从数据库读取并更新所有动态调度任务。"""
    try:
        morning_time, evening_time = await _load_schedule_times()
        await reschedule_time_job("morning_briefing", morning_time)
        await reschedule_time_job("evening_review", evening_time)
        # 周/月复盘跟随晚间时间偏移 5/10 分钟
        e_h, e_m = int(evening_time.split(":")[0]), int(evening_time.split(":")[1])
        w_m = (e_m + 5) % 60
        w_h = (e_h + (e_m + 5) // 60) % 24
        await _reschedule_job_raw("weekly_retro_check", w_h, w_m)
        m_h2 = (e_h + (e_m + 10) // 60) % 24
        m_m2 = (e_m + 10) % 60
        await _reschedule_job_raw("monthly_retro_check", m_h2, m_m2)
        logger.info(f"调度配置已更新: 晨报={morning_time} 晚间={evening_time}")
    except Exception as e:
        logger.warning(f"刷新调度配置失败: {e}")


async def _reschedule_job_raw(job_id: str, hour: int, minute: int):
    """直接更新时间，不解析字符串。"""
    try:
        trigger = CronTrigger(hour=hour, minute=minute)
        scheduler.reschedule_job(job_id, trigger=trigger)
    except Exception as e:
        logger.error(f"更新调度任务 [{job_id}] 失败: {e}")


# ---- 辅助清理任务 ----

async def _chart_cleanup():
    """清理超过 CHARTS_RETENTION_HOURS 小时的旧图表文件。"""
    import os
    import time as _time
    from pathlib import Path

    charts_dir = Path(config.charts_dir)
    if not charts_dir.exists():
        return

    cutoff = _time.time() - config.charts_retention_hours * 3600
    cleaned = 0
    for f in charts_dir.glob("*.png"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            cleaned += 1

    if cleaned:
        logger.info(f"图表清理完成，删除了 {cleaned} 个文件")


async def _pending_action_cleaner():
    """清理超过 30 分钟无响应的 pending_action。"""
    from sqlalchemy import text

    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                UPDATE conversation_sessions
                SET metadata = metadata - 'pending_action'
                WHERE metadata -> 'pending_action' IS NOT NULL
                  AND (metadata -> 'pending_action' ->> 'created_at')::timestamptz
                      < NOW() - INTERVAL '30 minutes'
            """),
        )
        await session.commit()
        if result.rowcount:
            logger.info(f"清理了 {result.rowcount} 个过期的 pending_action")


async def _session_cleaner():
    """关闭超过 2 小时无响应的 session。"""
    from sqlalchemy import text

    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                UPDATE conversation_sessions
                SET ended_at = NOW()
                WHERE ended_at IS NULL
                  AND started_at < NOW() - INTERVAL '2 hours'
            """),
        )
        await session.commit()
        if result.rowcount:
            logger.info(f"关闭了 {result.rowcount} 个过期 session")

"""
定时任务函数 — APScheduler 调用的具体任务逻辑。

任务列表:
  daily_todo_gen      每天 0:00 生成当天 todo_instances
  morning_briefing    根据 system_config 晨报时间
  evening_review      根据 system_config 复盘时间
  todo_followup_scanner  每分钟扫描待跟进
  chart_cleanup       每天 3:00 清理旧图表
  pending_action_cleaner 每 5 分钟
  session_cleaner     每 10 分钟
"""

import logging
from datetime import date, datetime, time, timezone

from sqlalchemy import text

from app.database import async_session_factory
from app.config import config

logger = logging.getLogger("scheduler.jobs")


def _today() -> date:
    return date.today()


def _parse_time(val) -> time | None:
    """将字符串或 time 对象统一为 time 对象（Python 3.14 asyncpg 兼容）。"""
    if val is None:
        return None
    if isinstance(val, time):
        return val
    if isinstance(val, str):
        parts = val.strip().split(":")
        return time(int(parts[0]), int(parts[1]))
    return None


# ============================================================
# 每日待办实例生成
# ============================================================

async def daily_todo_gen():
    """
    每天 0:00 执行：根据 active 的 Todo 规则生成当天 TodoInstance。

    逻辑：
      - type=one_time 且 scheduled_date=今天 → 生成
      - type=recurring → 解析 recurrence_rule 判断是否生成
        - frequency=daily → 每天
        - frequency=weekly 且今天在 days 列表中 → 生成
        - frequency=every_n_days → 从创建日起每隔 n 天生成
    """
    today = date.today()
    logger.info(f"开始生成 {today} 的待办实例...")

    async with async_session_factory() as session:
        # 查询所有 active 的 todos（含时间和时长信息）
        result = await session.execute(
            text("""
                SELECT id, type, recurrence_rule, scheduled_date,
                       scheduled_time, duration_minutes
                FROM todos WHERE status = 'active'
            """)
        )
        todos = result.fetchall()
        created_count = 0
        followup_count = 0

        for todo in todos:
            todo_id, todo_type, rule, sched_date, sched_time, duration = todo
            should_create = False
            effective_time = sched_time  # 默认用 todo 级时间

            if todo_type == "one_time":
                if sched_date and sched_date == today:
                    should_create = True

            elif todo_type == "recurring" and rule:
                freq = rule.get("frequency", "")
                if freq == "daily":
                    should_create = True
                    effective_time = rule.get("time") or sched_time
                elif freq == "weekly":
                    day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3,
                               "fri": 4, "sat": 5, "sun": 6}
                    today_weekday = today.weekday()
                    target_days = rule.get("days", [])
                    mapped_days = []
                    for d in target_days:
                        if isinstance(d, str) and d.lower() in day_map:
                            mapped_days.append(day_map[d.lower()])
                        elif isinstance(d, int):
                            mapped_days.append(d)
                    if today_weekday in mapped_days:
                        should_create = True
                        effective_time = rule.get("time") or sched_time
                elif freq == "every_n_days":
                    n = rule.get("n", 1)
                    result2 = await session.execute(
                        text("SELECT created_at FROM todos WHERE id = :id"),
                        {"id": todo_id},
                    )
                    created_row = result2.fetchone()
                    if created_row:
                        created_at_val = created_row[0]
                        created_at_d = created_at_val.date() if isinstance(created_at_val, datetime) else created_at_val
                        days_diff = (today - created_at_d).days
                        if days_diff >= 0 and days_diff % n == 0:
                            should_create = True
                            effective_time = rule.get("time") or sched_time

            if should_create:
                result3 = await session.execute(
                    text("SELECT id FROM todo_instances WHERE todo_id = :tid AND date = :d"),
                    {"tid": todo_id, "d": today},
                )
                if result3.fetchone() is None:
                    result_ins = await session.execute(
                        text("""
                            INSERT INTO todo_instances (todo_id, date, scheduled_time)
                            VALUES (:todo_id, :date, :scheduled_time)
                            RETURNING id
                        """),
                        {
                            "todo_id": todo_id,
                            "date": today,
                            "scheduled_time": _parse_time(effective_time),
                        },
                    )
                    instance_id = result_ins.scalar()
                    created_count += 1

                    # 如果有固定时间 + 时长，注册跟进任务
                    effective_duration = duration
                    if rule and not effective_duration:
                        effective_duration = rule.get("duration_minutes")
                    if effective_time and effective_duration:
                        import json
                        from datetime import timedelta
                        pt = _parse_time(effective_time)
                        followup_dt = datetime.combine(today, pt) + timedelta(minutes=effective_duration)
                        await session.execute(
                            text("""
                                INSERT INTO scheduled_tasks
                                    (task_type, reference_id, scheduled_at, payload)
                                VALUES
                                    ('todo_followup', :ref_id, :followup_at, CAST(:payload AS jsonb))
                            """),
                            {
                                "ref_id": instance_id,
                                "followup_at": followup_dt,
                                "payload": json.dumps({"todo_id": todo_id}),
                            },
                        )
                        followup_count += 1

        await session.commit()
        logger.info(
            f"{today} 待办实例生成完成，创建 {created_count} 个实例，"
            f"注册 {followup_count} 个跟进任务"
        )


# ============================================================
# 晨报
# ============================================================

async def morning_briefing():
    """
    晨报生成与发送。

    流程：
      1. 查询今天的 todo_instances
      2. 查询天气
      3. 查询昨天未完成的实例
      4. 如果是周一，附上周复盘
      5. 如果是每月1日，附上月复盘
      6. 用 DeepSeek Flash 生成晨报
      7. 发送到微信
    """
    today = date.today()
    logger.info(f"生成 {today} 晨报...")

    # 1. 查询今天的实例
    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                SELECT ti.id, ti.scheduled_time, ti.status,
                       t.title, t.duration_minutes, g.name AS goal_name
                FROM todo_instances ti
                JOIN todos t ON ti.todo_id = t.id
                LEFT JOIN goals g ON t.goal_id = g.id
                WHERE ti.date = :today
                ORDER BY ti.scheduled_time NULLS LAST
            """),
            {"today": today},
        )
        today_instances = [
            {
                "id": r[0],
                "scheduled_time": str(r[1]) if r[1] else None,
                "status": r[2],
                "title": r[3],
                "duration_minutes": r[4],
                "goal_name": r[5],
            }
            for r in result.fetchall()
        ]

        # 2. 昨天未完成
        yesterday = date.fromordinal(today.toordinal() - 1)
        result2 = await session.execute(
            text("""
                SELECT t.title FROM todo_instances ti
                JOIN todos t ON ti.todo_id = t.id
                WHERE ti.date = :yesterday AND ti.status IN ('pending', 'postponed')
            """),
            {"yesterday": yesterday},
        )
        yesterday_unfinished = [r[0] for r in result2.fetchall()]

        # 3. 周复盘（周一）
        weekly_retro = None
        if today.weekday() == 0:  # Monday
            result3 = await session.execute(
                text("""
                    SELECT content FROM retrospectives
                    WHERE type = 'weekly'
                    ORDER BY date DESC LIMIT 1
                """),
            )
            row = result3.fetchone()
            if row:
                weekly_retro = row[0][:500]  # 截取前500字

        # 4. 月复盘（每月1日）
        monthly_retro = None
        if today.day == 1:
            result4 = await session.execute(
                text("""
                    SELECT content FROM retrospectives
                    WHERE type = 'monthly'
                    ORDER BY date DESC LIMIT 1
                """),
            )
            row = result4.fetchone()
            if row:
                monthly_retro = row[0][:500]

        # 5. 勿扰模式检查
        result5 = await session.execute(
            text("SELECT value FROM system_config WHERE key = 'dnd_mode'")
        )
        dnd_row = result5.fetchone()
        is_dnd = dnd_row and dnd_row[0] == "true"

    # 6. 天气
    weather_info = None
    try:
        from app.services.weather import get_weather
        weather_info = await get_weather()
        if "error" in weather_info:
            weather_info = None
    except Exception as e:
        logger.warning(f"天气获取失败，静默降级: {e}")

    # 7. 调用 DeepSeek Flash 生成晨报
    task_count = len(today_instances)
    briefing_parts = [
        f"早上好！今天是 {today.strftime('%Y年%m月%d日')}，星期{'一二三四五六日'[today.weekday()]}。",
    ]

    if weather_info and "error" not in weather_info:
        briefing_parts.append(
            f"今日天气：{weather_info['city']} {weather_info['text']}，"
            f"{weather_info['temp']}°C，湿度 {weather_info['humidity']}%。"
        )

    if today_instances:
        instance_lines = []
        for inst in today_instances:
            line = f"  • {inst['title']}"
            if inst['scheduled_time']:
                line += f" ({inst['scheduled_time']})"
            if inst['goal_name']:
                line += f" [{inst['goal_name']}]"
            instance_lines.append(line)
        briefing_parts.append(
            f"今日待办 {len(today_instances)} 项：\n" + "\n".join(instance_lines)
        )
        if task_count > 8:
            briefing_parts.append("今天任务较多，注意节奏。")

    if yesterday_unfinished:
        briefing_parts.append(
            f"昨日未完成：{'、'.join(yesterday_unfinished)}"
        )

    # 天气极端 + 户外任务提示
    if weather_info and weather_info.get("is_extreme") and today_instances:
        outdoor_keywords = ["户外", "运动", "跑步", "健身", "散步", "出行", "骑"]
        outdoor_tasks = [
            inst for inst in today_instances
            if any(kw in inst['title'] for kw in outdoor_keywords)
        ]
        if outdoor_tasks:
            briefing_parts.append(
                f"⚠️ 今天有恶劣天气（{weather_info['text']}），"
                f"以下户外任务建议调整：{'、'.join(t['title'] for t in outdoor_tasks)}"
            )

    if weekly_retro:
        briefing_parts.append(f"\n📋 上周回顾：\n{weekly_retro[:300]}")

    if monthly_retro:
        briefing_parts.append(f"\n📊 上月回顾：\n{monthly_retro[:300]}")

    if is_dnd:
        briefing_parts = ["早上好！"]  # 勿扰模式精简版
        if today_instances:
            briefing_parts.append(f"今天有 {len(today_instances)} 项待办。")

    message = "\n\n".join(briefing_parts)

    # 8. 发送
    try:
        from app.services.cconnect import send_text
        await send_text(message)
        logger.info("晨报已发送")
    except Exception as e:
        logger.error(f"晨报发送失败: {e}")


# ============================================================
# Todo 跟进扫描
# ============================================================

async def todo_followup_scanner():
    """
    每分钟扫描 scheduled_tasks，执行到期的 todo_followup。

    流程：
      1. 查询 status=pending, task_type=todo_followup, scheduled_at <= NOW()
      2. 对每条：发送跟进消息
      3. 更新 status=sent
    """
    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                SELECT st.id, st.reference_id, st.payload,
                       ti.todo_id
                FROM scheduled_tasks st
                JOIN todo_instances ti ON st.reference_id = ti.id
                WHERE st.task_type = 'todo_followup'
                  AND st.status = 'pending'
                  AND st.scheduled_at <= NOW()
                ORDER BY st.scheduled_at
                LIMIT 10
            """),
        )
        tasks = result.fetchall()

        for task in tasks:
            task_id, instance_id, payload, todo_id = task

            # 获取 todo 信息
            result2 = await session.execute(
                text("SELECT title FROM todos WHERE id = :id"),
                {"id": todo_id},
            )
            todo_row = result2.fetchone()
            if todo_row is None:
                continue

            title = todo_row[0]
            message = f"你的「{title}」应该刚结束，完成了吗？"

            # 重复未完成检测
            result3 = await session.execute(
                text("""
                    SELECT COUNT(*) FROM todo_instances ti2
                    JOIN scheduled_tasks st2 ON st2.reference_id = ti2.id
                    WHERE ti2.todo_id = :todo_id
                      AND ti2.date >= CURRENT_DATE - INTERVAL '7 days'
                      AND ti2.status IN ('cancelled', 'postponed')
                """),
                {"todo_id": todo_id},
            )
            cancel_count = result3.scalar()
            if cancel_count and cancel_count >= 3:
                message += " 这个任务最近有几次没完成，需要调整一下吗？"

            # 发送
            try:
                from app.services.cconnect import send_text
                await send_text(message)
                logger.info(f"Todo 跟进已发送: todo_id={todo_id}")
            except Exception as e:
                logger.error(f"Todo 跟进发送失败: {e}")
                continue

            # 更新状态
            await session.execute(
                text("""
                    UPDATE scheduled_tasks
                    SET status = 'sent', executed_at = NOW()
                    WHERE id = :id
                """),
                {"id": task_id},
            )

        await session.commit()
        if tasks:
            logger.info(f"Todo 跟进扫描完成，处理了 {len(tasks)} 条")


# ============================================================
# 晚间复盘触发
# ============================================================

async def evening_review():
    """
    晚间复盘触发 — 盘点今日任务，发送摘要并引导对话。

    流程：
      1. 查询今日所有 todo_instances
      2. 计算完成率
      3. 创建 conversation_session（session_type=evening_review）
      4. 发送摘要消息
      5. 后续对话由 RetrospectiveAgent 接管
    """
    import json
    today = _today()
    logger.info(f"触发 {today} 晚间复盘...")

    async with async_session_factory() as session:
        # 查询今日实例
        result = await session.execute(
            text("""
                SELECT ti.id, ti.status, t.title, g.name AS goal_name
                FROM todo_instances ti
                JOIN todos t ON ti.todo_id = t.id
                LEFT JOIN goals g ON t.goal_id = g.id
                WHERE ti.date = :today
                ORDER BY ti.id
            """),
            {"today": today},
        )
        instances = [
            {"id": r[0], "status": r[1], "title": r[2], "goal_name": r[3]}
            for r in result.fetchall()
        ]

        if not instances:
            logger.info("今日无待办，跳过晚间复盘")
            return

        total = len(instances)
        completed = sum(1 for i in instances if i["status"] == "completed")
        rate = round(completed / total * 100, 1) if total > 0 else 0

        # 未完成列表
        unfinished = [i for i in instances if i["status"] != "completed"]

        # 勿扰检查
        result_dnd = await session.execute(
            text("SELECT value FROM system_config WHERE key = 'dnd_mode'")
        )
        dnd_row = result_dnd.fetchone()
        is_dnd = dnd_row and dnd_row[0] == "true"

        # 创建 session
        meta = json.dumps({"flow_state": "REVIEWING"})
        result_sess = await session.execute(
            text("""
                INSERT INTO conversation_sessions (session_type, messages, metadata)
                VALUES (:stype, CAST('[]' AS jsonb), CAST(:meta AS jsonb))
                RETURNING id
            """),
            {"stype": "evening_review", "meta": meta},
        )
        session_id = result_sess.scalar()
        await session.commit()

    # 构建消息
    if is_dnd:
        msg = f"今天怎么样？有什么想记的吗？"
    else:
        parts = [f"🌙 晚间复盘 — {today.strftime('%m月%d日')}"]
        parts.append(f"今日任务：完成 {completed}/{total} 项（{rate}%）")

        if unfinished:
            parts.append("未完成：")
            for u in unfinished:
                parts.append(f"  • {u['title']}")

        # 完成的重要任务追问
        important_done = [i for i in instances if i["status"] == "completed" and i.get("goal_name")]
        if important_done:
            parts.append(f"\n完成了 {len(important_done)} 个与目标相关的任务，聊聊感受？")

        parts.append("\n有什么想记录的，或者直接说「写复盘」开始生成。")
        msg = "\n".join(parts)

    try:
        from app.services.cconnect import send_text
        await send_text(msg)
        logger.info(f"晚间复盘已发送: session_id={session_id}")
    except Exception as e:
        logger.error(f"晚间复盘发送失败: {e}")


# ============================================================
# 周复盘触发
# ============================================================

async def weekly_retro_check():
    """
    检查是否周日 + 晚间复盘时间 → 触发周复盘流程。

    由 evening_review job 同一时间触发，check 逻辑内嵌。
    如果是周日，先完成日复盘后再引导周复盘对话。
    """
    today = _today()
    if today.weekday() != 6:  # 0=Mon, 6=Sun
        return

    logger.info(f"今天是周日，触发周复盘检查...")

    async with async_session_factory() as session:
        # 检查本周日复盘是否已生成
        result = await session.execute(
            text("SELECT id FROM retrospectives WHERE type = 'daily' AND date = :d"),
            {"d": today},
        )
        if result.fetchone() is None:
            logger.info("日复盘尚未生成，等待日复盘完成")
            return

        # 创建周复盘 session
        import json
        meta = json.dumps({"flow_state": "REVIEWING"})
        await session.execute(
            text("""
                INSERT INTO conversation_sessions (session_type, messages, metadata)
                VALUES (:stype, CAST('[]' AS jsonb), CAST(:meta AS jsonb))
            """),
            {"stype": "retrospective_weekly", "meta": meta},
        )
        await session.commit()

    msg = (
        "📅 今天是周日，我们来做周复盘吧！\n\n"
        "回顾一下这周：\n"
        "  • 这周整体感觉怎么样？\n"
        "  • 最有成就感的一件事？\n"
        "  • 最想改进的一件事？\n"
        "  • 下周有什么期待？\n\n"
        "随便聊聊，说完「写复盘」我就帮你整理。"
    )

    try:
        from app.services.cconnect import send_text
        await send_text(msg)
        logger.info("周复盘触发消息已发送")
    except Exception as e:
        logger.error(f"周复盘发送失败: {e}")


# ============================================================
# 月复盘触发
# ============================================================

async def monthly_retro_check():
    """
    检查是否月末最后一天 → 触发月复盘。

    每天 evening_review 时检查：
      next_day = today + 1 天
      如果 next_day.month != today.month → 今天是月末
    """
    today = _today()
    next_day = date(today.year, today.month, 1)
    # 用下月第一天 - 1 天来判断
    if today.month == 12:
        next_month_first = date(today.year + 1, 1, 1)
    else:
        next_month_first = date(today.year, today.month + 1, 1)
    last_day = next_month_first - __import__('datetime').timedelta(days=1)

    if today != last_day:
        return

    logger.info(f"今天是月末 ({today})，触发月复盘...")

    async with async_session_factory() as session:
        import json
        meta = json.dumps({"flow_state": "REVIEWING"})
        await session.execute(
            text("""
                INSERT INTO conversation_sessions (session_type, messages, metadata)
                VALUES (:stype, CAST('[]' AS jsonb), CAST(:meta AS jsonb))
            """),
            {"stype": "retrospective_monthly", "meta": meta},
        )
        await session.commit()

    msg = (
        f"📊 今天是 {today.month} 月最后一天，来做月复盘吧！\n\n"
        "回顾这个月：\n"
        "  • 这个月最大的收获是什么？\n"
        "  • 有什么遗憾或未完成的目标？\n"
        "  • 下个月的关键方向？\n\n"
        "聊聊这个月，说完「写复盘」我来整理。"
    )

    try:
        from app.services.cconnect import send_text
        await send_text(msg)
        logger.info("月复盘触发消息已发送")
    except Exception as e:
        logger.error(f"月复盘发送失败: {e}")

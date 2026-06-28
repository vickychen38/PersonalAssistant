"""
可视化 Tool — matplotlib 图表生成。

支持的图表类型:
  body_weight_trend / body_fat_trend / bmi_trend → 折线图
  measurements_trend → 多线折线图
  todo_completion_trend → 折线+柱状组合
  monthly_spending → 饼图
  budget_usage → 水平条形图
  emotion_trend → 标注折线图
  goal_progress → 水平进度条
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import config

logger = logging.getLogger("visualization")

# 中文字体配置
try:
    import matplotlib
    matplotlib.use("Agg")
    # 尝试使用中文字体（优先 Noto Sans CJK，Linux 服务器通用）
    matplotlib.rcParams["font.sans-serif"] = [
        "Noto Sans CJK SC", "Noto Sans CJK TC", "Noto Serif CJK SC",
        "PingFang SC", "Heiti SC", "STHeiti", "Arial Unicode MS", "SimHei",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False
except Exception as e:
    logging.getLogger("visualization").warning(f"中文字体加载失败，图表可能乱码: {e}")


async def generate_chart(
    chart_type: str,
    data: Optional[Dict[str, Any]] = None,
    title: str = "",
    time_range: Optional[str] = None,
    highlight: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    生成图表，保存到 CHARTS_DIR。若未传 data，则自动从数据库查询。

    参数:
        chart_type: 图表类型
        data: 数据 dict（可选，不传则自动查询）
        title: 图表标题
        time_range: 时间范围描述
        highlight: 高亮标注

    返回:
        {"path": str, "filename": str} 或 {"error": str}
    """
    import matplotlib.pyplot as plt

    charts_dir = Path(config.charts_dir)
    charts_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{chart_type}_{timestamp}.png"
    filepath = charts_dir / filename

    try:
        # 若未传 data，自动从数据库查询
        if data is None:
            data = await _fetch_chart_data(chart_type)

        if "error" in data:
            return data

        if chart_type in ("body_weight_trend", "body_fat_trend", "bmi_trend"):
            _plot_line(data, title, _label_for(chart_type), filepath)
        elif chart_type == "measurements_trend":
            _plot_multi_line(data, title, filepath)
        elif chart_type == "todo_completion_trend":
            _plot_completion(data, title, filepath)
        elif chart_type == "monthly_spending":
            _plot_pie(data, title, filepath)
        elif chart_type == "budget_usage":
            _plot_hbar(data, title, filepath)
        elif chart_type == "emotion_trend":
            _plot_emotion(data, title, filepath)
        elif chart_type == "goal_progress":
            _plot_progress(data, title, filepath)
        else:
            return {"error": f"不支持的图表类型: {chart_type}，支持: body_weight_trend/body_fat_trend/bmi_trend/measurements_trend/todo_completion_trend/monthly_spending/budget_usage/emotion_trend/goal_progress"}

        logger.info(f"图表已生成: {filepath}")
        return {"path": str(filepath), "filename": filename, "chart_type": chart_type}

    except Exception as e:
        logger.error(f"图表生成失败 [{chart_type}]: {e}", exc_info=True)
        return {"error": str(e)}


async def generate_chart_and_send(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    生成图表并发送到微信（Agent 工具入口）。

    参数:
        args: {"chart_type": str, "title": str (可选)}

    返回:
        {"path": str, "filename": str, "sent": bool} 或 {"error": str}
    """
    chart_type = args.get("chart_type", "")
    title = args.get("title", "")

    result = await generate_chart(chart_type=chart_type, title=title)

    if "error" in result:
        return result

    # 发送图片到微信
    try:
        from app.services.cconnect import send_image
        from app.services.context_store import get_last_context
        ctx = get_last_context()
        ok = await send_image(
            result["path"],
            session_key=ctx.get("session_key", ""),
            project=ctx.get("project", ""),
        )
        result["sent"] = ok
        if ok:
            logger.info(f"图表已发送: {result['filename']}")
        else:
            logger.warning(f"图表发送失败: {result['filename']}")
    except Exception as e:
        logger.error(f"图表发送异常: {e}")
        result["sent"] = False

    return result


def _label_for(chart_type: str) -> str:
    """根据 chart_type 返回 y 轴标签。"""
    return {
        "body_weight_trend": "体重 (kg)",
        "body_fat_trend": "体脂率 (%)",
        "bmi_trend": "BMI",
    }.get(chart_type, chart_type)


async def _fetch_chart_data(chart_type: str) -> Dict[str, Any]:
    """从数据库查询图表所需数据。"""
    from datetime import date, timedelta
    from sqlalchemy import text
    from app.database import async_session_factory

    today = date.today()
    days = 30  # 默认取 30 天

    async with async_session_factory() as s:
        if chart_type in ("body_weight_trend", "body_fat_trend", "bmi_trend"):
            col = {"body_weight_trend": "weight", "body_fat_trend": "body_fat_pct",
                   "bmi_trend": "bmi"}[chart_type]
            r = await s.execute(
                text(f"SELECT date::date, {col} FROM health_daily "
                     f"WHERE {col} IS NOT NULL AND date >= :start ORDER BY date"),
                {"start": today - timedelta(days=days)},
            )
            rows = r.fetchall()
            if not rows:
                return {"error": f"暂无{'体重' if chart_type == 'body_weight_trend' else '体脂' if chart_type == 'body_fat_trend' else 'BMI'}数据，先记录一些吧"}
            return {"dates": [str(row[0]) for row in rows], "values": [float(row[1]) for row in rows]}

        elif chart_type == "measurements_trend":
            r = await s.execute(
                text("SELECT recorded_at::date, shoulder, chest, upper_arm, waist, hip, thigh, calf "
                     "FROM body_measurements WHERE recorded_at >= :start ORDER BY recorded_at"),
                {"start": today - timedelta(days=days)},
            )
            rows = r.fetchall()
            if not rows:
                return {"error": "暂无围度数据"}
            dates = [str(row[0]) for row in rows]
            parts = ["shoulder", "chest", "upper_arm", "waist", "hip", "thigh", "calf"]
            lines = {}
            for p in parts:
                vals = [float(row[i+1]) if row[i+1] else None for i, row in enumerate(rows)]
                if any(v is not None for v in vals):
                    lines[p] = vals
            return {"dates": dates, "lines": lines}

        elif chart_type == "todo_completion_trend":
            days_list = [(today - timedelta(days=i)) for i in range(days - 1, -1, -1)]
            d_strs = [str(d) for d in days_list]
            totals, completeds = [], []
            for d in days_list:
                r = await s.execute(
                    text("SELECT COUNT(*), SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) "
                         "FROM todo_instances WHERE scheduled_at::date = :d"),
                    {"d": d},
                )
                row = r.fetchone()
                totals.append(row[0] or 0)
                completeds.append(row[1] or 0)
            return {"dates": d_strs, "total": totals, "completed": completeds}

        elif chart_type == "monthly_spending":
            month = today.strftime("%Y-%m")
            r = await s.execute(
                text("SELECT COALESCE(bc.name, '未分类'), SUM(a.amount) "
                     "FROM accounting a LEFT JOIN budget_categories bc ON a.category_id = bc.id "
                     "WHERE a.month = :month GROUP BY bc.name ORDER BY SUM(a.amount) DESC"),
                {"month": month},
            )
            rows = r.fetchall()
            if not rows:
                return {"error": f"{month} 暂无支出数据"}
            return {"labels": [row[0] for row in rows], "values": [float(row[1]) for row in rows]}

        elif chart_type == "budget_usage":
            r = await s.execute(
                text("SELECT bc.name, bc.monthly_budget, "
                     "COALESCE((SELECT SUM(a.amount) FROM accounting a "
                     "WHERE a.category_id = bc.id AND a.month = :month), 0) "
                     "FROM budget_categories bc ORDER BY bc.name"),
                {"month": today.strftime("%Y-%m")},
            )
            rows = r.fetchall()
            if not rows:
                return {"error": "暂无预算类目"}
            return {
                "categories": [row[0] for row in rows],
                "spent": [float(row[2]) for row in rows],
                "budgets": [float(row[1]) for row in rows],
            }

        elif chart_type == "emotion_trend":
            r = await s.execute(
                text("SELECT date::date, energy_level, emotion_tags "
                     "FROM daily_state WHERE date >= :start ORDER BY date"),
                {"start": today - timedelta(days=days)},
            )
            rows = r.fetchall()
            if not rows:
                return {"error": "暂无情绪数据，先记录一下今天的状态吧"}
            return {
                "dates": [str(row[0]) for row in rows],
                "energy": [row[1] or 0 for row in rows],
                "tags": [row[2] or [] for row in rows],
            }

        elif chart_type == "goal_progress":
            r = await s.execute(
                text("SELECT name, "
                     "CASE WHEN status='completed' THEN 100 "
                     "WHEN status='abandoned' THEN 0 ELSE 50 END "
                     "FROM goals ORDER BY created_at"),
            )
            rows = r.fetchall()
            if not rows:
                return {"error": "暂无目标数据"}
            return {"goals": [row[0] for row in rows], "progress": [row[1] for row in rows]}

        return {"error": f"不支持的图表类型: {chart_type}"}


def _plot_line(data: Dict, title: str, ylabel: str, filepath: Path):
    """折线图 — 体重/体脂/BMI。"""
    import matplotlib.pyplot as plt
    dates = data.get("dates", [])
    values = data.get("values", [])

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(dates, values, marker="o", linewidth=2, color="#2563eb")
    ax.set_title(title or f"{ylabel} 趋势", fontsize=14)
    ax.set_xlabel("日期")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    plt.tight_layout()
    plt.savefig(filepath, dpi=100)
    plt.close()


def _plot_multi_line(data: Dict, title: str, filepath: Path):
    """多线折线图 — 围度趋势。"""
    import matplotlib.pyplot as plt
    dates = data.get("dates", [])
    lines = data.get("lines", {})  # {"腰围": [80, 79, ...], "胸围": [...]}

    fig, ax = plt.subplots(figsize=(10, 4))
    colors = ["#2563eb", "#dc2626", "#16a34a", "#ca8a04", "#9333ea", "#0891b2", "#db2777"]
    for i, (name, values) in enumerate(lines.items()):
        ax.plot(dates, values, marker="o", linewidth=2, label=name, color=colors[i % len(colors)])
    ax.set_title(title or "围度趋势", fontsize=14)
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    plt.tight_layout()
    plt.savefig(filepath, dpi=100)
    plt.close()


def _plot_completion(data: Dict, title: str, filepath: Path):
    """折线+柱状组合 — 任务完成趋势。"""
    import matplotlib.pyplot as plt
    dates = data.get("dates", [])
    total = data.get("total", [])
    completed = data.get("completed", [])

    fig, ax1 = plt.subplots(figsize=(10, 4))
    ax1.bar(dates, total, alpha=0.4, color="#93c5fd", label="总数")
    ax1.bar(dates, completed, alpha=0.8, color="#2563eb", label="完成")
    ax1.set_xlabel("日期")
    ax1.set_ylabel("任务数")

    ax2 = ax1.twinx()
    rates = [round(c / t * 100, 1) if t > 0 else 0 for c, t in zip(completed, total)]
    ax2.plot(dates, rates, marker="s", color="#dc2626", linewidth=2, label="完成率%")
    ax2.set_ylabel("完成率 %")
    ax2.set_ylim(0, 105)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    ax1.set_title(title or "任务完成趋势", fontsize=14)
    ax1.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    plt.tight_layout()
    plt.savefig(filepath, dpi=100)
    plt.close()


def _plot_pie(data: Dict, title: str, filepath: Path):
    """饼图 — 月度支出结构。"""
    import matplotlib.pyplot as plt
    labels = data.get("labels", [])
    values = data.get("values", [])

    fig, ax = plt.subplots(figsize=(8, 6))
    colors = ["#3b82f6", "#ef4444", "#22c55e", "#eab308", "#a855f7", "#06b6d4",
              "#f97316", "#84cc16"]
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct="%1.1f%%",
        colors=colors[:len(labels)], startangle=90,
    )
    ax.set_title(title or "支出结构", fontsize=14)
    plt.tight_layout()
    plt.savefig(filepath, dpi=100)
    plt.close()


def _plot_hbar(data: Dict, title: str, filepath: Path):
    """水平条形图 — 预算使用情况。"""
    import matplotlib.pyplot as plt
    categories = data.get("categories", [])
    spent = data.get("spent", [])
    budgets = data.get("budgets", [])

    fig, ax = plt.subplots(figsize=(8, 5))
    y_pos = range(len(categories))
    ax.barh(y_pos, spent, height=0.6, color="#ef4444", label="已用")
    ax.barh(y_pos, budgets, height=0.6, color="#d1d5db", alpha=0.5, label="预算")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(categories)
    ax.set_xlabel("金额")
    ax.set_title(title or "预算使用", fontsize=14)
    ax.legend()
    plt.tight_layout()
    plt.savefig(filepath, dpi=100)
    plt.close()


def _plot_emotion(data: Dict, title: str, filepath: Path):
    """标注折线图 — 情绪能量趋势。"""
    import matplotlib.pyplot as plt
    dates = data.get("dates", [])
    energy = data.get("energy", [])
    tags = data.get("tags", [])

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(dates, energy, marker="o", linewidth=2, color="#8b5cf6")
    for i, (d, e) in enumerate(zip(dates, energy)):
        if i < len(tags) and tags[i]:
            ax.annotate(", ".join(tags[i]), (d, e), textcoords="offset points",
                        xytext=(0, 10), fontsize=8, color="#666")
    ax.set_title(title or "情绪能量趋势", fontsize=14)
    ax.set_ylabel("能量 (1-5)")
    ax.set_ylim(0, 6)
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    plt.tight_layout()
    plt.savefig(filepath, dpi=100)
    plt.close()


def _plot_progress(data: Dict, title: str, filepath: Path):
    """水平进度条 — 目标进展。"""
    import matplotlib.pyplot as plt
    goals = data.get("goals", [])
    progress = data.get("progress", [])

    fig, ax = plt.subplots(figsize=(8, len(goals) * 0.6 + 1))
    colors = plt.cm.Blues([0.4 + 0.5 * p / 100 for p in progress])
    bars = ax.barh(goals, progress, color=colors)
    ax.bar_label(bars, labels=[f"{p}%" for p in progress], padding=5)
    ax.set_xlim(0, 105)
    ax.set_title(title or "目标进展", fontsize=14)
    plt.tight_layout()
    plt.savefig(filepath, dpi=100)
    plt.close()

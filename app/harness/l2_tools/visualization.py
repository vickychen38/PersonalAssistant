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
    # 尝试使用中文字体
    matplotlib.rcParams["font.sans-serif"] = [
        "PingFang SC", "Heiti SC", "STHeiti", "Arial Unicode MS", "SimHei"
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False
except Exception as e:
    logging.getLogger("visualization").warning(f"中文字体加载失败，图表可能乱码: {e}")


async def generate_chart(
    chart_type: str,
    data: Dict[str, Any],
    title: str = "",
    time_range: Optional[str] = None,
    highlight: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    生成图表，保存到 CHARTS_DIR。

    参数:
        chart_type: 图表类型
        data: 数据 dict（格式取决于 chart_type）
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
        if chart_type in ("body_weight_trend", "body_fat_trend", "bmi_trend"):
            _plot_line(data, title, chart_type.replace("_trend", ""), filepath)
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
            return {"error": f"不支持的图表类型: {chart_type}"}

        logger.info(f"图表已生成: {filepath}")
        return {"path": str(filepath), "filename": filename}

    except Exception as e:
        logger.error(f"图表生成失败: {e}")
        return {"error": str(e)}


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

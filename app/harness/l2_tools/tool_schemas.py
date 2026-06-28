"""
工具 JSON Schema 注册表 — 为每个工具定义完整的 OpenAI function schema。

被各 Agent 的 _build_tool_schemas() 引用，替代之前空的 properties。
"""

# ============================================================
# Todo 工具
# ============================================================

GET_TODOS_BY_DATE = {
    "name": "get_todos_by_date",
    "description": "查询指定日期的待办实例列表，包含关联的待办规则和目标信息",
    "parameters": {
        "type": "object",
        "properties": {
            "target_date": {
                "type": "string",
                "description": "查询日期，YYYY-MM-DD 格式，默认今天",
            },
        },
        "required": [],
    },
}

GET_GOALS = {
    "name": "get_goals",
    "description": "查询目标列表，可按状态筛选",
    "parameters": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "description": "筛选状态：active / paused / completed / abandoned，不传返回全部",
                "enum": ["active", "paused", "completed", "abandoned"],
            },
        },
        "required": [],
    },
}

CREATE_TODO = {
    "name": "create_todo",
    "description": "创建一条待办规则（可以是单次或重复任务）",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "待办标题，1-200 字符",
            },
            "type": {
                "type": "string",
                "description": "类型：one_time（单次）或 recurring（重复）",
                "enum": ["one_time", "recurring"],
            },
            "goal_id": {
                "type": "integer",
                "description": "关联的目标 ID（可选）",
            },
            "description": {
                "type": "string",
                "description": "详细描述（可选）",
            },
            "scheduled_at": {
                "type": "string",
                "description": "计划日期时间，ISO 格式如 2026-07-15T14:30:00+08:00（可选）",
            },
            "scheduled_time": {
                "type": "string",
                "description": "计划时间，HH:MM 格式如 14:30（可选）",
            },
            "recurrence_rule": {
                "type": "object",
                "description": "重复规则，如 {\"frequency\":\"daily\"} / {\"frequency\":\"weekly\",\"days\":[1,3,5]} / {\"frequency\":\"every_n_days\",\"n\":2}（recurring 类型时必填）",
            },
            "duration_minutes": {
                "type": "integer",
                "description": "预计时长（分钟），用于到时跟进提醒",
            },
        },
        "required": ["title", "type"],
    },
}

CREATE_TODO_INSTANCE = {
    "name": "create_todo_instance",
    "description": "为某天手动创建待办实例（通常由调度器自动生成，也可手动创建）",
    "parameters": {
        "type": "object",
        "properties": {
            "todo_id": {
                "type": "integer",
                "description": "待办规则 ID",
            },
            "scheduled_at": {
                "type": "string",
                "description": "实例日期，YYYY-MM-DD 格式如 2026-07-15",
            },
            "scheduled_time": {
                "type": "string",
                "description": "具体时间，HH:MM 格式如 14:30（可选）",
            },
        },
        "required": ["todo_id", "scheduled_at"],
    },
}

UPDATE_TODO_INSTANCE_STATUS = {
    "name": "update_todo_instance_status",
    "description": "更新待办实例的状态（完成/取消/推迟）",
    "parameters": {
        "type": "object",
        "properties": {
            "id": {
                "type": "integer",
                "description": "待办实例 ID",
            },
            "status": {
                "type": "string",
                "description": "新状态",
                "enum": ["completed", "cancelled", "postponed"],
            },
            "notes": {
                "type": "string",
                "description": "备注（完成感受、取消原因等，可选）",
            },
            "postponed_to": {
                "type": "string",
                "description": "推迟到哪个日期，YYYY-MM-DD 格式（status=postponed 时使用）",
            },
            "completed_at": {
                "type": "string",
                "description": "完成时间，ISO 格式（status=completed 时自动填当前时间）",
            },
        },
        "required": ["id", "status"],
    },
}

UPDATE_TODO_RECURRENCE_RULE = {
    "name": "update_todo_recurrence_rule",
    "description": "更新待办的重复规则（中风险操作，需用户确认）",
    "parameters": {
        "type": "object",
        "properties": {
            "id": {
                "type": "integer",
                "description": "待办规则 ID",
            },
            "new_rule": {
                "type": "object",
                "description": "新的重复规则，如 {\"frequency\":\"weekly\",\"days\":[2,4],\"time\":\"10:00\"}",
            },
        },
        "required": ["id", "new_rule"],
    },
}

CREATE_GOAL = {
    "name": "create_goal",
    "description": "创建一个目标",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "目标名称，1-200 字符",
            },
            "description": {
                "type": "string",
                "description": "详细描述（可选）",
            },
            "category": {
                "type": "string",
                "description": "分类标签，如 运动、学习、工作（可选）",
            },
            "target_date": {
                "type": "string",
                "description": "目标截止日期，ISO 格式（可选）",
            },
        },
        "required": ["name"],
    },
}

UPDATE_GOAL_STATUS = {
    "name": "update_goal_status",
    "description": "更新目标状态",
    "parameters": {
        "type": "object",
        "properties": {
            "id": {
                "type": "integer",
                "description": "目标 ID",
            },
            "status": {
                "type": "string",
                "description": "新状态",
                "enum": ["active", "paused", "completed", "abandoned"],
            },
        },
        "required": ["id", "status"],
    },
}

CREATE_SCHEDULED_TASK = {
    "name": "create_scheduled_task",
    "description": "创建一个计划任务（用于定时跟进、提醒等）",
    "parameters": {
        "type": "object",
        "properties": {
            "task_type": {
                "type": "string",
                "description": "任务类型，如 todo_followup",
            },
            "reference_id": {
                "type": "integer",
                "description": "关联的业务 ID（可选）",
            },
            "scheduled_at": {
                "type": "string",
                "description": "计划执行时间，ISO 格式如 2026-07-15T18:00:00+08:00",
            },
            "payload": {
                "type": "object",
                "description": "附加数据（可选）",
            },
        },
        "required": ["task_type", "scheduled_at"],
    },
}

# ============================================================
# Accounting 工具
# ============================================================

GET_ACCOUNTING_SUMMARY = {
    "name": "get_accounting_summary",
    "description": "查询指定月份的记账汇总，包含各分类金额和总计",
    "parameters": {
        "type": "object",
        "properties": {
            "month": {
                "type": "string",
                "description": "月份，YYYY-MM 格式如 2026-06，不传默认当月",
            },
        },
        "required": [],
    },
}

GET_BUDGET_STATUS = {
    "name": "get_budget_status",
    "description": "查询所有预算类目的使用情况（预算额、已用额、使用率）",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

CREATE_ACCOUNTING_ENTRY = {
    "name": "create_accounting_entry",
    "description": "记录一笔支出或收入。正数金额=支出，负数金额=收入",
    "parameters": {
        "type": "object",
        "properties": {
            "amount": {
                "type": "number",
                "description": "金额，正数=支出，负数=收入，如 25.5 表示支出 25.5 元",
            },
            "category_id": {
                "type": "integer",
                "description": "预算类目 ID（可选，可通过 get_budget_status 获取已有类目列表）",
            },
            "description": {
                "type": "string",
                "description": "消费描述，如 午餐-牛肉面、地铁通勤",
            },
            "recorded_at": {
                "type": "string",
                "description": "消费时间，ISO 格式如 2026-07-15T12:30:00+08:00，不传默认当前时间",
            },
        },
        "required": ["amount"],
    },
}

CREATE_BUDGET_CATEGORY = {
    "name": "create_budget_category",
    "description": "创建一个预算类目",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "类目名称，如 餐饮、交通、购物",
            },
            "monthly_budget": {
                "type": "number",
                "description": "月度预算金额，如 2000.00",
            },
            "alert_threshold": {
                "type": "number",
                "description": "告警阈值（小数），0.80 表示用到 80% 时告警，默认 0.80",
            },
        },
        "required": ["name", "monthly_budget"],
    },
}

UPDATE_BUDGET_CATEGORY = {
    "name": "update_budget_category",
    "description": "更新预算类目的预算或告警阈值（中风险操作，需用户确认）",
    "parameters": {
        "type": "object",
        "properties": {
            "id": {
                "type": "integer",
                "description": "类目 ID",
            },
            "name": {
                "type": "string",
                "description": "新名称（可选）",
            },
            "monthly_budget": {
                "type": "number",
                "description": "新月度预算（可选）",
            },
            "alert_threshold": {
                "type": "number",
                "description": "新告警阈值（可选）",
            },
        },
        "required": ["id"],
    },
}

# ============================================================
# Health 工具
# ============================================================

GET_HEALTH_DAILY = {
    "name": "get_health_daily",
    "description": "查询指定日期范围的每日健康指标（体重、体脂、BMI）",
    "parameters": {
        "type": "object",
        "properties": {
            "start_date": {
                "type": "string",
                "description": "开始日期，YYYY-MM-DD 格式",
            },
            "end_date": {
                "type": "string",
                "description": "结束日期，YYYY-MM-DD 格式，默认今天",
            },
        },
        "required": [],
    },
}

GET_BODY_MEASUREMENTS = {
    "name": "get_body_measurements",
    "description": "查询指定日期范围的身体围度记录（肩/胸/臂/腰/臀/腿/小腿）",
    "parameters": {
        "type": "object",
        "properties": {
            "start_date": {
                "type": "string",
                "description": "开始日期，YYYY-MM-DD 格式",
            },
            "end_date": {
                "type": "string",
                "description": "结束日期，YYYY-MM-DD 格式，默认今天",
            },
        },
        "required": [],
    },
}

RECORD_HEALTH_DAILY = {
    "name": "record_health_daily",
    "description": "记录当天的体重、体脂等健康指标",
    "parameters": {
        "type": "object",
        "properties": {
            "weight": {
                "type": "number",
                "description": "体重（kg），如 65.5",
            },
            "body_fat_pct": {
                "type": "number",
                "description": "体脂率（%），如 22.5，不传则不记录",
            },
            "date": {
                "type": "string",
                "description": "记录日期，YYYY-MM-DD 格式，默认今天",
            },
        },
        "required": [],
    },
}

RECORD_BODY_MEASUREMENTS = {
    "name": "record_body_measurements",
    "description": "记录身体围度数据，所有部位可选填",
    "parameters": {
        "type": "object",
        "properties": {
            "shoulder": {
                "type": "number",
                "description": "肩围（cm），精确到 0.1",
            },
            "chest": {
                "type": "number",
                "description": "胸围（cm）",
            },
            "upper_arm": {
                "type": "number",
                "description": "大臂围（cm）",
            },
            "waist": {
                "type": "number",
                "description": "腰围（cm）",
            },
            "hip": {
                "type": "number",
                "description": "臀围（cm）",
            },
            "thigh": {
                "type": "number",
                "description": "大腿围（cm）",
            },
            "calf": {
                "type": "number",
                "description": "小腿围（cm）",
            },
            "notes": {
                "type": "string",
                "description": "备注（可选）",
            },
            "recorded_at": {
                "type": "string",
                "description": "记录时间，ISO 格式（可选，默认当前时间）",
            },
        },
        "required": [],
    },
}

# ============================================================
# Retrospective 工具
# ============================================================

GET_DAILY_STATE = {
    "name": "get_daily_state",
    "description": "查询指定日期范围的情绪状态记录（情绪标签、能量等级）",
    "parameters": {
        "type": "object",
        "properties": {
            "start_date": {
                "type": "string",
                "description": "开始日期，YYYY-MM-DD 格式",
            },
            "end_date": {
                "type": "string",
                "description": "结束日期，YYYY-MM-DD 格式，默认今天",
            },
        },
        "required": [],
    },
}

GET_RETROSPECTIVES = {
    "name": "get_retrospectives",
    "description": "查询复盘记录，按日期范围和类型筛选",
    "parameters": {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "复盘类型：daily / weekly / monthly，不传返回全部",
                "enum": ["daily", "weekly", "monthly"],
            },
            "start_date": {
                "type": "string",
                "description": "开始日期，YYYY-MM-DD 格式",
            },
            "end_date": {
                "type": "string",
                "description": "结束日期，YYYY-MM-DD 格式",
            },
        },
        "required": [],
    },
}

CREATE_RETROSPECTIVE = {
    "name": "create_retrospective",
    "description": "创建一份复盘记录",
    "parameters": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "复盘日期，YYYY-MM-DD 格式",
            },
            "type": {
                "type": "string",
                "description": "复盘类型",
                "enum": ["daily", "weekly", "monthly"],
            },
            "content": {
                "type": "string",
                "description": "复盘正文（Markdown 格式）",
            },
            "completion_rate": {
                "type": "number",
                "description": "当日任务完成率（0-100），如 85.5",
            },
            "emotion_summary": {
                "type": "array",
                "items": {"type": "string"},
                "description": "情绪标签列表，如 [\"充实\",\"略疲劳\"]",
            },
            "key_insights": {
                "type": "string",
                "description": "关键洞察/收获（可选）",
            },
        },
        "required": ["date", "type", "content"],
    },
}

UPSERT_DAILY_STATE = {
    "name": "upsert_daily_state",
    "description": "记录或更新当天的情绪状态（情绪标签、能量等级、备注）",
    "parameters": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "日期，YYYY-MM-DD 格式，默认今天",
            },
            "emotion_tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "情绪标签，如 [\"开心\",\"疲惫\",\"焦虑\",\"充实\",\"平静\"]",
            },
            "emotion_notes": {
                "type": "string",
                "description": "情绪备注（可选），自由文本",
            },
            "energy_level": {
                "type": "integer",
                "description": "能量等级 1-5（1=很低，5=很高）",
                "minimum": 1,
                "maximum": 5,
            },
        },
        "required": [],
    },
}

GET_RECENT_AGENT_ACTIONS = {
    "name": "get_recent_agent_actions",
    "description": "查询最近的工具调用记录，用于了解 Agent 操作历史",
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "返回条数，默认 20",
            },
        },
        "required": [],
    },
}

# ============================================================
# 通用工具
# ============================================================

GET_SYSTEM_CONFIG = {
    "name": "get_system_config",
    "description": "读取系统配置项的值",
    "parameters": {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "配置键名，如 morning_briefing_time / dnd_mode / city。不传返回全部",
            },
        },
        "required": [],
    },
}

GET_USER_KNOWLEDGE = {
    "name": "get_user_knowledge",
    "description": "查询用户知识库中某类别的信息（如运动习惯、作息规律）",
    "parameters": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "知识类别，如 运动习惯 / 饮食习惯 / 作息规律 / 健康目标 / 工作模式 / 消费习惯",
            },
        },
        "required": [],
    },
}

UPSERT_USER_KNOWLEDGE = {
    "name": "upsert_user_knowledge",
    "description": "写入或更新用户知识库中的一条信息",
    "parameters": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "知识类别，如 运动习惯 / 饮食习惯 / 消费习惯",
            },
            "key": {
                "type": "string",
                "description": "知识键名，如 健身频率 / 口味偏好",
            },
            "value": {
                "type": "string",
                "description": "知识内容，如 每周3次私教课 / 喜欢清淡口味",
            },
            "source_context": {
                "type": "string",
                "description": "来源上下文（可选），记录这条知识是从哪次对话中提取的",
            },
        },
        "required": ["category", "key", "value"],
    },
}

GET_WEATHER = {
    "name": "get_weather",
    "description": "查询指定城市的实时天气（温度、湿度、天气状况、极端天气预警）",
    "parameters": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名，如 北京 / 上海 / 深圳。不传则用系统配置中的默认城市",
            },
        },
        "required": [],
    },
}

GENERATE_CHART = {
    "name": "generate_chart",
    "description": "生成 matplotlib 图表并发送到微信。当前功能开发中，暂不可用",
    "parameters": {
        "type": "object",
        "properties": {
            "chart_type": {
                "type": "string",
                "description": "图表类型：pie（饼图）/ line（折线图）/ bar（柱状图）/ trend（趋势图）/ budget（预算图）/ completion（完成率图）/ health（健康趋势图）",
                "enum": ["pie", "line", "bar", "trend", "budget", "completion", "health"],
            },
        },
        "required": ["chart_type"],
    },
}

SEND_MESSAGE = {
    "name": "send_message",
    "description": "向用户发送文本消息。每条回复必须以此工具结尾",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "要发送的消息内容（Markdown 格式）",
            },
        },
        "required": ["content"],
    },
}

# ============================================================
# 注册表
# ============================================================

# 所有工具的 schema 字典
ALL_TOOL_SCHEMAS = {
    # Todo
    "get_todos_by_date": GET_TODOS_BY_DATE,
    "get_goals": GET_GOALS,
    "create_todo": CREATE_TODO,
    "create_todo_instance": CREATE_TODO_INSTANCE,
    "update_todo_instance_status": UPDATE_TODO_INSTANCE_STATUS,
    "update_todo_recurrence_rule": UPDATE_TODO_RECURRENCE_RULE,
    "create_goal": CREATE_GOAL,
    "update_goal_status": UPDATE_GOAL_STATUS,
    "create_scheduled_task": CREATE_SCHEDULED_TASK,
    # Accounting
    "get_accounting_summary": GET_ACCOUNTING_SUMMARY,
    "get_budget_status": GET_BUDGET_STATUS,
    "create_accounting_entry": CREATE_ACCOUNTING_ENTRY,
    "create_budget_category": CREATE_BUDGET_CATEGORY,
    "update_budget_category": UPDATE_BUDGET_CATEGORY,
    # Health
    "get_health_daily": GET_HEALTH_DAILY,
    "get_body_measurements": GET_BODY_MEASUREMENTS,
    "record_health_daily": RECORD_HEALTH_DAILY,
    "record_body_measurements": RECORD_BODY_MEASUREMENTS,
    # Retrospective
    "get_daily_state": GET_DAILY_STATE,
    "get_retrospectives": GET_RETROSPECTIVES,
    "create_retrospective": CREATE_RETROSPECTIVE,
    "upsert_daily_state": UPSERT_DAILY_STATE,
    "get_recent_agent_actions": GET_RECENT_AGENT_ACTIONS,
    # 跨领域通用
    "get_system_config": GET_SYSTEM_CONFIG,
    "get_user_knowledge": GET_USER_KNOWLEDGE,
    "upsert_user_knowledge": UPSERT_USER_KNOWLEDGE,
    "get_weather": GET_WEATHER,
    "generate_chart": GENERATE_CHART,
    "send_message": SEND_MESSAGE,
}


def build_tool_schemas(tool_names: list[str]) -> list[dict]:
    """
    根据工具名列表，构建 OpenAI function calling 格式的 tool schemas。

    参数:
        tool_names: 工具名列表，如 ["get_todos_by_date", "create_todo", "send_message"]

    返回:
        [{"type": "function", "function": {...}}, ...]
    """
    schemas = []
    for name in tool_names:
        func_def = ALL_TOOL_SCHEMAS.get(name)
        if func_def:
            schemas.append({
                "type": "function",
                "function": func_def,
            })
        else:
            # 未知工具回退到空 schema
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"Tool: {name}",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": True,
                    },
                },
            })
    return schemas

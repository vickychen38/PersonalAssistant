-- ============================================
-- 逐念 个人 AI 助理系统 · 数据库初始化 DDL
-- Version: 1.0.0
-- ============================================

BEGIN;

-- ============================================
-- 1. 目标表
-- ============================================
CREATE TABLE goals (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(200) NOT NULL,
    description  TEXT,
    category     VARCHAR(100),
    status       VARCHAR(20) NOT NULL DEFAULT 'active',
    target_date  DATE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
-- status 取值：active / paused / completed / abandoned

-- ============================================
-- 2. 待办规则表
-- ============================================
CREATE TABLE todos (
    id               SERIAL PRIMARY KEY,
    goal_id          INTEGER REFERENCES goals(id),
    title            VARCHAR(200) NOT NULL,
    description      TEXT,
    type             VARCHAR(20) NOT NULL,
    recurrence_rule  JSONB,
    scheduled_date   DATE,
    scheduled_time   TIME,
    duration_minutes INTEGER,
    status           VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
-- type 取值：one_time / recurring
-- status 取值：active / paused / completed / cancelled
-- recurrence_rule 示例：
--   {"frequency":"daily"}
--   {"frequency":"weekly","days":[2,4],"time":"12:00"}
--   {"frequency":"every_n_days","n":2}

CREATE INDEX idx_todos_goal_id ON todos(goal_id);
CREATE INDEX idx_todos_status ON todos(status);

-- ============================================
-- 3. 待办实例表
-- ============================================
CREATE TABLE todo_instances (
    id             SERIAL PRIMARY KEY,
    todo_id        INTEGER NOT NULL REFERENCES todos(id),
    date           DATE NOT NULL,
    scheduled_time TIME,
    status         VARCHAR(20) NOT NULL DEFAULT 'pending',
    completed_at   TIMESTAMP WITH TIME ZONE,
    postponed_to   DATE,
    notes          TEXT,
    created_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
-- status 取值：pending / completed / cancelled / postponed

CREATE INDEX idx_todo_instances_date_status ON todo_instances(date, status);
CREATE INDEX idx_todo_instances_todo_id_date ON todo_instances(todo_id, date);

-- ============================================
-- 4. 每日情绪状态表
-- ============================================
CREATE TABLE daily_state (
    id            SERIAL PRIMARY KEY,
    date          DATE NOT NULL UNIQUE,
    emotion_tags  TEXT[],
    emotion_notes TEXT,
    energy_level  SMALLINT,
    created_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
-- emotion_tags 示例：ARRAY['疲惫','焦虑']
-- energy_level 取值：1-5

-- ============================================
-- 5. 复盘表
-- ============================================
CREATE TABLE retrospectives (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    type            VARCHAR(10) NOT NULL,
    content         TEXT NOT NULL,
    completion_rate DECIMAL(5,2),
    emotion_summary TEXT[],
    key_insights    TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (date, type)
);
-- type 取值：daily / weekly / monthly
-- metadata 存储会话交接文档等

-- ============================================
-- 6. 每日健康指标表
-- ============================================
CREATE TABLE health_daily (
    id           SERIAL PRIMARY KEY,
    date         DATE NOT NULL UNIQUE,
    weight       DECIMAL(5,2),
    body_fat_pct DECIMAL(5,2),
    bmi          DECIMAL(5,2),
    recorded_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
-- bmi 由应用层计算写入，公式：weight / ((height_cm / 100) ** 2)，保留 1 位小数

-- ============================================
-- 7. 围度记录表
-- ============================================
CREATE TABLE body_measurements (
    id          SERIAL PRIMARY KEY,
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    shoulder    DECIMAL(5,1),
    chest       DECIMAL(5,1),
    upper_arm   DECIMAL(5,1),
    waist       DECIMAL(5,1),
    hip         DECIMAL(5,1),
    thigh       DECIMAL(5,1),
    calf        DECIMAL(5,1),
    notes       TEXT
);
-- 所有部位字段均可为空，支持不完整输入
-- shoulder=肩围，chest=胸围，upper_arm=大臂，waist=肚脐腰围
-- hip=臀围，thigh=大腿围，calf=小腿围

CREATE INDEX idx_body_measurements_recorded_at ON body_measurements(recorded_at);

-- ============================================
-- 8. 预算类目表
-- ============================================
CREATE TABLE budget_categories (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE,
    monthly_budget  DECIMAL(10,2),
    alert_threshold DECIMAL(3,2) NOT NULL DEFAULT 0.80,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- ============================================
-- 9. 记账流水表
-- ============================================
CREATE TABLE accounting (
    id          SERIAL PRIMARY KEY,
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    amount      DECIMAL(10,2) NOT NULL,
    category_id INTEGER REFERENCES budget_categories(id),
    description TEXT,
    source      VARCHAR(20) NOT NULL DEFAULT 'text',
    month       CHAR(7) NOT NULL
);
-- amount 正数为支出，负数为收入
-- source 取值：text / image
-- month 格式 YYYY-MM，由应用层写入时计算

CREATE INDEX idx_accounting_category_month ON accounting(category_id, month);
CREATE INDEX idx_accounting_month ON accounting(month);

-- ============================================
-- 10. 用户知识库
-- ============================================
CREATE TABLE user_knowledge (
    id             SERIAL PRIMARY KEY,
    category       VARCHAR(100) NOT NULL,
    key            VARCHAR(200) NOT NULL,
    value          TEXT NOT NULL,
    source_context TEXT,
    created_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (category, key)
);

-- ============================================
-- 11. 系统配置表
-- ============================================
CREATE TABLE system_config (
    key        VARCHAR(100) PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- 初始配置数据
INSERT INTO system_config (key, value) VALUES
    ('morning_briefing_time',    '07:30'),
    ('evening_review_time',      '22:00'),
    ('city',                     ''),
    ('dnd_mode',                 'false'),
    ('budget_default_threshold', '0.80');

-- ============================================
-- 12. 对话上下文表
-- ============================================
CREATE TABLE conversation_sessions (
    id           SERIAL PRIMARY KEY,
    session_type VARCHAR(50) NOT NULL,
    started_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    ended_at     TIMESTAMP WITH TIME ZONE,
    messages     JSONB NOT NULL DEFAULT '[]',
    metadata     JSONB NOT NULL DEFAULT '{}'
);
-- session_type 取值：casual / evening_review / retrospective_daily /
--   retrospective_weekly / retrospective_monthly
-- messages 格式：[{"role":"user","content":"...","ts":"..."},...]
-- messages 最多保留 50 条，超出时压缩
-- metadata 存储 flow_state（状态机状态）和 pending_action（中风险确认）
-- ended_at 为空表示进行中

CREATE INDEX idx_conv_sessions_ended_at ON conversation_sessions(ended_at);

-- ============================================
-- 13. 计划任务表
-- ============================================
CREATE TABLE scheduled_tasks (
    id           SERIAL PRIMARY KEY,
    task_type    VARCHAR(100) NOT NULL,
    reference_id INTEGER,
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status       VARCHAR(20) NOT NULL DEFAULT 'pending',
    executed_at  TIMESTAMP WITH TIME ZONE,
    payload      JSONB,
    created_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
-- task_type 取值：todo_followup / budget_alert / morning_briefing /
--   evening_review / weekly_retro / monthly_retro
-- status 取值：pending / sent / cancelled / failed

CREATE INDEX idx_scheduled_tasks_scheduled_status
    ON scheduled_tasks(scheduled_at, status);

-- ============================================
-- 14. Agent 行为日志表（L5 观测层）
-- ============================================
CREATE TABLE agent_action_logs (
    id          SERIAL PRIMARY KEY,
    session_id  INTEGER REFERENCES conversation_sessions(id),
    agent_type  VARCHAR(50),
    tool_name   VARCHAR(100),
    input       JSONB,
    output      JSONB,
    success     BOOLEAN NOT NULL,
    error_msg   TEXT,
    duration_ms INTEGER,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_action_logs_session_id ON agent_action_logs(session_id);
CREATE INDEX idx_agent_action_logs_created_at ON agent_action_logs(created_at);

COMMIT;

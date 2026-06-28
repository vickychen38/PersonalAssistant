-- ============================================
-- 逐念 · 时间字段精度细化迁移
-- 将 date 字段升级为 timestamptz
-- Version: 1.1.0
-- ============================================

BEGIN;

-- 1. goals.target_date → TIMESTAMPTZ
ALTER TABLE goals ALTER COLUMN target_date TYPE TIMESTAMP WITH TIME ZONE
    USING (target_date::timestamp with time zone);

-- 2. todo_instances.date → scheduled_at TIMESTAMPTZ
ALTER TABLE todo_instances ALTER COLUMN date TYPE TIMESTAMP WITH TIME ZONE
    USING (date::timestamp with time zone);
ALTER TABLE todo_instances RENAME COLUMN date TO scheduled_at;

-- 3. todo_instances.postponed_to → TIMESTAMPTZ
ALTER TABLE todo_instances ALTER COLUMN postponed_to TYPE TIMESTAMP WITH TIME ZONE
    USING (postponed_to::timestamp with time zone);

-- 4. todos.scheduled_date → scheduled_at TIMESTAMPTZ
ALTER TABLE todos ALTER COLUMN scheduled_date TYPE TIMESTAMP WITH TIME ZONE
    USING (scheduled_date::timestamp with time zone);
ALTER TABLE todos RENAME COLUMN scheduled_date TO scheduled_at;

COMMIT;

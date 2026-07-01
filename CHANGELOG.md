# 更新日志

## v1.6 — 2026-07-01

### 修复
- **P0：主动推送全部失败**：cc-connect 上下文存储了测试假数据（`project: "PA"`、`session_key: "partial_test"`），导致调度器（晨报/晚间复盘/待办提醒/周月复盘）所有推送返回 404。清除假数据，新增 `cc_connect_project` 配置项，所有推送改用 `_push_context()` 从 config 回退
- **P0：`create_scheduled_task` SQL 语法错误**：`:payload::jsonb` 异步驱动不兼容，改为 `CAST(:payload AS jsonb)`
- **P1：任务到点无提醒**：系统只会在任务结束后发跟进（"做完了吗？"），缺少开始提醒。`daily_todo_gen` 现在为每个有时间的任务创建两条 scheduled_task：`todo_reminder`（到点提醒）+ `todo_followup`（结束后跟进）
- **P1：StreamHandler 启动错误**：`logging.StreamHandler(_MillisFormatter(...))` 参数传错，改为先创建 handler 再 setFormatter，消除启动时的 `AttributeError: '_MillisFormatter' object has no attribute 'write'`
- **P2：Webhook ACP relay 兼容**：ACP agent 的 webhook payload 用 `session_id` 而非 `session_key`，导致 `save_webhook_context` 始终收到空值跳过保存

### 新增
- 预算表 `budget_categories` 新增 `month` 字段（YYYY-MM），支持每月独立预算。同月同名类目唯一约束。`create_budget_category` 自动填入当前月份，查询函数按月份过滤
- 配置新增 `cc_connect_project` 项，默认值 `"assistant-relay"`

### 清理
- 数据库去重：删除重复记账（ID 5 日用）、重复 todo（测评豆包 ID 9）、重复目标（ID 1）、recurring 私教课（ID 4,5）
- 体重表仅保留 6/30 和 7/1 数据
- `todo_followup_scanner` 重构：统一处理 `todo_reminder` 和 `todo_followup` 两种 task_type

---

## v1.5 — 2026-06-30

### 修复
- Agent 主动推送：调度器（晨报/晚间复盘/待办跟进/周月复盘）改用 `to_user` 发消息，不再用 `context_token` 回复令牌
- `send_image` / `send_tts` 补齐 `to_user` 参数，图表生成主动推送可用
- ChatAgent `send_message` 工具补齐 `to_user`
- `_post_to_cc` 日志引用未定义变量的 bug
- `router.py` `route_message` 底部重复 return 死代码
- 每次 DeepSeek API 调用自动注入当前北京时间，解决模型时间盲问题

### 清理
- Agent prompt 中移除冗余的手动日期注入（`deepseek.py` 已全局处理）

### 文档
- 新增 README.md（项目架构、快速开始、功能概览）
- 新增 CHANGELOG.md

### 工程
- 更新 .gitignore，排除 `logs/`、`charts/`、`.pytest_cache/`

---

## v1.4 — 2026-06-29

### 新增
- **ChatAgent 闲聊**：日常对话、心情倾诉，支持联网搜索（`web_search` 工具）
- **全链路 trace log**：每条消息传递路径可追踪（`trace_id`），日志文件持久化，支持 `/logs` API 和 `/logN` 斜杠命令实时查看
- **图表生成**：`generate_chart` 工具，基于 Matplotlib 生成消费分类饼图等
- **工具 JSON Schema 注册表**：统一管理和验证工具定义

### 测试
- 核心模块测试：37 个通过，47 个总计

### 修复
- 日志时间戳精确到毫秒
- 工具调用异常处理增强

---

## v1.3 — 2026-06-28

### 变更
- 数据模型时间字段精度升级：`date` → `timestamptz`
- 路由模型启用思考链（thinking），`max_tokens` 提升至 10000
- `agent_action_logs` 日志写入、cc-connect 上下文管理、晚间复盘强制执行

---

## v1.2 — 2026-06-25

### 新增
- Webhook 支持 sync 模式：ACP Agent relay 可同步等待 AI 回复

### 修复
- P0：路由模型禁用思考链，修正 `ROUTER_PROMPT` 意图定义

---

## v1.1 — 2026-06-24

### 修复
- **P0**：消除 `__import__` 动态导入，改为静态 import
- **P0**：DeepSeek 消息过滤非标准字段（仅保留 OpenAI 兼容 key）
- **P1**：熔断器改用 `asyncio.Lock` 防止竞态
- **P1**：熔断器 `CircuitBreakerOpenError` 不再被静默吞掉
- **P1**：`compressor` 改用 `tiktoken` 精确 token 计数
- **P1**：调度器时间越界修复 — 小时取模 24
- `append_message` 加 `FOR UPDATE` 行级锁防并发写冲突

### 新增
- L2 观测工具 (`observation_tools`)
- L2 天气工具包装层

---

## v1.0 — 2026-06-23

### 初始版本

- 逐念个人 AI 助理系统基本框架
- 5 个 AI Agent：待办、记账、健康、复盘、闲聊
- cc-connect 微信桥接接入
- DeepSeek API 集成（pro / flash 双模型）
- PostgreSQL 数据存储
- APScheduler 定时任务调度
- 斜杠命令支持（`/dnd`、`/city`、`/config`）
- L1-L6 分层能力框架
- 和风天气集成

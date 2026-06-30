# 逐念 — 个人 AI 助理系统

一个通过微信接入的个人 AI 助理，管理待办、记账、健康数据与成长复盘。

**微信发消息 → cc-connect 桥接 → 逐念 AI 路由 → DeepSeek 思考 → 微信回复**

---

## 功能概览

| 模块 | Agent | 功能 |
|------|-------|------|
| 📋 待办 | `TodoAgent` | 任务管理、目标追踪、每日晨报、待办跟进 |
| 💰 记账 | `AccountingAgent` | 消费记录、预算管理、超支预警 |
| 🏃 健康 | `HealthAgent` | 体重、体脂、围度记录，BMI 计算，趋势追踪 |
| 📝 复盘 | `RetrospectiveAgent` | 日/周/月复盘，情绪感知，成长追踪 |
| 💬 闲聊 | `ChatAgent` | 日常对话、心情倾诉、联网搜索 |

### 定时主动推送

| 任务 | 说明 |
|------|------|
| 每日晨报 | 当日待办 + 天气 + 昨日未完成 + 周/月复盘摘要 |
| 晚间复盘 | 当日完成率 + 未完成任务盘点 + 引导复盘对话 |
| 待办跟进 | 任务结束后询问完成情况 |
| 周复盘 | 周日触发周复盘对话 |
| 月复盘 | 月末触发月复盘对话 |

### 斜杠命令

| 命令 | 说明 |
|------|------|
| `/dnd on` / `/dnd off` | 勿扰模式开关 |
| `/city <城市名>` | 设置天气城市 |
| `/config morning 08:00` | 设置晨报时间 |
| `/config evening 21:00` | 设置晚间复盘时间 |
| `/log<N>` | 查看最近 N 行日志（如 `/log20`） |

---

## 系统架构

```
微信
  ↕
cc-connect (port 9527)
  ↕  Unix socket /send
逐念 FastAPI (port 8000)
  ├── webhook.py          # 消息接收与分发
  ├── router.py           # 斜杠命令 + AI 意图路由
  ├── scheduler/          # APScheduler 定时任务
  ├── agents/             # 5 个 AI Agent
  └── harness/            # 分层能力框架
        ├── L1 上下文       # 会话上下文注入
        ├── L2 工具         # 工具函数 + JSON Schema 注册
        ├── L3 编排         # 路由、流程、确认
        ├── L4 记忆         # 会话管理、知识存储
        ├── L5 评估         # 日志审计、质量检查
        └── L6 恢复         # 重试、熔断、校验
  ↕
DeepSeek API (v4-pro / v4-flash)
  ↕
PostgreSQL (assistant_db)
```

---

## 快速开始

### 环境要求

- Python 3.11+
- PostgreSQL 14+
- Node.js 22+（cc-connect）
- [cc-connect](https://github.com/chenhg5/cc-connect) 已安装并运行

### 安装

```bash
git clone https://github.com/vickychen38/PersonalAssistant.git
cd PersonalAssistant

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入实际值
```

### 配置环境变量

```bash
# DeepSeek API
DEEPSEEK_API_KEY=sk-your-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_PRO_MODEL=deepseek-v4-pro
DEEPSEEK_FLASH_MODEL=deepseek-v4-flash

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://assistant:password@localhost:5432/assistant_db

# 和风天气（可选）
HEWEATHER_API_KEY=your-key

# cc-connect 桥接
CC_CONNECT_API_URL=unix:///root/.cc-connect/run/api.sock
CC_CONNECT_WEBHOOK_SECRET=your-secret
WECHAT_USER_ID=your-wechat-user-id

# 用户参数
USER_HEIGHT_CM=158

# 应用
APP_PORT=8000
APP_ENV=production
```

### 初始化数据库

```bash
source venv/bin/activate
python3 -c "
from app.database import init_db
import asyncio
asyncio.run(init_db())
"
```

### 启动

```bash
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 健康检查

```bash
curl http://localhost:8000/health
# → {"status":"ok","service":"逐念"}
```

---

## 运行测试

```bash
source venv/bin/activate
pytest tests/ -v
```

---

## 技术栈

- **Web**: FastAPI + Uvicorn
- **AI**: DeepSeek API（OpenAI 兼容）
- **数据库**: PostgreSQL + SQLAlchemy + asyncpg
- **定时任务**: APScheduler
- **图表**: Matplotlib
- **天气**: 和风天气 API

---

## 目录结构

```
PersonalAssistant/
├── app/
│   ├── main.py              # FastAPI 入口 + 生命周期
│   ├── config.py            # 配置（从 .env 读取）
│   ├── database.py          # 数据库引擎 + 会话
│   ├── webhook.py           # cc-connect webhook 接收
│   ├── agents/              # AI Agent 实现
│   ├── services/            # 外部服务（DeepSeek、cc-connect、天气）
│   ├── models/              # SQLAlchemy 数据模型
│   ├── scheduler/           # 定时任务
│   └── harness/             # L1-L6 分层能力框架
├── migrations/              # SQL 迁移脚本
├── tests/                   # 测试
├── charts/                  # 图表输出目录
└── logs/                    # 运行时日志
```

---

## License

MIT

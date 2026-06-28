"""
测试：服务模块 — context_store, trace, deepseek parsing。
"""
import json
import pytest
import tempfile
from pathlib import Path


class TestContextStore:
    """context_store 持久化。"""

    @pytest.mark.asyncio
    async def test_save_and_read(self):
        from app.services.context_store import save_webhook_context, get_last_context
        save_webhook_context(
            session_key="sk_test123", project="PA",
            from_user="vicky", context_token="ct_abc",
        )
        ctx = get_last_context()
        assert ctx["session_key"] == "sk_test123"
        assert ctx["project"] == "PA"
        assert ctx["from_user"] == "vicky"
        assert ctx["context_token"] == "ct_abc"

    @pytest.mark.asyncio
    async def test_empty_defaults(self):
        from app.services.context_store import get_last_context
        # 即使 store 为空也不抛异常
        ctx = get_last_context()
        assert isinstance(ctx, dict)
        assert "session_key" in ctx
        assert "context_token" in ctx

    @pytest.mark.asyncio
    async def test_partial_save(self):
        from app.services.context_store import save_webhook_context, get_last_context
        save_webhook_context(session_key="partial_test")
        ctx = get_last_context()
        assert ctx["session_key"] == "partial_test"


class TestTrace:
    """Trace 追踪模块。"""

    def test_new_trace_id_unique(self):
        from app.services.trace import new_trace_id, Trace
        ids = [new_trace_id() for _ in range(100)]
        assert len(set(ids)) == 100
        assert all(len(tid) == 8 for tid in ids)

    def test_trace_logs_steps(self):
        from app.services.trace import Trace
        import logging
        logging.basicConfig(level=logging.DEBUG)

        trace = Trace(message_id="test_001")
        trace.log("webhook", "收到消息", user="vicky")
        trace.log("router", "路由", agent="todo")
        trace.done("ok")

        assert len(trace._steps) == 2
        assert trace._steps == ["webhook", "router"]

    def test_trace_elapsed(self):
        from app.services.trace import Trace
        import time
        trace = Trace(message_id="test_002")
        time.sleep(0.01)
        assert trace.total_ms > 0


class TestDeepseekMessageCleaning:
    """deepseek._build_params 消息清洗。"""

    def test_clean_messages_strips_extra_fields(self):
        from app.services.deepseek import _build_params
        msgs = [
            {"role": "user", "content": "hello", "ts": "2026-01-01", "extra": "x"},
        ]
        params = _build_params("sys", msgs, None, "flash", max_tokens=100)
        # 验证消息被清洗
        cleaned = params["messages"][1]  # [0] is system
        assert "role" in cleaned
        assert "content" in cleaned
        assert "ts" not in cleaned
        assert "extra" not in cleaned

    def test_message_truncation(self):
        from app.services.deepseek import _build_params
        msgs = [{"role": "user", "content": f"msg{i}"} for i in range(50)]
        params = _build_params("sys", msgs, None, "flash", max_tokens=100)
        # 系统消息 + 最多 20 条
        assert len(params["messages"]) <= 21

    def test_model_resolution(self):
        from app.services.deepseek import _resolve_model
        from app.config import config
        assert _resolve_model("flash") == config.deepseek_flash_model
        assert _resolve_model("pro") == config.deepseek_pro_model
        assert _resolve_model("custom-model") == "custom-model"


class TestChartDateFix:
    """get_health_daily 日期修正（数据库测试，需 --run-db 标记）。"""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="需要 session-scoped event loop")
    async def test_wrong_year_fallback(self):
        from app.harness.l2_tools.health_tools import get_health_daily
        result = await get_health_daily("2024-01-01", "2024-12-31")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="需要 session-scoped event loop")
    async def test_no_args_defaults(self):
        from app.harness.l2_tools.health_tools import get_health_daily
        result = await get_health_daily()
        assert isinstance(result, list)

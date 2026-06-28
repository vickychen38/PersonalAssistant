"""
测试：Router 斜杠命令 + 路由逻辑。
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestSlashCommands:
    """斜杠命令解析。"""

    @pytest.mark.asyncio
    async def test_dnd_on(self):
        from app.harness.l3_orchestration.router import _handle_slash_command
        with patch("app.harness.l2_tools.system_tools.update_system_config", new_callable=AsyncMock):
            result = await _handle_slash_command("/dnd on")
            assert result is not None
            assert "勿扰" in result

    @pytest.mark.asyncio
    async def test_dnd_off(self):
        from app.harness.l3_orchestration.router import _handle_slash_command
        with patch("app.harness.l2_tools.system_tools.update_system_config", new_callable=AsyncMock):
            result = await _handle_slash_command("/dnd off")
            assert result is not None
            assert "勿扰" in result

    @pytest.mark.asyncio
    async def test_city_set(self):
        from app.harness.l3_orchestration.router import _handle_slash_command
        with patch("app.harness.l2_tools.system_tools.update_system_config", new_callable=AsyncMock):
            result = await _handle_slash_command("/city 上海")
            assert result is not None
            assert "上海" in result

    @pytest.mark.asyncio
    async def test_log_command(self):
        from app.harness.l3_orchestration.router import _handle_slash_command
        result = await _handle_slash_command("/log5")
        assert result is not None
        assert "日志" in result

    @pytest.mark.asyncio
    async def test_log_default(self):
        from app.harness.l3_orchestration.router import _handle_slash_command
        result = await _handle_slash_command("/log")
        assert result is not None
        assert "日志" in result

    @pytest.mark.asyncio
    async def test_not_a_slash_command(self):
        from app.harness.l3_orchestration.router import _handle_slash_command
        result = await _handle_slash_command("今天天气怎么样")
        assert result is None

    @pytest.mark.asyncio
    async def test_config_morning(self):
        from app.harness.l3_orchestration.router import _handle_slash_command
        with patch("app.harness.l2_tools.system_tools.update_system_config", new_callable=AsyncMock), \
             patch("app.scheduler.setup.reschedule_time_job", new_callable=AsyncMock):
            result = await _handle_slash_command("/config morning 08:00")
            assert result is not None
            assert "08:00" in result


class TestAIRoute:
    """AI 路由意图分类。"""

    @pytest.mark.asyncio
    async def test_todo_intent(self):
        with patch("app.services.deepseek.chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = {"content": "todo"}
            from app.harness.l3_orchestration.router import ai_route
            result = await ai_route("明天要做什么")
            assert result == "todo"

    @pytest.mark.asyncio
    async def test_accounting_intent(self):
        with patch("app.services.deepseek.chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = {"content": "accounting"}
            from app.harness.l3_orchestration.router import ai_route
            result = await ai_route("花了50块钱")
            assert result == "accounting"

    @pytest.mark.asyncio
    async def test_unclear_fallback(self):
        with patch("app.services.deepseek.chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = {"content": "unclear"}
            from app.harness.l3_orchestration.router import ai_route
            result = await ai_route("你好")
            assert result == "unclear"


class TestRouteMessage:
    """route_message 主入口。"""

    @pytest.mark.asyncio
    async def test_slash_command_priority(self):
        from app.harness.l3_orchestration.router import route_message
        with patch("app.harness.l2_tools.system_tools.update_system_config", new_callable=AsyncMock):
            result = await route_message("/dnd on")
            assert result["route_type"] == "slash_command"
            assert result["reply"] is not None
            assert result["agent_type"] is None

    @pytest.mark.asyncio
    async def test_ai_route_fallback(self):
        from app.harness.l3_orchestration.router import route_message
        with patch("app.harness.l3_orchestration.router.ai_route", new_callable=AsyncMock) as mock_route:
            mock_route.return_value = "todo"
            result = await route_message("帮我加个任务")
            assert result["route_type"] == "ai_route"
            assert result["agent_type"] == "todo"

    @pytest.mark.asyncio
    async def test_session_continue(self):
        from app.harness.l3_orchestration.router import route_message
        session = {
            "id": 1,
            "session_type": "evening_review",
            "messages": [],
            "metadata": {},
        }
        result = await route_message("写复盘", session)
        assert result["route_type"] == "session_continue"
        assert result["agent_type"] == "retrospective"


class TestDispatchToAgent:
    """dispatch_to_agent。"""

    @pytest.mark.asyncio
    async def test_unknown_agent(self):
        from app.harness.l3_orchestration.router import dispatch_to_agent
        result = await dispatch_to_agent("unknown_agent", "hello")
        assert "不知道" in result

    @pytest.mark.asyncio
    async def test_dispatch_to_todo(self):
        from app.harness.l3_orchestration.router import dispatch_to_agent
        with patch("app.agents.TodoAgent") as mock_cls:
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value="好的，记下了")
            mock_cls.return_value = mock_agent

            from app.harness.l3_orchestration.router import AGENT_MAP
            AGENT_MAP["todo"] = mock_cls

            result = await dispatch_to_agent("todo", "加个任务")
            assert result == "好的，记下了"

"""
测试：Todo 工具 CRUD（真实数据库）。

注意：部分测试需要 session-scoped event loop，pytest-asyncio 1.4.0 不支持。
数据库集成测试用 --run-db 标记手动运行。
"""
import pytest
from datetime import date

pytestmark = pytest.mark.skip(reason="需要 session-scoped event loop (pytest-asyncio >= 1.5)")


class TestCreateTodo:
    """create_todo 创建待办规则。"""

    @pytest.mark.asyncio
    async def test_create_one_time_todo(self):
        from app.harness.l2_tools.todo_tools import create_todo, CreateTodoInput
        data = CreateTodoInput(title="测试单次任务", type="one_time",
                               scheduled_at=date.today().isoformat(),
                               scheduled_time="14:30")
        result = await create_todo(data)
        assert "error" not in result
        assert result["title"] == "测试单次任务"
        assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_create_recurring_todo(self):
        from app.harness.l2_tools.todo_tools import create_todo, CreateTodoInput
        data = CreateTodoInput(title="每日复盘", type="recurring",
                               recurrence_rule={"frequency": "daily", "time": "21:00"})
        result = await create_todo(data)
        assert "error" not in result
        assert result["title"] == "每日复盘"


class TestGetTodosByDate:
    """get_todos_by_date 查询。"""

    @pytest.mark.asyncio
    async def test_no_todos_for_future(self):
        from app.harness.l2_tools.todo_tools import get_todos_by_date
        result = await get_todos_by_date("2099-01-01")
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_default_today(self):
        from app.harness.l2_tools.todo_tools import get_todos_by_date
        result = await get_todos_by_date()
        assert isinstance(result, list)


class TestCreateGoal:
    """create_goal 创建目标。"""

    @pytest.mark.asyncio
    async def test_create_simple_goal(self):
        from app.harness.l2_tools.todo_tools import create_goal, CreateGoalInput
        # target_date 类型已改为 timestamptz，接受 ISO 字符串
        data = CreateGoalInput(name="减脂到55kg", category="运动")
        result = await create_goal(data)
        assert "error" not in result
        assert result["name"] == "减脂到55kg"

    @pytest.mark.asyncio
    async def test_get_goals(self):
        from app.harness.l2_tools.todo_tools import get_goals
        result = await get_goals()
        assert isinstance(result, list)


class TestUpdateTodoInstanceStatus:
    """update_todo_instance_status 更新实例状态。"""

    @pytest.mark.asyncio
    async def test_invalid_instance_id(self):
        from app.harness.l2_tools.todo_tools import update_todo_instance_status
        result = await update_todo_instance_status(99999, "completed")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_completed_status(self):
        from app.harness.l2_tools.todo_tools import (create_todo, create_todo_instance,
                                                       update_todo_instance_status,
                                                       CreateTodoInput, CreateTodoInstanceInput)
        today = date.today().isoformat()
        # 创建 todo + instance
        todo = await create_todo(CreateTodoInput(title="临时测试", type="one_time",
                                                   scheduled_at=today))
        assert "error" not in todo
        inst = await create_todo_instance(CreateTodoInstanceInput(
            todo_id=todo["id"], scheduled_at=today))
        assert "error" not in inst

        # 标记完成
        result = await update_todo_instance_status(inst["id"], "completed",
                                                     notes="干完了")
        assert "error" not in result
        assert result["status"] == "completed"

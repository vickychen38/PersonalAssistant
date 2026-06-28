"""
测试：Pydantic 模型别名兼容 + 工具 Schema 注册表。
"""
import pytest


class TestCreateTodoInput:
    """CreateTodoInput: scheduled_date 别名兼容。"""

    def test_new_name_scheduled_at(self):
        from app.harness.l2_tools.todo_tools import CreateTodoInput
        todo = CreateTodoInput(title="测试", type="one_time", scheduled_at="2026-07-15")
        assert todo.scheduled_at == "2026-07-15"

    def test_old_name_scheduled_date_alias(self):
        from app.harness.l2_tools.todo_tools import CreateTodoInput
        todo = CreateTodoInput(title="测试", type="recurring", scheduled_date="2026-08-01")
        assert todo.scheduled_at == "2026-08-01"

    def test_missing_required_fields(self):
        from app.harness.l2_tools.todo_tools import CreateTodoInput
        with pytest.raises(Exception):
            CreateTodoInput(title="测试")  # 缺少 type


class TestCreateTodoInstanceInput:
    """CreateTodoInstanceInput: date 别名兼容。"""

    def test_new_name_scheduled_at(self):
        from app.harness.l2_tools.todo_tools import CreateTodoInstanceInput
        inst = CreateTodoInstanceInput(todo_id=1, scheduled_at="2026-07-01")
        assert inst.scheduled_at == "2026-07-01"

    def test_old_name_date_alias(self):
        from app.harness.l2_tools.todo_tools import CreateTodoInstanceInput
        inst = CreateTodoInstanceInput(todo_id=2, date="2026-07-15", scheduled_time="14:30")
        assert inst.scheduled_at == "2026-07-15"

    def test_both_names_populate_by_name(self):
        from app.harness.l2_tools.todo_tools import CreateTodoInstanceInput
        # scheduled_at 和 date 都传时，用 field name
        inst = CreateTodoInstanceInput(todo_id=1, scheduled_at="2026-08-01")
        assert inst.scheduled_at == "2026-08-01"


class TestToolSchemaRegistry:
    """工具 Schema 注册表完整性。"""

    def test_all_registered_tools_have_schema(self):
        from app.harness.l2_tools.tool_schemas import ALL_TOOL_SCHEMAS, build_tool_schemas
        assert len(ALL_TOOL_SCHEMAS) >= 28

    def test_build_tool_schemas_known(self):
        from app.harness.l2_tools.tool_schemas import build_tool_schemas
        schemas = build_tool_schemas(["get_todos_by_date", "create_todo", "send_message"])
        assert len(schemas) == 3
        for s in schemas:
            assert s["type"] == "function"
            assert "name" in s["function"]
            assert "parameters" in s["function"]

    def test_build_tool_schemas_unknown_fallback(self):
        from app.harness.l2_tools.tool_schemas import build_tool_schemas
        schemas = build_tool_schemas(["nonexistent_tool"])
        assert len(schemas) == 1
        assert schemas[0]["function"]["parameters"]["additionalProperties"] is True

    def test_chart_types_are_data_types_not_styles(self):
        from app.harness.l2_tools.tool_schemas import GENERATE_CHART
        valid = GENERATE_CHART["parameters"]["properties"]["chart_type"]["enum"]
        assert "body_weight_trend" in valid
        assert "monthly_spending" in valid
        assert "emotion_trend" in valid
        assert "pie" not in valid  # 不是样式名

    def test_send_message_has_content_required(self):
        from app.harness.l2_tools.tool_schemas import SEND_MESSAGE
        assert "content" in SEND_MESSAGE["parameters"]["required"]


class TestUpdateStatusInput:
    """UpdateTodoInstanceStatusInput 验证。"""

    def test_valid_statuses(self):
        from app.harness.l2_tools.todo_tools import UpdateTodoInstanceStatusInput
        for s in ["completed", "cancelled", "postponed"]:
            inp = UpdateTodoInstanceStatusInput(id=1, status=s)
            assert inp.status == s

    def test_invalid_status_rejected(self):
        from app.harness.l2_tools.todo_tools import UpdateTodoInstanceStatusInput
        with pytest.raises(Exception):
            UpdateTodoInstanceStatusInput(id=1, status="deleted")

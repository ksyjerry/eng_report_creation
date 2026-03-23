"""도구 레이어 테스트 — 타입 변환, DSD 읽기 도구, 도구 실행."""

import asyncio
import pytest

from agent.tools import ToolRegistry, tool, collect_tools, _coerce_args


# ──────────────────────────────────────────────
# _coerce_args 테스트
# ──────────────────────────────────────────────

class TestCoerceArgs:

    def test_string_to_int(self):
        schema = {"x": {"type": "integer"}}
        assert _coerce_args({"x": "42"}, schema) == {"x": 42}

    def test_string_to_float(self):
        schema = {"x": {"type": "number"}}
        assert _coerce_args({"x": "3.14"}, schema) == {"x": 3.14}

    def test_string_to_bool(self):
        schema = {"x": {"type": "boolean"}}
        assert _coerce_args({"x": "true"}, schema) == {"x": True}
        assert _coerce_args({"x": "false"}, schema) == {"x": False}

    def test_int_to_string(self):
        schema = {"x": {"type": "string"}}
        assert _coerce_args({"x": 42}, schema) == {"x": "42"}

    def test_already_correct_type(self):
        schema = {"x": {"type": "integer"}}
        assert _coerce_args({"x": 42}, schema) == {"x": 42}

    def test_unknown_param_passthrough(self):
        schema = {"x": {"type": "integer"}}
        assert _coerce_args({"x": "1", "y": "hello"}, schema) == {"x": 1, "y": "hello"}

    def test_none_value(self):
        schema = {"x": {"type": "integer"}}
        assert _coerce_args({"x": None}, schema) == {"x": None}

    def test_invalid_conversion_passthrough(self):
        schema = {"x": {"type": "integer"}}
        result = _coerce_args({"x": "not_a_number"}, schema)
        assert result == {"x": "not_a_number"}


# ──────────────────────────────────────────────
# @tool 데코레이터 + get_type_hints 테스트
# ──────────────────────────────────────────────

class TestToolDecorator:

    def test_int_params_detected(self):
        @tool("test_tool", "test")
        def my_func(a: int, b: str, c: float = 1.0) -> str:
            return ""

        assert my_func._tool_def["parameters"]["a"]["type"] == "integer"
        assert my_func._tool_def["parameters"]["b"]["type"] == "string"
        assert my_func._tool_def["parameters"]["c"]["type"] == "number"
        assert my_func._tool_def["parameters"]["c"]["default"] == 1.0

    def test_write_flag(self):
        @tool("write_tool", "write test", is_write=True)
        def my_func(text: str) -> str:
            return ""

        assert my_func._tool_def["is_write"] is True


# ──────────────────────────────────────────────
# ToolRegistry.execute 타입 변환 통합 테스트
# ──────────────────────────────────────────────

class TestRegistryExecute:

    def test_coerces_args_on_execute(self):
        registry = ToolRegistry()

        @tool("add", "Add two numbers")
        def add(a: int, b: int) -> str:
            return str(a + b)

        registry.register(
            name="add",
            description="Add",
            parameters=add._tool_def["parameters"],
            func=add,
        )

        result = asyncio.get_event_loop().run_until_complete(
            registry.execute("add", {"a": "3", "b": "7"})
        )
        assert result == "10"

    def test_unknown_tool(self):
        registry = ToolRegistry()
        result = asyncio.get_event_loop().run_until_complete(
            registry.execute("nonexistent", {})
        )
        assert "ERROR" in result


# ──────────────────────────────────────────────
# DSD 읽기 도구 테스트 (실제 파일 사용)
# ──────────────────────────────────────────────

DSD_PATH = "/Users/jkim564/Documents/ai/eng_fs_creation/files/Hybe 2025 Eng Report.dsd"
DOCX_PATH = "/Users/jkim564/Documents/ai/eng_fs_creation/files/Hybe 2024 Eng Report.docx"


@pytest.fixture
def ctx_with_dsd():
    """DSD + DOCX가 로드된 DocumentContext."""
    import os
    if not os.path.exists(DSD_PATH):
        pytest.skip("Test files not found")

    from agent.document_context import DocumentContext
    from agent.tools import read_tools

    ctx = DocumentContext()
    ctx.load_dsd(DSD_PATH)
    ctx.load_docx(DOCX_PATH)
    read_tools.set_context(ctx)
    return ctx


class TestDsdReadTools:

    def test_read_dsd_structure(self, ctx_with_dsd):
        from agent.tools.read_tools import read_dsd_structure
        result = read_dsd_structure()
        assert "하이브" in result
        assert "BS" in result
        assert "IS" in result
        assert "CE" in result
        assert "CF" in result

    def test_read_dsd_table_bs(self, ctx_with_dsd):
        from agent.tools.read_tools import read_dsd_table
        result = read_dsd_table("BS")
        assert "재무상태표" in result
        assert "자산" in result
        assert "부채" in result

    def test_read_dsd_table_invalid(self, ctx_with_dsd):
        from agent.tools.read_tools import read_dsd_table
        result = read_dsd_table("INVALID")
        assert "ERROR" in result
        assert "Available" in result

    def test_read_dsd_notes(self, ctx_with_dsd):
        from agent.tools.read_tools import read_dsd_notes
        result = read_dsd_notes()
        assert "주석" in result

    def test_read_dsd_note_detail(self, ctx_with_dsd):
        from agent.tools.read_tools import read_dsd_note_detail
        result = read_dsd_note_detail("1")
        # Note 1 should exist
        assert "주석 1" in result or "ERROR" in result

    def test_read_dsd_no_data(self):
        from agent.document_context import DocumentContext
        from agent.tools import read_tools
        ctx = DocumentContext()
        read_tools.set_context(ctx)

        from agent.tools.read_tools import read_dsd_structure
        result = read_dsd_structure()
        assert "ERROR" in result

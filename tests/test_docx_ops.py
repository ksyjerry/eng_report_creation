"""agent/tools/docx_ops/ 단위 테스트."""

import pytest
from lxml import etree

from agent.tools.docx_ops.xml_helpers import OOXML_NS, w, find_w, findall_w, get_cell_text
from agent.tools.docx_ops.cell_writer import set_cell_text, clear_cell_text
from agent.tools.docx_ops.row_cloner import clone_row, delete_row
from agent.tools.docx_ops.text_replacer import replace_text_in_element
from agent.tools.docx_ops.column_mapper import build_column_mapping, ColumnMapping


W_NS = OOXML_NS["w"]


def _make_tc(text: str, bold: bool = False) -> etree._Element:
    """테스트용 <w:tc> 생성."""
    tc = etree.Element(w("tc"), nsmap={"w": W_NS})
    p = etree.SubElement(tc, w("p"))
    r = etree.SubElement(p, w("r"))
    if bold:
        rpr = etree.SubElement(r, w("rPr"))
        etree.SubElement(rpr, w("b"))
    t = etree.SubElement(r, w("t"))
    t.text = text
    return tc


def _make_table(rows_data: list[list[str]], col_widths: list[int] | None = None) -> etree._Element:
    """테스트용 <w:tbl> 생성."""
    tbl = etree.Element(w("tbl"), nsmap={"w": W_NS})

    if col_widths:
        grid = etree.SubElement(tbl, w("tblGrid"))
        for width in col_widths:
            gc = etree.SubElement(grid, w("gridCol"))
            gc.set(w("w"), str(width))

    for row in rows_data:
        tr = etree.SubElement(tbl, w("tr"))
        for cell_text in row:
            tc = _make_tc(cell_text)
            tr.append(tc)

    return tbl


# ==================================================================
# cell_writer 테스트
# ==================================================================

class TestCellWriter:

    def test_set_cell_text_basic(self):
        tc = _make_tc("old text")
        set_cell_text(tc, "new text")
        assert get_cell_text(tc) == "new text"

    def test_set_cell_text_preserves_bold(self):
        tc = _make_tc("old", bold=True)
        set_cell_text(tc, "new")
        assert get_cell_text(tc) == "new"
        # bold 서식이 보존되어야 함
        assert tc.find(f".//{w('b')}") is not None

    def test_set_cell_text_empty(self):
        tc = _make_tc("some text")
        set_cell_text(tc, "")
        assert get_cell_text(tc) == ""

    def test_clear_cell_text(self):
        tc = _make_tc("some text")
        clear_cell_text(tc)
        assert get_cell_text(tc) == ""

    def test_set_cell_text_multi_run(self):
        """여러 Run이 있는 셀 — 마지막 Run에 텍스트 배치."""
        tc = etree.Element(w("tc"), nsmap={"w": W_NS})
        p = etree.SubElement(tc, w("p"))
        # Run 1
        r1 = etree.SubElement(p, w("r"))
        t1 = etree.SubElement(r1, w("t"))
        t1.text = "first "
        # Run 2
        r2 = etree.SubElement(p, w("r"))
        t2 = etree.SubElement(r2, w("t"))
        t2.text = "second"

        set_cell_text(tc, "replaced")
        assert get_cell_text(tc) == "replaced"

    def test_set_cell_text_no_runs(self):
        """Run이 없는 셀 — 새 Run 생성."""
        tc = etree.Element(w("tc"), nsmap={"w": W_NS})
        p = etree.SubElement(tc, w("p"))

        set_cell_text(tc, "new text")
        assert get_cell_text(tc) == "new text"


# ==================================================================
# row_cloner 테스트
# ==================================================================

class TestRowCloner:

    def test_clone_row_basic(self):
        tbl = _make_table([
            ["Header1", "Header2"],
            ["Row1-1", "Row1-2"],
            ["Row2-1", "Row2-2"],
        ])

        clone_row(tbl, source_row_idx=1, insert_after_idx=2,
                  cell_texts={0: "New-1", 1: "New-2"})

        rows = findall_w(tbl, "w:tr")
        assert len(rows) == 4  # 3 + 1 추가
        # 새 행은 index 3 (row 2 다음)
        new_row_cells = findall_w(rows[3], "w:tc")
        assert get_cell_text(new_row_cells[0]) == "New-1"
        assert get_cell_text(new_row_cells[1]) == "New-2"

    def test_clone_row_preserves_original(self):
        tbl = _make_table([
            ["A", "B"],
            ["C", "D"],
        ])

        clone_row(tbl, source_row_idx=0, insert_after_idx=0)

        rows = findall_w(tbl, "w:tr")
        assert len(rows) == 3
        # 원본은 변경 안 됨
        orig_cells = findall_w(rows[0], "w:tc")
        assert get_cell_text(orig_cells[0]) == "A"

    def test_clone_row_clears_vmerge(self):
        """복제된 행에서 vMerge가 제거되어야 함."""
        tbl = etree.Element(w("tbl"), nsmap={"w": W_NS})
        tr = etree.SubElement(tbl, w("tr"))
        tc = etree.SubElement(tr, w("tc"))
        tc_pr = etree.SubElement(tc, w("tcPr"))
        vm = etree.SubElement(tc_pr, w("vMerge"))
        vm.set(w("val"), "restart")
        p = etree.SubElement(tc, w("p"))
        r = etree.SubElement(p, w("r"))
        t = etree.SubElement(r, w("t"))
        t.text = "merged"

        clone_row(tbl, source_row_idx=0, insert_after_idx=0)

        rows = findall_w(tbl, "w:tr")
        new_row = rows[1]
        new_tc_pr = find_w(findall_w(new_row, "w:tc")[0], "w:tcPr")
        assert find_w(new_tc_pr, "w:vMerge") is None

    def test_delete_row(self):
        tbl = _make_table([
            ["A", "B"],
            ["C", "D"],
            ["E", "F"],
        ])

        delete_row(tbl, 1)

        rows = findall_w(tbl, "w:tr")
        assert len(rows) == 2
        # row 0 = "A", "B" 유지
        assert get_cell_text(findall_w(rows[0], "w:tc")[0]) == "A"
        # row 1 = "E", "F" (원래 row 2)
        assert get_cell_text(findall_w(rows[1], "w:tc")[0]) == "E"

    def test_delete_row_out_of_range(self):
        tbl = _make_table([["A"]])
        with pytest.raises(IndexError):
            delete_row(tbl, 5)


# ==================================================================
# text_replacer 테스트
# ==================================================================

class TestTextReplacer:

    def test_simple_replacement(self):
        root = etree.Element(w("body"), nsmap={"w": W_NS})
        p = etree.SubElement(root, w("p"))
        r = etree.SubElement(p, w("r"))
        t = etree.SubElement(r, w("t"))
        t.text = "December 31, 2024 and 2023"

        changed = replace_text_in_element(root, [("2024", "2025"), ("2023", "2024")])

        assert changed is True
        assert t.text == "December 31, 2025 and 2024"

    def test_cross_run_replacement(self):
        """'2024'가 두 Run에 걸쳐 '20' + '24'로 분리된 경우."""
        root = etree.Element(w("body"), nsmap={"w": W_NS})
        p = etree.SubElement(root, w("p"))
        r1 = etree.SubElement(p, w("r"))
        t1 = etree.SubElement(r1, w("t"))
        t1.text = "Year 20"
        r2 = etree.SubElement(p, w("r"))
        t2 = etree.SubElement(r2, w("t"))
        t2.text = "24 ended"

        changed = replace_text_in_element(root, [("2024", "2025")])

        assert changed is True
        full_text = t1.text + t2.text
        assert "2025" in full_text
        assert "2024" not in full_text

    def test_no_match(self):
        root = etree.Element(w("body"), nsmap={"w": W_NS})
        p = etree.SubElement(root, w("p"))
        r = etree.SubElement(p, w("r"))
        t = etree.SubElement(r, w("t"))
        t.text = "No years here"

        changed = replace_text_in_element(root, [("2024", "2025")])

        assert changed is False
        assert t.text == "No years here"

    def test_cascade_prevention(self):
        """'2023'→'2024', '2024'→'2025' 동시 적용 시 cascade 방지."""
        root = etree.Element(w("body"), nsmap={"w": W_NS})
        p = etree.SubElement(root, w("p"))
        r = etree.SubElement(p, w("r"))
        t = etree.SubElement(r, w("t"))
        t.text = "2023 and 2024"

        changed = replace_text_in_element(root, [("2023", "2024"), ("2024", "2025")])

        assert changed is True
        # "2024"→"2025" 먼저, "2023"→"2024" 그 다음 (정렬 역순)
        # 결과: "2024 and 2025"
        assert t.text == "2024 and 2025"


# ==================================================================
# column_mapper 테스트
# ==================================================================

class TestColumnMapper:

    def test_no_spacers(self):
        tbl = _make_table(
            [["A", "B", "C"]],
            col_widths=[4500, 2000, 2000],
        )
        mapping = build_column_mapping(tbl)

        assert mapping.num_physical_cols == 3
        assert mapping.num_logical_cols == 3
        assert mapping.spacer_indices == []

    def test_with_spacers(self):
        tbl = _make_table(
            [["Label", "", "Value1", "", "Value2"]],
            col_widths=[4500, 58, 2000, 58, 2000],
        )
        mapping = build_column_mapping(tbl)

        assert mapping.num_physical_cols == 5
        assert mapping.spacer_indices == [1, 3]
        assert mapping.num_logical_cols == 3
        assert mapping.logical_to_physical[0] == [0]
        assert mapping.logical_to_physical[1] == [2]
        assert mapping.logical_to_physical[2] == [4]

    def test_no_grid_info_fallback(self):
        """tblGrid 없는 경우 → 첫 행 셀 수로 fallback."""
        tbl = _make_table([["A", "B", "C"]])  # col_widths 없음
        mapping = build_column_mapping(tbl)

        assert mapping.num_logical_cols == 3
        assert mapping.spacer_indices == []

    def test_custom_threshold(self):
        tbl = _make_table(
            [["A", "", "B"]],
            col_widths=[4500, 150, 2000],
        )
        # threshold=200이면 150은 spacer
        mapping_200 = build_column_mapping(tbl, spacer_threshold=200)
        assert mapping_200.spacer_indices == [1]

        # threshold=100이면 150은 spacer 아님
        mapping_100 = build_column_mapping(tbl, spacer_threshold=100)
        assert mapping_100.spacer_indices == []


# ==================================================================
# ToolRegistry 테스트
# ==================================================================

class TestToolRegistry:

    @pytest.mark.asyncio
    async def test_register_and_execute(self):
        from agent.tools import ToolRegistry

        registry = ToolRegistry()
        registry.register(
            name="test_tool",
            description="A test tool",
            parameters={"x": {"type": "integer"}},
            func=lambda x: f"result: {x}",
        )

        result = await registry.execute("test_tool", {"x": 42})
        assert result == "result: 42"

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        from agent.tools import ToolRegistry

        registry = ToolRegistry()
        result = await registry.execute("nonexistent", {})
        assert "ERROR" in result
        assert "nonexistent" in result

    @pytest.mark.asyncio
    async def test_tool_error_handling(self):
        from agent.tools import ToolRegistry

        def bad_tool():
            raise ValueError("something went wrong")

        registry = ToolRegistry()
        registry.register("bad", "fails", {}, bad_tool)

        result = await registry.execute("bad", {})
        assert "ERROR" in result
        assert "ValueError" in result

    def test_tool_decorator(self):
        from agent.tools import tool

        @tool("my_tool", "does stuff", is_write=True)
        def my_tool(text: str, count: int = 5) -> str:
            return f"{text}:{count}"

        assert my_tool._tool_def["name"] == "my_tool"
        assert my_tool._tool_def["is_write"] is True
        assert my_tool._tool_def["parameters"]["text"]["type"] == "string"
        assert my_tool._tool_def["parameters"]["count"]["type"] == "integer"

    def test_collect_tools(self):
        from agent.tools import tool, collect_tools
        import types

        @tool("fn1", "desc1")
        def fn1(x: str) -> str:
            return x

        @tool("fn2", "desc2", is_write=True)
        def fn2(y: int) -> str:
            return str(y)

        module = types.ModuleType("fake_module")
        module.fn1 = fn1
        module.fn2 = fn2

        registry = collect_tools([module])
        assert "fn1" in registry.list_tools()
        assert "fn2" in registry.list_tools()

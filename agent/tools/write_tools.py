"""
쓰기 도구 — LLM이 DOCX 문서를 수정하는 도구들.
모든 수정은 docx_ops/ 저수준 함수를 통해 수행하여 서식 보존.
"""

from __future__ import annotations

from agent.tools import tool
from agent.tools.docx_ops.cell_writer import set_cell_text as _set_cell_text
from agent.tools.docx_ops.row_cloner import clone_row as _clone_row, delete_row as _delete_row
from agent.tools.docx_ops.text_replacer import replace_text_in_element
from agent.tools.docx_ops.xml_helpers import findall_w, get_cell_text


_ctx = None


def set_context(ctx) -> None:
    global _ctx
    _ctx = ctx


def _get_ctx():
    if _ctx is None:
        raise RuntimeError("DocumentContext not initialized")
    return _ctx


@tool("set_cell_text", "테이블 셀의 텍스트를 변경합니다. 기존 서식을 보존합니다.", is_write=True)
def set_cell_text(table_index: int, row: int, physical_col: int, text: str) -> str:
    """셀 텍스트 변경."""
    ctx = _get_ctx()
    try:
        tc = ctx.get_cell(table_index, row, physical_col)
        # 레이블 보호
        existing = get_cell_text(tc).strip()
        clean = existing.replace(",", "").replace("(", "").replace(")", "").replace("-", "").replace("\\", "").replace(" ", "")
        if existing and clean and not clean.replace(".", "").isdigit():
            return f"SKIPPED: Table {table_index}, row {row}, col {physical_col} — existing text '{existing[:40]}' is a label, not a number"
        _set_cell_text(tc, text)
        actual = get_cell_text(tc)
        return f"OK: Table {table_index}, row {row}, col {physical_col} → '{actual}'"
    except IndexError as e:
        return f"ERROR: {e}"


@tool("batch_set_cells", "한 테이블의 여러 셀을 한 번에 수정합니다. cells: [[row, physical_col, text], ...]", is_write=True)
def batch_set_cells(table_index: int, cells: list) -> str:
    """여러 셀을 일괄 수정. cells = [[row, col, text], ...]"""
    ctx = _get_ctx()
    ok = 0
    errors = []
    skipped_details = []
    for item in cells:
        try:
            row, col, text = int(item[0]), int(item[1]), str(item[2])
            tc = ctx.get_cell(table_index, row, col)
            # 레이블 보호: 기존 텍스트가 숫자가 아니면 덮어쓰기 방지
            existing = get_cell_text(tc).strip()
            clean = existing.replace(",", "").replace("(", "").replace(")", "").replace("-", "").replace("\\", "").replace(" ", "")
            if existing and clean and not clean.replace(".", "").isdigit():
                skipped_details.append(f"R{row}C{col}: \"{existing[:40]}\" is a label")
                continue
            _set_cell_text(tc, text)
            ok += 1
        except Exception as e:
            errors.append(f"R{item[0]}C{item[1]}: {e}")
    result = f"OK: {ok}/{len(cells)} cells updated in Table {table_index}"
    if skipped_details:
        result += f"\nSKIPPED ({len(skipped_details)} label cells):"
        for detail in skipped_details[:10]:
            result += f"\n  {detail}"
    if errors:
        result += f"\nERRORS ({len(errors)}):"
        for err in errors[:5]:
            result += f"\n  {err}"
    return result


@tool("clone_row", "테이블 행을 복제하여 삽입합니다. 원본 행의 서식을 보존합니다.", is_write=True)
def clone_row(table_index: int, source_row: int, insert_after: int, cell_texts: dict = None) -> str:
    """행 복제 및 삽입."""
    ctx = _get_ctx()
    try:
        tbl = ctx.get_table(table_index)
        # cell_texts 키를 int로 변환 (JSON에서 str로 올 수 있음)
        int_texts = None
        if cell_texts:
            int_texts = {int(k): v for k, v in cell_texts.items()}

        from agent.tools.docx_ops.column_mapper import build_column_mapping
        mapping = build_column_mapping(tbl)

        _clone_row(
            tbl,
            source_row_idx=source_row,
            insert_after_idx=insert_after,
            cell_texts=int_texts,
            spacer_indices=mapping.spacer_indices,
        )
        new_idx = insert_after + 1
        total = len(findall_w(tbl, "w:tr"))
        return f"OK: Cloned row {source_row}, inserted after row {insert_after}. New row index: {new_idx}. Total rows: {total}"
    except (IndexError, Exception) as e:
        return f"ERROR: {e}"


@tool("delete_row", "테이블에서 행을 삭제합니다.", is_write=True)
def delete_row(table_index: int, row: int) -> str:
    """행 삭제."""
    ctx = _get_ctx()
    try:
        tbl = ctx.get_table(table_index)
        _delete_row(tbl, row)
        remaining = len(findall_w(tbl, "w:tr"))
        return f"OK: Deleted row {row} from table {table_index}. Remaining rows: {remaining}"
    except (IndexError, Exception) as e:
        return f"ERROR: {e}"


@tool("replace_text_in_paragraph", "본문 문단의 텍스트를 교체합니다.", is_write=True)
def replace_text_in_paragraph(paragraph_index: int, old_text: str, new_text: str) -> str:
    """문단 텍스트 교체."""
    ctx = _get_ctx()
    try:
        p = ctx.get_paragraph(paragraph_index)
        changed = replace_text_in_element(p.getparent(), [(old_text, new_text)])
        if changed:
            return f"OK: Replaced '{old_text}' → '{new_text}' in paragraph {paragraph_index}"
        else:
            return f"WARNING: '{old_text}' not found in paragraph {paragraph_index}"
    except (IndexError, Exception) as e:
        return f"ERROR: {e}"


@tool("replace_in_headers_footers", "모든 헤더/푸터에서 텍스트를 일괄 교체합니다.", is_write=True)
def replace_in_headers_footers(replacements: list) -> str:
    """헤더/푸터 텍스트 교체 (연도 롤링 등)."""
    ctx = _get_ctx()
    # replacements: [["old1", "new1"], ["old2", "new2"]]
    repl_tuples = [(old, new) for old, new in replacements]
    total_changed = 0

    for header in ctx.headers:
        if replace_text_in_element(header, repl_tuples):
            total_changed += 1

    for footer in ctx.footers:
        if replace_text_in_element(footer, repl_tuples):
            total_changed += 1

    return f"OK: Replacements applied to {total_changed} headers/footers"


@tool("replace_in_table_headers", "테이블 헤더 행의 연도/기간 텍스트를 교체합니다.", is_write=True)
def replace_in_table_headers(replacements: list) -> str:
    """테이블 헤더 행 텍스트 교체."""
    ctx = _get_ctx()
    repl_tuples = [(old, new) for old, new in replacements]
    tables_changed = 0

    for tbl in ctx.get_tables():
        rows = findall_w(tbl, "w:tr")
        # 처음 3행을 헤더로 간주
        header_rows = rows[:min(3, len(rows))]
        for row in header_rows:
            if replace_text_in_element(row, repl_tuples):
                tables_changed += 1

    return f"OK: Replacements applied across {tables_changed} table header rows"

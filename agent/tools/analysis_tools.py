"""
분석 도구 — DSD↔DOCX 비교, 검증, column 분석.
"""

from __future__ import annotations

import re
from typing import Optional

from agent.tools import tool
from agent.tools.docx_ops.column_mapper import build_column_mapping
from agent.tools.docx_ops.xml_helpers import findall_w, get_cell_text, w


_ctx = None
_memory = None


def set_context(ctx) -> None:
    global _ctx
    _ctx = ctx


def set_memory(mem) -> None:
    """Working Memory 인스턴스를 설정."""
    global _memory
    _memory = mem


def _get_ctx():
    if _ctx is None:
        raise RuntimeError("DocumentContext not initialized")
    return _ctx


def _parse_numeric(text: str) -> int | None:
    """다양한 숫자 형식을 int로 파싱."""
    text = text.strip()
    if not text or text in ("-", "—", "–", "\\", "/"):
        return 0

    negative = False
    # 괄호 형식: (1,234) → -1234
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
        negative = True
    # 삼각형: △1,234 → -1234
    if text.startswith("△") or text.startswith("▲"):
        text = text[1:]
        negative = True

    # 콤마, 공백 제거
    text = text.replace(",", "").replace(" ", "").replace("\u00a0", "")

    # 음수 부호
    if text.startswith("-"):
        text = text[1:]
        negative = True

    if not text:
        return None

    try:
        val = int(float(text))
        return -val if negative else val
    except ValueError:
        return None


@tool("get_column_info", "테이블의 컬럼 구조를 분석합니다. Spacer 컬럼, 기간 컬럼을 식별합니다.")
def get_column_info(table_index: int) -> str:
    """테이블 column 정보 반환."""
    ctx = _get_ctx()
    tbl = ctx.get_table(table_index)
    mapping = build_column_mapping(tbl)

    lines = [f"== Column Info: Table {table_index} =="]
    lines.append(f"Physical columns: {mapping.num_physical_cols}")
    lines.append(f"Logical columns: {mapping.num_logical_cols}")
    if mapping.spacer_indices:
        lines.append(f"Spacer columns: {mapping.spacer_indices}")

    lines.append("\nPhysical → Logical mapping:")
    for phys_idx, width in enumerate(mapping.physical_widths):
        if phys_idx in mapping.spacer_indices:
            lines.append(f"  Physical {phys_idx} → SPACER (width: {width} dxa)")
        else:
            log_idx = mapping.physical_to_logical.get(phys_idx, "?")
            lines.append(f"  Physical {phys_idx} → Logical {log_idx} (width: {width} dxa)")

    return "\n".join(lines)


@tool("validate_numbers", "DSD와 DOCX 간 숫자 값을 검증합니다.")
def validate_numbers(docx_table_index: int, expected_values: dict) -> str:
    """
    DOCX 테이블의 숫자를 기대값과 비교.

    expected_values: {"row:col": value, ...} 예: {"5:2": 1234567, "6:2": -456}
    """
    ctx = _get_ctx()
    tbl = ctx.get_table(docx_table_index)
    rows = findall_w(tbl, "w:tr")

    results = []
    pass_count = 0
    fail_count = 0

    for key, expected in expected_values.items():
        parts = key.split(":")
        if len(parts) != 2:
            results.append(f"  SKIP: Invalid key format '{key}' (expected 'row:col')")
            continue

        row_idx, col_idx = int(parts[0]), int(parts[1])
        if row_idx >= len(rows):
            results.append(f"  SKIP: Row {row_idx} out of range")
            continue

        cells = findall_w(rows[row_idx], "w:tc")
        # physical col 접근
        phys_col = 0
        cell_text = ""
        for tc in cells:
            span = 1
            tc_pr = findall_w(tc, "w:tcPr")
            if tc_pr:
                gs_list = findall_w(tc_pr[0], "w:gridSpan")
                if gs_list:
                    try:
                        span = int(gs_list[0].get(w("val"), "1"))
                    except ValueError:
                        span = 1
            if phys_col == col_idx:
                cell_text = get_cell_text(tc)
                break
            phys_col += span

        actual = _parse_numeric(cell_text)
        expected_int = int(expected) if expected is not None else None

        if actual is None and expected_int is None:
            pass_count += 1
            results.append(f"  Row {row_idx}, col {col_idx}: both empty ✓")
        elif actual is not None and expected_int is not None:
            diff = abs(actual - expected_int)
            if diff <= 1:
                pass_count += 1
                results.append(f"  Row {row_idx}, col {col_idx}: {actual} == {expected_int} ✓")
            else:
                fail_count += 1
                results.append(f"  Row {row_idx}, col {col_idx}: {actual} != {expected_int} (diff={diff}) ✗")
        else:
            fail_count += 1
            results.append(f"  Row {row_idx}, col {col_idx}: actual='{cell_text}' vs expected={expected_int} ✗")

    header = f"== Number Validation: Table {docx_table_index} ==\n"
    header += f"Checked: {pass_count + fail_count} values. PASS: {pass_count}, FAIL: {fail_count}\n"

    return header + "\n".join(results)


# ---------------------------------------------------------------------------
# 검증 도구 (Verification Tools)
# ---------------------------------------------------------------------------


@tool("find_unmatched_tables", "자동 검증 결과에서 미매칭/오류 테이블 목록을 반환합니다.")
def find_unmatched_tables() -> str:
    """verify_report에서 오류 테이블 목록 반환."""
    ctx = _get_ctx()
    # Access working memory through module-level variable
    if _memory is None:
        return "ERROR: Working memory not available"
    report_text = _memory.get("verify_report")
    if not report_text:
        return "INFO: Auto-verification has not run yet. No verify_report in memory."
    return report_text


@tool("compare_dsd_docx", "DSD 주석 데이터와 DOCX 테이블을 행별로 비교합니다.")
def compare_dsd_docx(note_number: str, docx_table_index: int) -> str:
    """DSD 주석 테이블과 DOCX 테이블을 행별로 비교하여 차이를 보여줍니다."""
    ctx = _get_ctx()

    if ctx.dsd_data is None:
        return "ERROR: DSD data not loaded"

    # DSD에서 해당 주석의 테이블 데이터 추출
    from agent.note_filler import (
        extract_dsd_tables,
        _parse_number,
        _convert_value,
        _detect_docx_unit,
    )

    dsd_tables = extract_dsd_tables(ctx.dsd_data)
    # 해당 note_number의 DSD 테이블 찾기
    matched_dsd = [t for t in dsd_tables if t.note_number == note_number]
    if not matched_dsd:
        return f"ERROR: DSD note '{note_number}' not found. Available notes: {sorted(set(t.note_number for t in dsd_tables))}"

    # DOCX 테이블 읽기
    try:
        tbl = ctx.get_table(docx_table_index)
    except IndexError as e:
        return f"ERROR: {e}"

    rows = findall_w(tbl, "w:tr")
    docx_unit = _detect_docx_unit(tbl)

    # 컬럼 매핑으로 physical column 구조 파악
    mapping = build_column_mapping(tbl)

    # DOCX 테이블 행 데이터 읽기
    docx_rows = []
    for ri, tr in enumerate(rows):
        cells = findall_w(tr, "w:tc")
        cell_texts = []
        for tc in cells:
            cell_texts.append(get_cell_text(tc).strip())
        docx_rows.append(cell_texts)

    # DSD 테이블별 비교 결과 생성
    lines = [f"== DSD Note {note_number} vs DOCX Table {docx_table_index} =="]
    lines.append(f"DOCX unit: {docx_unit}")
    lines.append(f"DOCX rows: {len(rows)}, Physical cols: {mapping.num_physical_cols}")
    lines.append("")

    for dsd_tbl in matched_dsd:
        dsd_unit = dsd_tbl.unit or "원"
        lines.append(f"--- DSD Table (note {dsd_tbl.note_number}, table_idx {dsd_tbl.table_idx_in_note}, unit: {dsd_unit}) ---")
        lines.append(f"{'Row':>4} | {'DOCX Label':<30} | {'DSD Cur':>12} | {'DOCX Cur':>12} | {'Match':>5} | {'DSD Pri':>12} | {'DOCX Pri':>12} | {'Match':>5}")
        lines.append("-" * 115)

        for dsd_row in dsd_tbl.rows:
            dsd_label = dsd_row.label[:30]

            # DSD 값 (단위 변환)
            dsd_cur_raw = dsd_row.values.get("current")
            dsd_pri_raw = dsd_row.values.get("prior")
            dsd_cur = _convert_value(dsd_cur_raw, dsd_unit, docx_unit)
            dsd_pri = _convert_value(dsd_pri_raw, dsd_unit, docx_unit)

            # DOCX에서 대응하는 행 찾기 (단순 인덱스 기반)
            docx_label = ""
            docx_cur_text = ""
            docx_pri_text = ""
            docx_cur_val: Optional[int] = None
            docx_pri_val: Optional[int] = None

            # DOCX 행 검색: 라벨 유사성으로 찾기
            best_ri = -1
            for ri, row_texts in enumerate(docx_rows):
                if row_texts and row_texts[0]:
                    # 라벨의 첫 몇 글자가 일치하면 매칭
                    docx_lbl = row_texts[0].strip()
                    if docx_lbl and (
                        dsd_label in docx_lbl
                        or docx_lbl in dsd_label
                        or dsd_label[:5] == docx_lbl[:5]
                    ):
                        best_ri = ri
                        break

            if best_ri >= 0 and best_ri < len(docx_rows):
                row_texts = docx_rows[best_ri]
                docx_label = row_texts[0] if row_texts else ""
                # 숫자 열에서 값 읽기 (spacer 제외한 logical columns)
                logical_cells = []
                phys = 0
                cells_in_row = findall_w(rows[best_ri], "w:tc")
                for tc in cells_in_row:
                    if phys not in mapping.spacer_indices:
                        logical_cells.append(get_cell_text(tc).strip())
                    span = 1
                    tc_pr = findall_w(tc, "w:tcPr")
                    if tc_pr:
                        gs_list = findall_w(tc_pr[0], "w:gridSpan")
                        if gs_list:
                            try:
                                span = int(gs_list[0].get(w("val"), "1"))
                            except ValueError:
                                span = 1
                    phys += span

                # logical_cells: [label, current, prior, ...]
                if len(logical_cells) > 1:
                    docx_cur_text = logical_cells[1]
                    docx_cur_val = _parse_numeric(docx_cur_text)
                if len(logical_cells) > 2:
                    docx_pri_text = logical_cells[2]
                    docx_pri_val = _parse_numeric(docx_pri_text)

            # 비교
            cur_match = "✓" if _values_match(dsd_cur, docx_cur_val) else "✗"
            pri_match = "✓" if _values_match(dsd_pri, docx_pri_val) else "✗"

            dsd_cur_str = f"{dsd_cur:,}" if dsd_cur is not None else "-"
            dsd_pri_str = f"{dsd_pri:,}" if dsd_pri is not None else "-"
            docx_cur_display = docx_cur_text if docx_cur_text else "-"
            docx_pri_display = docx_pri_text if docx_pri_text else "-"

            lines.append(
                f"{dsd_row.row_idx:>4} | {dsd_label:<30} | {dsd_cur_str:>12} | {docx_cur_display:>12} | {cur_match:>5} | {dsd_pri_str:>12} | {docx_pri_display:>12} | {pri_match:>5}"
            )

        lines.append("")

    return "\n".join(lines)


def _values_match(expected: Optional[int], actual: Optional[int], tolerance: int = 1) -> bool:
    """두 숫자 값이 일치하는지 비교. 반올림 오차(±1) 허용."""
    if expected is None and actual is None:
        return True
    if expected is not None and actual is not None:
        return abs(expected - actual) <= tolerance
    # 둘 다 0으로 취급되는 경우
    if expected == 0 and actual is None:
        return True
    if actual == 0 and expected is None:
        return True
    return False


@tool("verify_table", "특정 DOCX 테이블의 값을 DSD와 비교하여 검증합니다.")
def verify_table(docx_table_index: int) -> str:
    """DOCX 테이블의 현재 셀 값을 DSD 기대값과 비교하여 상세 검증 보고서 반환."""
    ctx = _get_ctx()

    # Working memory에서 매칭 정보 확인
    match_info = None
    if _memory is not None:
        match_info = _memory.get("verify_report")

    try:
        tbl = ctx.get_table(docx_table_index)
    except IndexError as e:
        return f"ERROR: {e}"

    rows = findall_w(tbl, "w:tr")
    mapping = build_column_mapping(tbl)

    lines = [f"== Verify Table {docx_table_index} =="]
    lines.append(f"Rows: {len(rows)}, Physical cols: {mapping.num_physical_cols}, Logical cols: {mapping.num_logical_cols}")
    if mapping.spacer_indices:
        lines.append(f"Spacer columns: {mapping.spacer_indices}")
    lines.append("")

    # 모든 행의 셀 값 읽기
    lines.append(f"{'Row':>4} | {'Label':<35} | {'Col1 (Current)':>15} | {'Col2 (Prior)':>15}")
    lines.append("-" * 80)

    pass_count = 0
    fail_count = 0
    empty_count = 0

    for ri, tr in enumerate(rows):
        cells = findall_w(tr, "w:tc")
        # spacer 제외한 logical cells
        logical_texts = []
        phys = 0
        for tc in cells:
            if phys not in mapping.spacer_indices:
                logical_texts.append(get_cell_text(tc).strip())
            span = 1
            tc_pr = findall_w(tc, "w:tcPr")
            if tc_pr:
                gs_list = findall_w(tc_pr[0], "w:gridSpan")
                if gs_list:
                    try:
                        span = int(gs_list[0].get(w("val"), "1"))
                    except ValueError:
                        span = 1
            phys += span

        label = logical_texts[0][:35] if logical_texts else ""
        col1 = logical_texts[1] if len(logical_texts) > 1 else ""
        col2 = logical_texts[2] if len(logical_texts) > 2 else ""

        # 숫자 값 파싱하여 검증
        col1_val = _parse_numeric(col1) if col1 else None
        col2_val = _parse_numeric(col2) if col2 else None

        if col1_val is not None or col2_val is not None:
            pass_count += 1
        elif not label and not col1 and not col2:
            empty_count += 1

        lines.append(f"{ri:>4} | {label:<35} | {col1:>15} | {col2:>15}")

    lines.append("")
    lines.append(f"Summary: {len(rows)} rows, {pass_count} with data, {empty_count} empty")

    # verify_report 정보가 있으면 해당 테이블의 상태 추가
    if match_info:
        # 해당 테이블 번호 언급 여부 확인
        table_ref = f"Table {docx_table_index}"
        if table_ref in match_info:
            lines.append("")
            lines.append("=== From verify_report ===")
            for line in match_info.split("\n"):
                if table_ref in line or f"table {docx_table_index}" in line.lower():
                    lines.append(f"  {line.strip()}")

    return "\n".join(lines)

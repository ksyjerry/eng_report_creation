"""
읽기 도구 — LLM이 DSD/DOCX 문서를 이해할 수 있도록 구조와 내용을 텍스트로 반환.
컨텍스트 절약을 위해 긴 내용은 truncate.
"""

from __future__ import annotations

from agent.tools import tool
from agent.tools.docx_ops.xml_helpers import w, findall_w, find_w, get_cell_text


# 전역 DocumentContext 참조 (agent 초기화 시 설정)
_ctx = None


def set_context(ctx) -> None:
    global _ctx
    _ctx = ctx


def _get_ctx():
    if _ctx is None:
        raise RuntimeError("DocumentContext not initialized. Call set_context() first.")
    return _ctx


@tool("read_docx_structure", "DOCX 전체 구조를 요약합니다. 테이블 수, 각 테이블의 행 수와 처음 2행 내용 포함.")
def read_docx_structure() -> str:
    """DOCX 전체 구조를 요약 텍스트로 반환. 각 테이블의 실제 행 수와 처음 2행 내용 표시."""
    ctx = _get_ctx()
    lines = ["== DOCX 구조 =="]

    tables = ctx.get_tables()
    lines.append(f"테이블: {len(tables)}개")
    for i, tbl in enumerate(tables):
        rows = findall_w(tbl, "w:tr")
        if rows:
            first_row_cells = findall_w(rows[0], "w:tc")
            cols = len(first_row_cells)
            # 처음 2행의 내용 표시 (테이블 식별용)
            row_previews = []
            for ri in range(min(2, len(rows))):
                cells = findall_w(rows[ri], "w:tc")
                texts = [get_cell_text(c).strip() for c in cells if get_cell_text(c).strip()]
                if texts:
                    row_previews.append(" | ".join(t[:30] for t in texts[:4]))
            preview = " // ".join(row_previews) if row_previews else "(empty)"
            lines.append(f"  Table {i}: {len(rows)}행 x {cols}열 — {preview}")

    paras = ctx.get_paragraphs()
    lines.append(f"\n본문 문단: {len(paras)}개")

    lines.append(f"헤더: {len(ctx.headers)}개")
    lines.append(f"푸터: {len(ctx.footers)}개")

    return "\n".join(lines)


@tool("read_table", "테이블을 마크다운 형태로 반환합니다.")
def read_table(table_index: int, max_rows: int = 50) -> str:
    """테이블을 마크다운 형태로 반환."""
    ctx = _get_ctx()
    tbl = ctx.get_table(table_index)
    rows = findall_w(tbl, "w:tr")
    total_rows = len(rows)
    show_rows = min(total_rows, max_rows)

    lines = [f"== Table {table_index} (DOCX) — {total_rows}행 =="]

    for i in range(show_rows):
        cells = findall_w(rows[i], "w:tc")
        cell_texts = [get_cell_text(tc).strip() for tc in cells]
        line = " | ".join(cell_texts)
        lines.append(f"Row {i}: | {line} |")

        # 헤더 구분선 (첫 행 다음)
        if i == 0:
            lines.append("|" + "|".join(["---"] * len(cells)) + "|")

    if total_rows > max_rows:
        lines.append(f"\n(showing {show_rows} of {total_rows} rows)")

    return "\n".join(lines)


@tool("read_cell", "특정 셀의 값을 반환합니다.")
def read_cell(table_index: int, row: int, col: int) -> str:
    """특정 셀 값 반환."""
    ctx = _get_ctx()
    tc = ctx.get_cell(table_index, row, col)
    text = get_cell_text(tc)
    return f"Table {table_index}, row {row}, col {col}: '{text}'"


@tool("read_header_footer", "모든 헤더/푸터 텍스트를 반환합니다.")
def read_header_footer() -> str:
    """모든 header/footer 텍스트 반환."""
    ctx = _get_ctx()
    lines = []

    for i, header in enumerate(ctx.headers):
        texts = []
        for t in header.iter(w("t")):
            if t.text:
                texts.append(t.text)
        if texts:
            lines.append(f"== Header {i} ==")
            lines.append("".join(texts))

    for i, footer in enumerate(ctx.footers):
        texts = []
        for t in footer.iter(w("t")):
            if t.text:
                texts.append(t.text)
        if texts:
            lines.append(f"== Footer {i} ==")
            lines.append("".join(texts))

    return "\n".join(lines) if lines else "(No headers/footers found)"


@tool("read_dsd_structure", "DSD 파일의 전체 구조를 요약합니다. 재무제표 종류, 기간, 행 수 등.")
def read_dsd_structure() -> str:
    """DSD 파싱 결과의 전체 구조를 요약."""
    ctx = _get_ctx()
    if ctx.dsd_data is None:
        return "ERROR: DSD 파일이 로드되지 않았습니다."

    d = ctx.dsd_data
    lines = ["== DSD 구조 =="]
    lines.append(f"회사: {d.meta.company}")
    lines.append(f"당기: {d.meta.period_current}")
    lines.append(f"전기: {d.meta.period_prior}")
    lines.append(f"문서유형: {d.meta.doc_type.value}")
    lines.append(f"섹션: {len(d.sections)}개")

    for s in d.sections:
        lines.append(f"\n  Section {s.section_index}: {s.title} ({s.section_type})")
        for fs in s.financial_statements:
            lines.append(f"    FS: {fs.statement_type.value} — {fs.title}")
            lines.append(f"      기간: {fs.periods}")
            lines.append(f"      행: {len(fs.table.rows)}, 헤더행: {len(fs.table.headers)}")
            if fs.table.unit:
                lines.append(f"      단위: {fs.table.unit}")
        lines.append(f"    주석: {len(s.notes)}개")

    return "\n".join(lines)


@tool("read_dsd_table", "DSD 재무제표 테이블 데이터를 반환합니다. statement_type: BS, IS, CE, CF")
def read_dsd_table(statement_type: str, max_rows: int = 60) -> str:
    """DSD 재무제표 테이블을 텍스트로 반환."""
    ctx = _get_ctx()
    if ctx.dsd_data is None:
        return "ERROR: DSD 파일이 로드되지 않았습니다."

    # 재무제표 찾기
    target = None
    for s in ctx.dsd_data.sections:
        for fs in s.financial_statements:
            if fs.statement_type.value == statement_type:
                target = fs
                break
        if target:
            break

    if target is None:
        types = [fs.statement_type.value for s in ctx.dsd_data.sections for fs in s.financial_statements]
        return f"ERROR: '{statement_type}' not found. Available: {types}"

    lines = [f"== DSD {target.title} ({target.statement_type.value}) =="]
    lines.append(f"기간: {target.periods}")
    if target.table.unit:
        lines.append(f"단위: {target.table.unit}")

    # 헤더
    for hi, hrow in enumerate(target.table.headers):
        cells = [c.text.strip() for c in hrow.cells]
        lines.append(f"Header {hi}: | {' | '.join(cells)} |")

    # 데이터 행
    rows = target.table.rows
    show = min(len(rows), max_rows)
    for i in range(show):
        row = rows[i]
        cells = [c.text.strip() for c in row.cells]
        prefix = ""
        if row.is_total:
            prefix = "[합계] "
        elif row.is_subtotal:
            prefix = "[소계] "
        indent = "  " * (row.cells[0].indent_level if row.cells else 0)
        lines.append(f"Row {i}: {prefix}{indent}| {' | '.join(cells)} |")

    if len(rows) > max_rows:
        lines.append(f"\n(showing {show} of {len(rows)} rows)")

    return "\n".join(lines)


@tool("read_dsd_notes", "DSD 주석 목록을 반환합니다.")
def read_dsd_notes(max_notes: int = 40) -> str:
    """DSD 주석 목록 반환."""
    ctx = _get_ctx()
    if ctx.dsd_data is None:
        return "ERROR: DSD 파일이 로드되지 않았습니다."

    notes = ctx.dsd_data.get_all_notes()
    lines = [f"== DSD 주석 ({len(notes)}개) =="]
    for note in notes[:max_notes]:
        lines.append(f"  주석 {note.number}: {note.title}")
        # 간단한 요소 카운트
        tables = sum(1 for e in note.elements if e.type.value == "table")
        paras = sum(1 for e in note.elements if e.type.value == "paragraph")
        lines.append(f"    문단: {paras}, 테이블: {tables}")

    if len(notes) > max_notes:
        lines.append(f"\n(showing {max_notes} of {len(notes)} notes)")

    return "\n".join(lines)


@tool("read_dsd_note_detail", "특정 DSD 주석의 상세 내용을 반환합니다.")
def read_dsd_note_detail(note_number: str) -> str:
    """특정 주석의 상세 내용 반환."""
    ctx = _get_ctx()
    if ctx.dsd_data is None:
        return "ERROR: DSD 파일이 로드되지 않았습니다."

    notes = ctx.dsd_data.get_all_notes()
    target = None
    for n in notes:
        if n.number == note_number:
            target = n
            break

    if target is None:
        return f"ERROR: Note {note_number} not found. Available: {[n.number for n in notes[:20]]}"

    lines = [f"== 주석 {target.number}: {target.title} =="]
    for elem in target.elements:
        if elem.type.value == "paragraph":
            indent = "  " * (elem.depth or 0)
            prefix = f"{elem.numbering} " if elem.numbering else ""
            lines.append(f"{indent}{prefix}{elem.text}")
        elif elem.type.value == "subtitle":
            lines.append(f"\n### {elem.numbering or ''} {elem.text}")
        elif elem.type.value == "table" and elem.table:
            for hi, hrow in enumerate(elem.table.headers):
                hcells = [c.text.strip() for c in hrow.cells]
                lines.append(f"\n[Table header: | {' | '.join(hcells)} |]")
            lines.append(f"[Table: {len(elem.table.rows)} rows]")
            for ri, row in enumerate(elem.table.rows[:15]):
                cells = [c.text.strip() for c in row.cells]
                prefix = "[합계] " if row.is_total else ""
                lines.append(f"  {prefix}| {' | '.join(cells)} |")
            if len(elem.table.rows) > 15:
                lines.append(f"  (... {len(elem.table.rows) - 15} more rows)")

    # 긴 주석은 truncate하되, 테이블 데이터를 우선 포함
    result = "\n".join(lines)
    if len(result) > 8000:
        return result[:8000] + f"\n\n(truncated at 8000 chars, total {len(result)} chars)"
    return result


@tool("search_text", "DOCX 전체에서 텍스트를 검색합니다.")
def search_text(query: str) -> str:
    """DOCX 전체에서 텍스트 검색. 위치 + 주변 텍스트 반환."""
    ctx = _get_ctx()
    results = []
    max_results = 20

    # 본문 문단 검색
    for i, p in enumerate(ctx.get_paragraphs()):
        texts = []
        for t in p.iter(w("t")):
            if t.text:
                texts.append(t.text)
        full = "".join(texts)
        if query in full:
            results.append(f"  Paragraph {i}: '{full[:100]}'")

    # 테이블 검색
    for ti, tbl in enumerate(ctx.get_tables()):
        rows = findall_w(tbl, "w:tr")
        for ri, row in enumerate(rows):
            cells = findall_w(row, "w:tc")
            for ci, tc in enumerate(cells):
                text = get_cell_text(tc)
                if query in text:
                    results.append(f"  Table {ti}, row {ri}, col {ci}: '{text[:80]}'")

    # 헤더/푸터 검색
    for i, header in enumerate(ctx.headers):
        texts = []
        for t in header.iter(w("t")):
            if t.text:
                texts.append(t.text)
        full = "".join(texts)
        if query in full:
            results.append(f"  Header {i}: '{full[:100]}'")

    for i, footer in enumerate(ctx.footers):
        texts = []
        for t in footer.iter(w("t")):
            if t.text:
                texts.append(t.text)
        full = "".join(texts)
        if query in full:
            results.append(f"  Footer {i}: '{full[:100]}'")

    if not results:
        return f"No occurrences of '{query}' found."

    header = f"Found {len(results)} occurrences of '{query}':"
    if len(results) > max_results:
        results = results[:max_results]
        header += f" (showing first {max_results})"

    return header + "\n" + "\n".join(results)

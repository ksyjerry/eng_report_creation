"""
Parse DOCX tables into clean TableData, handling:
- Spacer columns (narrow gridCol widths → removed from logical output)
- vMerge (vertical cell merging)
- gridSpan (horizontal cell spanning)
- Preserves original-to-logical column mapping for the writer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from docx.table import Table as DocxTable

from ir_schema import CellValue, TableRow, TableData, DocxProfile
from utils.xml_helpers import w, find_w, findall_w

# Default spacer threshold (overridden by profile when available)
DEFAULT_SPACER_THRESHOLD = 200


@dataclass
class ColumnMapping:
    """Maps logical columns back to physical grid columns."""
    logical_to_physical: dict[int, list[int]] = field(default_factory=dict)
    physical_to_logical: dict[int, int] = field(default_factory=dict)
    spacer_indices: list[int] = field(default_factory=list)
    physical_widths: list[int] = field(default_factory=list)


def parse_table(
    docx_table: DocxTable,
    source_index: int = -1,
    profile: DocxProfile | None = None,
    spacer_threshold: int = DEFAULT_SPACER_THRESHOLD,
) -> tuple[TableData, ColumnMapping]:
    """
    Parse a python-docx Table into a TableData with spacer columns removed.

    Returns:
        (TableData, ColumnMapping) — the clean table and the mapping back
        to physical columns.
    """
    tbl = docx_table._tbl

    # ── 1. Read grid columns and detect spacers ─────────────
    col_mapping = _build_column_mapping(tbl, spacer_threshold)
    num_logical_cols = len(col_mapping.logical_to_physical)

    # ── 2. Parse rows (handling vMerge + gridSpan) ──────────
    xml_rows = findall_w(tbl, "w:tr")
    # vmerge_state[logical_col] = CellValue currently being extended downward
    vmerge_state: dict[int, CellValue] = {}
    # Track rowspan start positions for vmerge: (row_idx, logical_col)
    vmerge_start_row: dict[int, int] = {}

    parsed_rows: list[TableRow] = []

    for row_idx, tr in enumerate(xml_rows):
        row_cells = _parse_row(
            tr, col_mapping, num_logical_cols,
            vmerge_state, vmerge_start_row, row_idx, parsed_rows,
        )
        is_empty = all(c.text.strip() == "" for c in row_cells)
        parsed_rows.append(TableRow(cells=row_cells, is_empty=is_empty))

    # ── 3. Separate headers from data rows ──────────────────
    headers, data_rows = _split_headers(parsed_rows)

    # ── 4. Detect title and unit from headers / first rows ──
    title, unit = _detect_title_unit(headers, data_rows)

    # Build logical→physical mapping (first physical index for each logical column)
    log_to_phys = {}
    for log_idx, phys_list in col_mapping.logical_to_physical.items():
        if phys_list:
            log_to_phys[log_idx] = phys_list[0]

    table_data = TableData(
        id=f"tbl_{source_index}",
        headers=headers,
        rows=data_rows,
        title=title,
        unit=unit,
        source_index=source_index,
        logical_to_physical=log_to_phys,
    )

    return table_data, col_mapping


# ── Column mapping ──────────────────────────────────────────────

def _build_column_mapping(tbl_element, spacer_threshold: int) -> ColumnMapping:
    """Build logical→physical column mapping, filtering out spacer columns."""
    grid_cols = findall_w(tbl_element, "w:tblGrid/w:gridCol")

    physical_widths: list[int] = []
    for gc in grid_cols:
        w_val = gc.get(w("w"))
        if w_val is not None:
            try:
                physical_widths.append(int(w_val))
            except ValueError:
                physical_widths.append(0)
        else:
            physical_widths.append(0)

    spacer_indices: list[int] = []
    logical_to_physical: dict[int, list[int]] = {}
    physical_to_logical: dict[int, int] = {}
    logical_idx = 0

    for phys_idx, width in enumerate(physical_widths):
        if 0 < width < spacer_threshold:
            spacer_indices.append(phys_idx)
        else:
            logical_to_physical[logical_idx] = [phys_idx]
            physical_to_logical[phys_idx] = logical_idx
            logical_idx += 1

    # If no grid col info at all, fall back to counting cells in first row
    if not physical_widths:
        rows = findall_w(tbl_element, "w:tr")
        if rows:
            first_row_cells = findall_w(rows[0], "w:tc")
            for i in range(len(first_row_cells)):
                logical_to_physical[i] = [i]
                physical_to_logical[i] = i

    return ColumnMapping(
        logical_to_physical=logical_to_physical,
        physical_to_logical=physical_to_logical,
        spacer_indices=spacer_indices,
        physical_widths=physical_widths,
    )


# ── Row parsing ─────────────────────────────────────────────────

def _parse_row(
    tr,
    col_mapping: ColumnMapping,
    num_logical_cols: int,
    vmerge_state: dict[int, CellValue],
    vmerge_start_row: dict[int, int],
    current_row_idx: int,
    parsed_rows: list[TableRow],
) -> list[CellValue]:
    """Parse a single <w:tr> into a list of CellValues aligned to logical columns."""
    cells_xml = findall_w(tr, "w:tc")

    # Walk physical columns occupied by each XML cell
    phys_col = 0
    # Build a physical-column-indexed map first
    phys_cells: dict[int, CellValue] = {}
    phys_vmerge_continue: set[int] = set()  # physical cols that are vmerge continuations

    for tc in cells_xml:
        tc_pr = find_w(tc, "w:tcPr")

        # gridSpan
        span = 1
        if tc_pr is not None:
            gs = find_w(tc_pr, "w:gridSpan")
            if gs is not None:
                try:
                    span = int(gs.get(w("val"), "1"))
                except ValueError:
                    span = 1

        # vMerge
        is_vmerge_restart = False
        is_vmerge_continue = False
        if tc_pr is not None:
            vm = find_w(tc_pr, "w:vMerge")
            if vm is not None:
                val = vm.get(w("val"), "")
                if val == "restart":
                    is_vmerge_restart = True
                else:
                    is_vmerge_continue = True

        # Cell text
        text = _cell_text(tc)

        # Alignment
        align = ""
        if tc_pr is not None:
            jc = find_w(tc, "w:p/w:pPr/w:jc")
            if jc is not None:
                align = jc.get(w("val"), "").upper()

        # Indent level (from indentation in first paragraph)
        indent_level = 0
        if tc_pr is not None:
            ind = find_w(tc, "w:p/w:pPr/w:ind")
            if ind is not None:
                left = ind.get(w("left"), "0")
                try:
                    indent_level = int(left) // 360  # ~0.25 inch per level
                except ValueError:
                    pass

        cell = CellValue(
            text=text,
            colspan=1,  # will be adjusted for logical columns
            rowspan=1,
            is_header=False,
            align=align,
            indent_level=indent_level,
        )

        if is_vmerge_continue:
            for p in range(phys_col, phys_col + span):
                phys_vmerge_continue.add(p)
        else:
            if is_vmerge_restart:
                # Mark this as start of vmerge
                pass  # rowspan will be resolved later
            for p in range(phys_col, phys_col + span):
                phys_cells[p] = cell

        phys_col += span

    # Now map physical cells to logical columns
    result: list[CellValue] = []
    logical_col = 0
    visited_phys: set[int] = set()

    for log_idx in range(num_logical_cols):
        if log_idx not in col_mapping.logical_to_physical:
            result.append(CellValue(text=""))
            continue

        phys_indices = col_mapping.logical_to_physical[log_idx]
        phys_start = phys_indices[0]

        # Check if this physical column is a vmerge continuation
        if phys_start in phys_vmerge_continue:
            # Update the rowspan of the cell that started this merge
            if log_idx in vmerge_state:
                vmerge_state[log_idx].rowspan += 1
            result.append(CellValue(text="", rowspan=0))  # placeholder
            continue

        if phys_start in phys_cells:
            cell = phys_cells[phys_start]

            # Check if this cell spans multiple logical columns
            # (a physical gridSpan may cover spacer + content cols)
            logical_span = _compute_logical_span(
                phys_start, phys_col, phys_cells, col_mapping
            )
            cell.colspan = max(1, logical_span)

            # Track vmerge state
            # If this physical col has a vMerge restart, track it
            tc_list = findall_w(tr, "w:tc")
            for tc in tc_list:
                tc_pr = find_w(tc, "w:tcPr")
                if tc_pr is not None:
                    vm = find_w(tc_pr, "w:vMerge")
                    if vm is not None and vm.get(w("val"), "") == "restart":
                        # Store in vmerge state for continuation tracking
                        vmerge_state[log_idx] = cell
                        vmerge_start_row[log_idx] = current_row_idx
                        break

            result.append(cell)
        else:
            result.append(CellValue(text=""))

        # Clear vmerge state for this column if we have a real cell
        # (not a continuation) and it's not a restart
        if phys_start not in phys_vmerge_continue and phys_start in phys_cells:
            # Only clear if there's no vMerge restart on this cell
            if log_idx in vmerge_state and vmerge_state[log_idx] is not phys_cells.get(phys_start):
                del vmerge_state[log_idx]
                if log_idx in vmerge_start_row:
                    del vmerge_start_row[log_idx]

    return result


def _compute_logical_span(
    phys_start: int,
    total_phys_cols: int,
    phys_cells: dict[int, CellValue],
    col_mapping: ColumnMapping,
) -> int:
    """
    Given a cell that starts at phys_start, compute how many logical
    columns it spans (considering that it may span over spacer cols).
    """
    cell = phys_cells.get(phys_start)
    if cell is None:
        return 1

    # Find all physical columns that map to this same cell object
    cell_phys_cols = [p for p, c in phys_cells.items() if c is cell]
    if not cell_phys_cols:
        return 1

    # Map to logical columns
    logical_cols = set()
    for p in cell_phys_cols:
        if p in col_mapping.physical_to_logical:
            logical_cols.add(col_mapping.physical_to_logical[p])

    return max(1, len(logical_cols))


# ── Header / data split ────────────────────────────────────────

def _split_headers(rows: list[TableRow]) -> tuple[list[TableRow], list[TableRow]]:
    """
    Heuristic: header rows are at the top and typically contain
    non-numeric text (column labels, period names, units).
    """
    if not rows:
        return [], []

    header_end = 0
    for i, row in enumerate(rows):
        if row.is_empty:
            # Empty row 2 pattern: row index 1 is separator
            if i == 1 and len(rows) > 2:
                continue
            break
        # Check if row has mostly non-numeric cells
        non_numeric = sum(1 for c in row.cells if c.text.strip() and not _is_numeric(c.text))
        numeric = sum(1 for c in row.cells if _is_numeric(c.text))
        if non_numeric > numeric or numeric == 0:
            header_end = i + 1
        else:
            break

    # At least row 0 is a header if it looks non-numeric
    if header_end == 0 and rows:
        header_end = 1

    headers = rows[:header_end]
    data = rows[header_end:]

    for h_row in headers:
        h_row.is_header_row = True
        for c in h_row.cells:
            c.is_header = True

    return headers, data


def _is_numeric(text: str) -> bool:
    """Check if text looks like a financial number."""
    cleaned = text.strip().replace(",", "").replace("\\", "").replace("\u20a9", "")
    cleaned = cleaned.strip()
    if not cleaned:
        return False
    if cleaned in ("-", "—", "–"):
        return True
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = cleaned[1:-1].strip()
    cleaned = cleaned.lstrip("-")
    return cleaned.replace(".", "", 1).isdigit()


# ── Title / unit detection ──────────────────────────────────────

def _detect_title_unit(
    headers: list[TableRow],
    data_rows: list[TableRow],
) -> tuple[str, str]:
    """Extract table title and unit string from header rows."""
    title = ""
    unit = ""

    for row in headers:
        for cell in row.cells:
            text = cell.text.strip()
            if not text:
                continue
            # Unit patterns
            if "in " in text.lower() and ("won" in text.lower() or "thousand" in text.lower()
                                          or "million" in text.lower()):
                unit = text
            elif text.startswith("(") and "won" in text.lower():
                unit = text
            elif text.startswith("(in "):
                unit = text

    return title, unit


# ── Helpers ─────────────────────────────────────────────────────

def _cell_text(tc_element) -> str:
    """Extract combined text from all paragraphs in a w:tc."""
    texts = []
    for t_el in tc_element.iter(w("t")):
        if t_el.text:
            texts.append(t_el.text)
    return "".join(texts)

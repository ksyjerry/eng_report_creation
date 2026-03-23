"""
DSD TABLE element parser.
Handles COLSPAN/ROWSPAN expansion and produces TableData structures.
"""

import re
from lxml import etree

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ir_schema import TableData, TableRow, CellValue
from utils.xml_helpers import get_attr


def _get_cell_text(cell_elem) -> str:
    """
    Extract text from a TD/TH/TU cell element.
    Handles nested P elements and &cr; entities.
    """
    # Try method="text" first for simple cells
    text = etree.tostring(cell_elem, method="text", encoding="unicode") or ""
    # &cr; appears as literal text "&cr;" after XML parsing of &amp;cr;
    text = text.replace("&cr;", "\n")
    # Collapse multiple whitespace within lines but preserve newlines
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = re.sub(r'\s+', ' ', line).strip()
        if stripped:
            cleaned_lines.append(stripped)
    return "\n".join(cleaned_lines)


def _detect_indent_level(cell_elem) -> int:
    """Detect indent level from leading spaces in cell text."""
    raw_text = (cell_elem.text or "")
    if not raw_text:
        # Check nested P elements
        p = cell_elem.find('.//P')
        if p is not None:
            raw_text = p.text or ""
    leading = len(raw_text) - len(raw_text.lstrip())
    if leading >= 6:
        return 3
    elif leading >= 4:
        return 2
    elif leading >= 2:
        return 1
    return 0


def parse_table(table_elem) -> TableData:
    """
    Parse a TABLE element into a TableData structure.
    Expands COLSPAN and ROWSPAN into flat cell structures.

    Args:
        table_elem: lxml Element for a TABLE tag

    Returns:
        TableData with headers and rows populated
    """
    table_data = TableData()

    # Get table-level attributes
    border = get_attr(table_elem, "BORDER", "0")
    table_data.id = f"table_border{border}"

    # Parse COLGROUP to get column count
    cols = table_elem.findall('.//COLGROUP/COL')
    num_cols = len(cols) if cols else 0

    # Collect all rows from THEAD and TBODY
    header_rows = []
    body_rows = []

    thead = table_elem.find('.//THEAD')
    tbody = table_elem.find('.//TBODY')

    if thead is not None:
        header_rows = thead.findall('TR')
    if tbody is not None:
        body_rows = tbody.findall('TR')

    # If no explicit THEAD/TBODY, get all TR elements directly
    if not header_rows and not body_rows:
        all_trs = table_elem.findall('.//TR')
        body_rows = all_trs

    # Parse header rows
    parsed_headers = _parse_rows(header_rows, num_cols, is_header=True)
    # Parse body rows
    parsed_body = _parse_rows(body_rows, num_cols, is_header=False)

    table_data.headers = parsed_headers
    table_data.rows = parsed_body

    return table_data


def _parse_rows(tr_elements: list, num_cols: int, is_header: bool = False) -> list[TableRow]:
    """
    Parse a list of TR elements, handling COLSPAN and ROWSPAN.
    Returns a list of TableRow with expanded cells.
    """
    if not tr_elements:
        return []

    # We use a grid to track rowspan carryovers
    # grid[row_idx][col_idx] = CellValue or None
    rows = []
    # Track rowspan: for each column, how many more rows it spans
    rowspan_tracker: dict[int, tuple[int, CellValue]] = {}
    # Maps col_idx -> (remaining_rows, cell_value)

    for tr_elem in tr_elements:
        cells_in_row: list[CellValue] = []
        cell_elements = tr_elem.findall('TD') + tr_elem.findall('TH') + tr_elem.findall('TU')

        # Sort by document order (they come out in order from findall on each tag,
        # but we need them interleaved by position)
        cell_elements = []
        for child in tr_elem:
            if child.tag in ('TD', 'TH', 'TU'):
                cell_elements.append(child)

        col_idx = 0
        cell_iter = iter(cell_elements)

        # Build the row, accounting for rowspans from previous rows
        while col_idx < max(num_cols, 1) or cell_elements:
            # Check if this column is occupied by a rowspan from above
            if col_idx in rowspan_tracker:
                remaining, carry_cell = rowspan_tracker[col_idx]
                # Add a copy of the carried cell
                cells_in_row.append(CellValue(
                    text=carry_cell.text,
                    colspan=1,
                    rowspan=1,
                    is_header=carry_cell.is_header,
                    align=carry_cell.align,
                    indent_level=carry_cell.indent_level,
                ))
                if remaining <= 1:
                    del rowspan_tracker[col_idx]
                else:
                    rowspan_tracker[col_idx] = (remaining - 1, carry_cell)
                col_idx += 1
                continue

            # Get next cell element
            try:
                cell_elem = next(cell_iter)
            except StopIteration:
                break

            colspan = int(get_attr(cell_elem, "COLSPAN", "1") or "1")
            rowspan = int(get_attr(cell_elem, "ROWSPAN", "1") or "1")
            align = get_attr(cell_elem, "ALIGN", "")
            cell_is_header = is_header or cell_elem.tag == "TH"

            text = _get_cell_text(cell_elem)
            indent = _detect_indent_level(cell_elem)

            cell = CellValue(
                text=text,
                colspan=colspan,
                rowspan=rowspan,
                is_header=cell_is_header,
                align=align.upper(),
                indent_level=indent,
            )

            # Add the cell (expand colspan)
            for c in range(colspan):
                cells_in_row.append(CellValue(
                    text=text if c == 0 else "",
                    colspan=1,
                    rowspan=1,
                    is_header=cell_is_header,
                    align=align.upper(),
                    indent_level=indent if c == 0 else 0,
                ))
                # Track rowspan for subsequent rows
                if rowspan > 1:
                    rowspan_tracker[col_idx + c] = (rowspan - 1, cell)

            col_idx += colspan

        # Determine row properties
        row_text = " ".join(c.text for c in cells_in_row).strip()
        is_empty = not row_text
        is_total = bool(re.search(r'합\s*계|총\s*계|소\s*계', row_text))
        is_subtotal = bool(re.search(r'소\s*계', row_text))

        table_row = TableRow(
            cells=cells_in_row,
            is_header_row=is_header,
            is_subtotal=is_subtotal,
            is_total=is_total and not is_subtotal,
            is_empty=is_empty,
        )
        rows.append(table_row)

    return rows

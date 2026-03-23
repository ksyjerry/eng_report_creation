"""
Number validator — compare numeric values between DSD source and output DOCX.

For every financial statement table in the DSD, find the corresponding table
in the output DOCX and verify that all numeric cells match (within tolerance).
"""

from __future__ import annotations

import re

from ir_schema import (
    ParsedDocument, TableData, TableRow, FinancialStatement, StatementType,
)
from utils.number_format import parse_korean_number
from skills.review.review_report import ReviewItem, ReviewReport


# Tolerance: allow +-1 for integer rounding
TOLERANCE = 1


def _parse_number(text: str) -> int | float | None:
    """Parse a number from either Korean or English formatted text."""
    return parse_korean_number(text)


def _table_numbers(table: TableData) -> list[tuple[int, int, str, int | float]]:
    """
    Extract all numeric cells from a table as (row_idx, col_idx, raw_text, value).
    row_idx is relative to data rows (excludes headers).
    """
    results = []
    for r_idx, row in enumerate(table.rows):
        for c_idx, cell in enumerate(row.cells):
            text = cell.text.strip()
            if not text:
                continue
            val = _parse_number(text)
            if val is not None:
                results.append((r_idx, c_idx, text, val))
    return results


def _match_statement_type(title: str) -> StatementType | None:
    """Try to match a table title to a StatementType."""
    lower = title.lower()
    if "balance" in lower or "financial position" in lower or "재무상태" in lower:
        return StatementType.BALANCE_SHEET
    if "income" in lower or "comprehensive" in lower or "profit" in lower or "손익" in lower:
        return StatementType.INCOME_STATEMENT
    if "equity" in lower or "자본변동" in lower:
        return StatementType.CHANGES_IN_EQUITY
    if "cash" in lower or "현금" in lower:
        return StatementType.CASH_FLOW
    return None


def _find_matching_table(
    dsd_stmt: FinancialStatement,
    output_stmts: list[FinancialStatement],
) -> FinancialStatement | None:
    """Find the output financial statement that matches the DSD statement type."""
    for out_stmt in output_stmts:
        if out_stmt.statement_type == dsd_stmt.statement_type:
            return out_stmt
    return None


def _find_matching_table_by_title(
    dsd_table: TableData,
    output_tables: list[TableData],
) -> TableData | None:
    """Find a matching output table by title similarity."""
    dsd_title = dsd_table.title.lower().strip()
    if not dsd_title:
        return None
    for out_tbl in output_tables:
        out_title = out_tbl.title.lower().strip()
        if out_title and (dsd_title in out_title or out_title in dsd_title):
            return out_tbl
    return None


def _row_label(row: TableRow) -> str:
    """Get the label (first non-empty text cell) of a row for location reporting."""
    for cell in row.cells:
        text = cell.text.strip()
        if text and _parse_number(text) is None:
            return text
    return ""


def validate_numbers(
    dsd_doc: ParsedDocument,
    output_doc: ParsedDocument,
    report: ReviewReport,
) -> None:
    """
    Compare all numeric values in DSD financial statement tables against
    the corresponding tables in the output DOCX.

    Strategy:
      1. Try to match by FinancialStatement type (DSD FS ↔ output FS).
      2. If the output DOCX has no FinancialStatement objects (common when
         the DOCX parser puts everything into notes/preamble), fall back to
         scanning all output tables and matching by title keywords.
      3. Compare note-level tables by note number.

    Adds ReviewItems to the report for any mismatches.
    """
    dsd_stmts = dsd_doc.get_financial_statements()
    output_stmts = output_doc.get_financial_statements()

    if not dsd_stmts:
        report.add(ReviewItem(
            severity="WARNING",
            category="number",
            location="document",
            message="No financial statements found in DSD source",
        ))
        # Still try note-level comparison
        _compare_note_tables(dsd_doc, output_doc, report)
        return

    # Collect all tables from the output (FS tables + note/preamble tables)
    all_output_tables = _collect_all_tables(output_doc)

    matched = 0

    if output_stmts:
        # Path A: structured FinancialStatement matching
        for dsd_stmt in dsd_stmts:
            out_stmt = _find_matching_table(dsd_stmt, output_stmts)
            if out_stmt is None:
                report.add(ReviewItem(
                    severity="WARNING",
                    category="number",
                    location=f"Financial Statement: {dsd_stmt.title or dsd_stmt.statement_type.value}",
                    message="No matching FS object in output; will try table-title fallback",
                ))
                continue

            if dsd_stmt.table is None or out_stmt.table is None:
                if dsd_stmt.table is not None and out_stmt.table is None:
                    report.add(ReviewItem(
                        severity="CRITICAL",
                        category="number",
                        location=f"Financial Statement: {dsd_stmt.title or dsd_stmt.statement_type.value}",
                        message="DSD has table data but output DOCX table is missing",
                    ))
                continue

            matched += 1
            _compare_table_numbers(
                dsd_stmt.table, out_stmt.table,
                f"FS:{dsd_stmt.statement_type.value}",
                report,
            )
    else:
        # Path B: output has no FinancialStatement objects — match by title
        report.add(ReviewItem(
            severity="INFO",
            category="number",
            location="document",
            message="Output DOCX has no FinancialStatement objects; using table-title matching",
        ))

        for dsd_stmt in dsd_stmts:
            if dsd_stmt.table is None:
                continue
            out_table = _find_table_by_statement_type(
                dsd_stmt.statement_type, all_output_tables,
            )
            if out_table is not None:
                matched += 1
                _compare_table_numbers(
                    dsd_stmt.table, out_table,
                    f"FS:{dsd_stmt.statement_type.value}",
                    report,
                )
            else:
                report.add(ReviewItem(
                    severity="WARNING",
                    category="number",
                    location=f"Financial Statement: {dsd_stmt.title or dsd_stmt.statement_type.value}",
                    message="No matching table found in output DOCX by title search",
                ))

    report.add(ReviewItem(
        severity="INFO",
        category="number",
        location="document",
        message=f"Matched {matched}/{len(dsd_stmts)} financial statement tables for number comparison",
    ))

    # Also compare note-level tables
    _compare_note_tables(dsd_doc, output_doc, report)


def _collect_all_tables(doc: ParsedDocument) -> list[tuple[str, TableData]]:
    """Collect all tables from a document with descriptive labels."""
    tables = []
    for section in doc.sections:
        for fs in section.financial_statements:
            if fs.table is not None:
                tables.append((fs.title or fs.statement_type.value, fs.table))
        for note in section.notes:
            for elem in note.elements:
                if elem.table is not None:
                    tables.append((note.title, elem.table))
        for elem in section.elements:
            if elem.table is not None:
                tables.append((section.title, elem.table))
    return tables


def _find_table_by_statement_type(
    stmt_type: StatementType,
    all_tables: list[tuple[str, TableData]],
) -> TableData | None:
    """
    Search all output tables for one whose title/header matches the given
    StatementType.  Uses both the table title and header row text.
    """
    # Keywords per statement type
    keywords: dict[StatementType, list[str]] = {
        StatementType.BALANCE_SHEET: [
            "balance sheet", "financial position", "statement of financial position",
        ],
        StatementType.INCOME_STATEMENT: [
            "income", "comprehensive income", "profit or loss",
            "statement of comprehensive income",
        ],
        StatementType.CHANGES_IN_EQUITY: [
            "changes in equity", "equity",
        ],
        StatementType.CASH_FLOW: [
            "cash flow", "cash flows",
        ],
    }
    kws = keywords.get(stmt_type, [])
    if not kws:
        return None

    for title, table in all_tables:
        # Check the label/title
        combined = title.lower()
        # Also check header row text
        for row in table.headers:
            for cell in row.cells:
                combined += " " + cell.text.lower()

        for kw in kws:
            if kw in combined:
                return table
    return None


def _compare_table_numbers(
    dsd_table: TableData,
    out_table: TableData,
    location_prefix: str,
    report: ReviewReport,
) -> None:
    """Compare numbers row-by-row between two tables."""
    dsd_nums = _table_numbers(dsd_table)
    out_nums = _table_numbers(out_table)

    # Build a map of (row, col) -> value for the output
    out_map: dict[tuple[int, int], tuple[str, int | float]] = {}
    for r, c, text, val in out_nums:
        out_map[(r, c)] = (text, val)

    mismatches = 0
    for r, c, dsd_text, dsd_val in dsd_nums:
        if (r, c) not in out_map:
            # Could be structural difference — row counts may differ
            # Try to find by row label matching instead of exact position
            label = _row_label(dsd_table.rows[r]) if r < len(dsd_table.rows) else ""
            report.add(ReviewItem(
                severity="WARNING",
                category="number",
                location=f"{location_prefix} row {r} col {c} ({label})",
                message="Numeric cell in DSD has no corresponding cell in output",
                expected=dsd_text,
                found="(missing)",
            ))
            mismatches += 1
            continue

        out_text, out_val = out_map[(r, c)]
        if not _values_equal(dsd_val, out_val):
            label = _row_label(dsd_table.rows[r]) if r < len(dsd_table.rows) else ""
            report.add(ReviewItem(
                severity="CRITICAL",
                category="number",
                location=f"{location_prefix} row {r} col {c} ({label})",
                message="Number mismatch",
                expected=f"{dsd_text} (={dsd_val})",
                found=f"{out_text} (={out_val})",
            ))
            mismatches += 1

    if mismatches == 0 and dsd_nums:
        report.add(ReviewItem(
            severity="INFO",
            category="number",
            location=location_prefix,
            message=f"All {len(dsd_nums)} numeric cells match",
        ))


def _values_equal(a: int | float, b: int | float) -> bool:
    """Check if two values are equal within tolerance."""
    if isinstance(a, int) and isinstance(b, int):
        return abs(a - b) <= TOLERANCE
    return abs(float(a) - float(b)) <= TOLERANCE


def _compare_note_tables(
    dsd_doc: ParsedDocument,
    output_doc: ParsedDocument,
    report: ReviewReport,
) -> None:
    """Compare tables within notes (beyond the main financial statements)."""
    dsd_notes = dsd_doc.get_all_notes()
    output_notes = output_doc.get_all_notes()

    # Build a map of note number -> note for output
    out_note_map: dict[str, list[TableData]] = {}
    for note in output_notes:
        tables = [e.table for e in note.elements if e.table is not None]
        if tables:
            out_note_map[note.number] = tables

    note_table_mismatches = 0
    for dsd_note in dsd_notes:
        dsd_tables = [e.table for e in dsd_note.elements if e.table is not None]
        if not dsd_tables:
            continue

        out_tables = out_note_map.get(dsd_note.number, [])
        if not out_tables:
            # Not necessarily an error — notes may be restructured
            continue

        # Compare tables by position
        for t_idx, dsd_tbl in enumerate(dsd_tables):
            if t_idx < len(out_tables):
                _compare_table_numbers(
                    dsd_tbl, out_tables[t_idx],
                    f"Note {dsd_note.number} table {t_idx}",
                    report,
                )

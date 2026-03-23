"""
Balance checker — verify accounting equations hold in the output DOCX.

Equations checked:
  - Balance Sheet: Total Assets == Total Liabilities + Total Equity
  - Income Statement: Gross Profit == Revenue - COGS
  - Cash Flow: Ending Cash == Beginning Cash + Net change from activities
"""

from __future__ import annotations

import re

from ir_schema import ParsedDocument, FinancialStatement, StatementType, TableData, TableRow
from utils.number_format import parse_korean_number
from skills.review.review_report import ReviewItem, ReviewReport


# Tolerance for balance checks (same as number_validator)
TOLERANCE = 1


def check_balances(
    output_doc: ParsedDocument,
    report: ReviewReport,
) -> None:
    """
    Verify accounting equations for each financial statement in the output DOCX.
    Adds ReviewItems for any equation that doesn't balance.
    """
    stmts = output_doc.get_financial_statements()

    for stmt in stmts:
        if stmt.table is None:
            continue
        if stmt.statement_type == StatementType.BALANCE_SHEET:
            _check_balance_sheet(stmt, report)
        elif stmt.statement_type == StatementType.INCOME_STATEMENT:
            _check_income_statement(stmt, report)
        elif stmt.statement_type == StatementType.CASH_FLOW:
            _check_cash_flow(stmt, report)


# ── Balance Sheet ────────────────────────────────────────────────

def _check_balance_sheet(stmt: FinancialStatement, report: ReviewReport) -> None:
    """Total Assets == Total Liabilities + Total Equity."""
    table = stmt.table
    if table is None:
        return

    values = _extract_labeled_values(table)

    for col_idx in _numeric_columns(table):
        total_assets = _find_value(values, col_idx, [
            "total assets", "assets, total",
        ])
        total_liabilities = _find_value(values, col_idx, [
            "total liabilities", "liabilities, total",
        ])
        total_equity = _find_value(values, col_idx, [
            "total equity", "total stockholders' equity",
            "total shareholders' equity", "equity, total",
        ])
        total_le = _find_value(values, col_idx, [
            "total liabilities and equity",
            "total liabilities and stockholders' equity",
            "total liabilities and shareholders' equity",
        ])

        # Method 1: Total Assets == Total Liabilities and Equity (single row)
        if total_assets is not None and total_le is not None:
            if not _close(total_assets, total_le):
                report.add(ReviewItem(
                    severity="CRITICAL",
                    category="balance",
                    location=f"Balance Sheet col {col_idx}",
                    message="Total Assets != Total Liabilities and Equity",
                    expected=f"Total Assets = {total_assets:,}",
                    found=f"Total L+E = {total_le:,}",
                ))
            else:
                report.add(ReviewItem(
                    severity="INFO",
                    category="balance",
                    location=f"Balance Sheet col {col_idx}",
                    message="Total Assets == Total Liabilities and Equity (balanced)",
                ))
            continue

        # Method 2: Total Assets == Total Liabilities + Total Equity
        if total_assets is not None and total_liabilities is not None and total_equity is not None:
            computed = total_liabilities + total_equity
            if not _close(total_assets, computed):
                report.add(ReviewItem(
                    severity="CRITICAL",
                    category="balance",
                    location=f"Balance Sheet col {col_idx}",
                    message="Total Assets != Total Liabilities + Total Equity",
                    expected=f"Total Assets = {total_assets:,}",
                    found=f"Liabilities ({total_liabilities:,}) + Equity ({total_equity:,}) = {computed:,}",
                ))
            else:
                report.add(ReviewItem(
                    severity="INFO",
                    category="balance",
                    location=f"Balance Sheet col {col_idx}",
                    message="Assets == Liabilities + Equity (balanced)",
                ))


# ── Income Statement ────────────────────────────────────────────

def _check_income_statement(stmt: FinancialStatement, report: ReviewReport) -> None:
    """Gross Profit == Revenue - COGS."""
    table = stmt.table
    if table is None:
        return

    values = _extract_labeled_values(table)

    for col_idx in _numeric_columns(table):
        revenue = _find_value(values, col_idx, [
            "revenue", "net revenue", "sales", "net sales", "operating revenue",
        ])
        cogs = _find_value(values, col_idx, [
            "cost of sales", "cost of goods sold", "cost of revenue", "cogs",
        ])
        gross_profit = _find_value(values, col_idx, [
            "gross profit", "gross margin",
        ])

        if revenue is not None and cogs is not None and gross_profit is not None:
            computed = revenue - abs(cogs)  # COGS may be stored as positive
            # Also try with cogs as-is (could be negative)
            computed_alt = revenue + cogs if cogs < 0 else revenue - cogs
            if _close(gross_profit, computed) or _close(gross_profit, computed_alt):
                report.add(ReviewItem(
                    severity="INFO",
                    category="balance",
                    location=f"Income Statement col {col_idx}",
                    message="Gross Profit == Revenue - COGS (balanced)",
                ))
            else:
                report.add(ReviewItem(
                    severity="WARNING",
                    category="balance",
                    location=f"Income Statement col {col_idx}",
                    message="Gross Profit != Revenue - COGS",
                    expected=f"Revenue ({revenue:,}) - COGS ({cogs:,}) = {computed:,}",
                    found=f"Gross Profit = {gross_profit:,}",
                ))


# ── Cash Flow ────────────────────────────────────────────────────

def _check_cash_flow(stmt: FinancialStatement, report: ReviewReport) -> None:
    """Ending Cash == Beginning Cash + Operating + Investing + Financing."""
    table = stmt.table
    if table is None:
        return

    values = _extract_labeled_values(table)

    for col_idx in _numeric_columns(table):
        beginning = _find_value(values, col_idx, [
            "cash and cash equivalents at beginning",
            "beginning balance", "cash at beginning",
            "cash and cash equivalents, beginning",
        ])
        ending = _find_value(values, col_idx, [
            "cash and cash equivalents at end",
            "ending balance", "cash at end",
            "cash and cash equivalents, end",
        ])
        operating = _find_value(values, col_idx, [
            "net cash from operating activities",
            "net cash provided by operating activities",
            "cash flows from operating activities",
            "net cash used in operating activities",
        ])
        investing = _find_value(values, col_idx, [
            "net cash from investing activities",
            "net cash used in investing activities",
            "cash flows from investing activities",
        ])
        financing = _find_value(values, col_idx, [
            "net cash from financing activities",
            "net cash used in financing activities",
            "cash flows from financing activities",
        ])
        fx_effect = _find_value(values, col_idx, [
            "effect of exchange rate changes",
            "effect of foreign exchange",
            "foreign currency translation",
        ])

        if beginning is not None and ending is not None:
            components = [c for c in [operating, investing, financing, fx_effect] if c is not None]
            if components:
                computed = beginning + sum(components)
                if _close(ending, computed):
                    report.add(ReviewItem(
                        severity="INFO",
                        category="balance",
                        location=f"Cash Flow col {col_idx}",
                        message="Ending Cash == Beginning + activities (balanced)",
                    ))
                else:
                    report.add(ReviewItem(
                        severity="WARNING",
                        category="balance",
                        location=f"Cash Flow col {col_idx}",
                        message="Ending Cash != Beginning + Operating + Investing + Financing",
                        expected=f"Beginning ({beginning:,}) + activities = {computed:,}",
                        found=f"Ending Cash = {ending:,}",
                    ))


# ── Helpers ──────────────────────────────────────────────────────

def _extract_labeled_values(
    table: TableData,
) -> list[tuple[str, int, int | float]]:
    """
    Extract (row_label, col_idx, numeric_value) triples from a table.
    row_label is the text of the first non-numeric cell in the row.
    """
    results = []
    for row in table.rows:
        label = ""
        for cell in row.cells:
            text = cell.text.strip()
            if text and parse_korean_number(text) is None:
                label = text.lower().strip()
                break

        if not label:
            continue

        for c_idx, cell in enumerate(row.cells):
            val = parse_korean_number(cell.text.strip())
            if val is not None:
                results.append((label, c_idx, val))

    return results


def _find_value(
    values: list[tuple[str, int, int | float]],
    col_idx: int,
    keywords: list[str],
) -> int | float | None:
    """Find a value by label keywords at a specific column."""
    for label, c_idx, val in values:
        if c_idx != col_idx:
            continue
        for kw in keywords:
            if kw in label or label in kw:
                return val
    return None


def _numeric_columns(table: TableData) -> list[int]:
    """Identify which column indices contain numeric data."""
    col_counts: dict[int, int] = {}
    for row in table.rows:
        for c_idx, cell in enumerate(row.cells):
            if parse_korean_number(cell.text.strip()) is not None:
                col_counts[c_idx] = col_counts.get(c_idx, 0) + 1
    # Return columns that have at least 3 numeric cells
    return [c for c, cnt in sorted(col_counts.items()) if cnt >= 3]


def _close(a: int | float, b: int | float) -> bool:
    """Check if two values are equal within tolerance."""
    return abs(float(a) - float(b)) <= TOLERANCE

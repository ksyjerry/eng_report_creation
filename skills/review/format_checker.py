"""
Format checker — detect structural and formatting issues in the output DOCX.

Checks:
  - Empty tables (0 data rows)
  - Mismatched column counts across rows
  - Untranslated content markers ([NEEDS_TRANSLATION:...])
  - Header year correctness
  - XML parsing errors (malformed DOCX)
"""

from __future__ import annotations

import re
import zipfile
from lxml import etree

from ir_schema import ParsedDocument, DocxProfile, TableData, NoteElement, ElementType
from skills.review.review_report import ReviewItem, ReviewReport


def check_format(
    output_path: str,
    output_doc: ParsedDocument,
    dsd_doc: ParsedDocument,
    report: ReviewReport,
) -> None:
    """
    Run all format checks against the output DOCX.
    Adds ReviewItems for any issues found.
    """
    _check_empty_tables(output_doc, report)
    _check_column_consistency(output_doc, report)
    _check_untranslated_markers(output_doc, report)
    _check_header_years(output_doc, dsd_doc, report)
    _check_xml_validity(output_path, report)


def _check_empty_tables(doc: ParsedDocument, report: ReviewReport) -> None:
    """Flag tables with zero data rows."""
    table_idx = 0
    for section in doc.sections:
        # Financial statement tables
        for fs in section.financial_statements:
            if fs.table is not None:
                if len(fs.table.rows) == 0:
                    report.add(ReviewItem(
                        severity="CRITICAL",
                        category="format",
                        location=f"Financial Statement: {fs.title or fs.statement_type.value}",
                        message="Table has 0 data rows (empty table)",
                    ))
                table_idx += 1

        # Note tables
        for note in section.notes:
            for elem in note.elements:
                if elem.type == ElementType.TABLE and elem.table is not None:
                    if len(elem.table.rows) == 0:
                        report.add(ReviewItem(
                            severity="WARNING",
                            category="format",
                            location=f"Note {note.number}: {note.title} (table {table_idx})",
                            message="Table has 0 data rows (empty table)",
                        ))
                    table_idx += 1


def _check_column_consistency(doc: ParsedDocument, report: ReviewReport) -> None:
    """Check for tables where rows have different column counts."""
    tables = _all_tables(doc)

    for tbl_desc, table in tables:
        if not table.rows:
            continue

        col_counts = set()
        for row in table.headers + table.rows:
            # Compute effective column count considering colspan
            effective = sum(c.colspan for c in row.cells)
            col_counts.add(effective)

        if len(col_counts) > 1:
            report.add(ReviewItem(
                severity="WARNING",
                category="format",
                location=tbl_desc,
                message=f"Inconsistent column counts across rows: {sorted(col_counts)}",
            ))


def _check_untranslated_markers(doc: ParsedDocument, report: ReviewReport) -> None:
    """Check for [NEEDS_TRANSLATION:...] markers left in the output."""
    marker_pattern = re.compile(r"\[NEEDS_TRANSLATION:", re.IGNORECASE)
    found_count = 0

    for section in doc.sections:
        for note in section.notes:
            for elem in note.elements:
                if elem.text and marker_pattern.search(elem.text):
                    found_count += 1
                    report.add(ReviewItem(
                        severity="CRITICAL",
                        category="format",
                        location=f"Note {note.number}: {note.title}",
                        message=f"Untranslated content marker found: {elem.text[:100]}",
                    ))
                if elem.table is not None:
                    for row in elem.table.headers + elem.table.rows:
                        for cell in row.cells:
                            if marker_pattern.search(cell.text):
                                found_count += 1
                                report.add(ReviewItem(
                                    severity="CRITICAL",
                                    category="format",
                                    location=f"Note {note.number}: {note.title} (table cell)",
                                    message=f"Untranslated content in table: {cell.text[:100]}",
                                ))

        # Also check raw elements
        for elem in section.elements:
            if elem.text and marker_pattern.search(elem.text):
                found_count += 1
                report.add(ReviewItem(
                    severity="CRITICAL",
                    category="format",
                    location=f"Section: {section.title}",
                    message=f"Untranslated content marker: {elem.text[:100]}",
                ))

    if found_count == 0:
        report.add(ReviewItem(
            severity="INFO",
            category="format",
            location="document",
            message="No untranslated content markers found",
        ))


def _check_header_years(
    output_doc: ParsedDocument,
    dsd_doc: ParsedDocument,
    report: ReviewReport,
) -> None:
    """Check that financial statement headers contain the correct years."""
    expected_current = dsd_doc.meta.period_current
    expected_prior = dsd_doc.meta.period_prior

    if not expected_current:
        return

    stmts = output_doc.get_financial_statements()
    for stmt in stmts:
        if stmt.table is None:
            continue

        # Check header rows for year presence
        header_text = " ".join(
            cell.text for row in stmt.table.headers for cell in row.cells
        )

        if expected_current and expected_current not in header_text:
            report.add(ReviewItem(
                severity="WARNING",
                category="format",
                location=f"Financial Statement: {stmt.title or stmt.statement_type.value}",
                message=f"Current period year '{expected_current}' not found in table headers",
                expected=expected_current,
                found=header_text[:200],
            ))

        if expected_prior and expected_prior not in header_text:
            report.add(ReviewItem(
                severity="INFO",
                category="format",
                location=f"Financial Statement: {stmt.title or stmt.statement_type.value}",
                message=f"Prior period year '{expected_prior}' not found in table headers",
                expected=expected_prior,
                found=header_text[:200],
            ))


def _check_xml_validity(output_path: str, report: ReviewReport) -> None:
    """Verify the DOCX is a valid ZIP with parseable XML."""
    try:
        with zipfile.ZipFile(output_path, "r") as zf:
            names = zf.namelist()
            if "word/document.xml" not in names:
                report.add(ReviewItem(
                    severity="CRITICAL",
                    category="format",
                    location="DOCX structure",
                    message="Missing word/document.xml — invalid DOCX file",
                ))
                return

            # Try to parse document.xml
            with zf.open("word/document.xml") as f:
                try:
                    etree.parse(f)
                except etree.XMLSyntaxError as e:
                    report.add(ReviewItem(
                        severity="CRITICAL",
                        category="format",
                        location="word/document.xml",
                        message=f"XML parsing error: {e}",
                    ))
                    return

            report.add(ReviewItem(
                severity="INFO",
                category="format",
                location="DOCX structure",
                message=f"Valid DOCX with {len(names)} entries",
            ))

    except zipfile.BadZipFile as e:
        report.add(ReviewItem(
            severity="CRITICAL",
            category="format",
            location="DOCX file",
            message=f"Not a valid ZIP/DOCX file: {e}",
        ))
    except FileNotFoundError:
        report.add(ReviewItem(
            severity="CRITICAL",
            category="format",
            location="DOCX file",
            message=f"Output file not found: {output_path}",
        ))


def _all_tables(doc: ParsedDocument) -> list[tuple[str, TableData]]:
    """Collect all tables from the document with descriptive labels."""
    tables = []
    for section in doc.sections:
        for fs in section.financial_statements:
            if fs.table is not None:
                desc = f"FS: {fs.title or fs.statement_type.value}"
                tables.append((desc, fs.table))
        for note in section.notes:
            for elem in note.elements:
                if elem.type == ElementType.TABLE and elem.table is not None:
                    desc = f"Note {note.number}: {note.title}"
                    tables.append((desc, elem.table))
    return tables

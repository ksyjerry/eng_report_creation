"""
Completeness checker — verify all DSD notes/tables appear in the output DOCX.

Counts expected vs found notes, tables, and paragraphs.
"""

from __future__ import annotations

import re

from ir_schema import ParsedDocument, Note, NoteElement, ElementType
from skills.review.review_report import ReviewItem, ReviewReport


def check_completeness(
    dsd_doc: ParsedDocument,
    output_doc: ParsedDocument,
    report: ReviewReport,
) -> None:
    """
    Check that every DSD note has a matching section in the output DOCX,
    and that every DSD table has a corresponding table in output.

    Adds ReviewItems to the report for missing content.
    """
    dsd_notes = dsd_doc.get_all_notes()
    output_notes = output_doc.get_all_notes()

    # Build lookup by note number for output
    out_note_by_number: dict[str, Note] = {}
    for note in output_notes:
        if note.number:
            out_note_by_number[note.number] = note

    # Also build a title-based lookup (normalized)
    out_note_by_title: dict[str, Note] = {}
    for note in output_notes:
        if note.title:
            key = _normalize_title(note.title)
            out_note_by_title[key] = note

    # Track counts
    expected_notes = len(dsd_notes)
    found_notes = 0
    expected_tables = 0
    found_tables = 0
    expected_paragraphs = 0
    found_paragraphs = 0
    missing_notes: list[str] = []

    for dsd_note in dsd_notes:
        # Try to find matching output note
        out_note = out_note_by_number.get(dsd_note.number)
        if out_note is None and dsd_note.title:
            out_note = out_note_by_title.get(_normalize_title(dsd_note.title))

        if out_note is None:
            missing_notes.append(
                f"Note {dsd_note.number}: {dsd_note.title}"
            )
            # Count all elements as missing
            for elem in dsd_note.elements:
                if elem.type == ElementType.TABLE:
                    expected_tables += 1
                elif elem.type == ElementType.PARAGRAPH:
                    expected_paragraphs += 1
            continue

        found_notes += 1

        # Compare elements within the note
        dsd_tables = [e for e in dsd_note.elements if e.type == ElementType.TABLE]
        out_tables = [e for e in out_note.elements if e.type == ElementType.TABLE]
        dsd_paras = [e for e in dsd_note.elements if e.type == ElementType.PARAGRAPH]
        out_paras = [e for e in out_note.elements if e.type == ElementType.PARAGRAPH]

        expected_tables += len(dsd_tables)
        found_tables += min(len(out_tables), len(dsd_tables))
        expected_paragraphs += len(dsd_paras)
        found_paragraphs += min(len(out_paras), len(dsd_paras))

        if len(out_tables) < len(dsd_tables):
            report.add(ReviewItem(
                severity="WARNING",
                category="completeness",
                location=f"Note {dsd_note.number}: {dsd_note.title}",
                message=f"Missing tables: expected {len(dsd_tables)}, found {len(out_tables)}",
                expected=str(len(dsd_tables)),
                found=str(len(out_tables)),
            ))

    # Report missing notes
    for note_desc in missing_notes:
        report.add(ReviewItem(
            severity="WARNING",
            category="completeness",
            location=note_desc,
            message="Note present in DSD but not found in output DOCX",
        ))

    # Check financial statements
    dsd_fs = dsd_doc.get_financial_statements()
    out_fs = output_doc.get_financial_statements()
    out_fs_types = {s.statement_type for s in out_fs}

    for dsd_stmt in dsd_fs:
        if dsd_stmt.statement_type not in out_fs_types:
            report.add(ReviewItem(
                severity="CRITICAL",
                category="completeness",
                location=f"Financial Statement: {dsd_stmt.title or dsd_stmt.statement_type.value}",
                message="Financial statement present in DSD but missing from output DOCX",
            ))

    # Summary info items
    report.add(ReviewItem(
        severity="INFO",
        category="completeness",
        location="document",
        message=(
            f"Notes: {found_notes}/{expected_notes} found | "
            f"Tables: {found_tables}/{expected_tables} found | "
            f"Paragraphs: {found_paragraphs}/{expected_paragraphs} found"
        ),
    ))

    if missing_notes:
        report.add(ReviewItem(
            severity="INFO",
            category="completeness",
            location="document",
            message=f"{len(missing_notes)} notes missing from output",
        ))


def _normalize_title(title: str) -> str:
    """Normalize a note title for fuzzy matching."""
    # Remove numbering, punctuation, extra whitespace
    text = re.sub(r"^\d+[\.\)]\s*", "", title.strip())
    text = re.sub(r"\s+", " ", text).lower().strip()
    return text

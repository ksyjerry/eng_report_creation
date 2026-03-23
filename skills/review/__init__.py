"""
review skill — Validate generated English financial statements.

Takes the generated DOCX output, re-parses it, and validates against the
original DSD source data. Produces a ReviewReport with errors, warnings,
and pass/fail status.

Entry point: review(output_path, dsd_doc, docx_profile) -> ReviewReport
"""

from __future__ import annotations

import os
import sys

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ir_schema import ParsedDocument, DocxProfile
from skills.parse_docx import parse_docx
from skills.review.review_report import ReviewReport, ReviewItem
from skills.review.number_validator import validate_numbers
from skills.review.completeness_checker import check_completeness
from skills.review.balance_checker import check_balances
from skills.review.format_checker import check_format


def review(
    output_path: str,
    dsd_doc: ParsedDocument,
    docx_profile: DocxProfile | None = None,
) -> ReviewReport:
    """
    Validate a generated DOCX against its DSD source data.

    Args:
        output_path:   Path to the generated DOCX file.
        dsd_doc:       ParsedDocument from the DSD source (the ground truth).
        docx_profile:  Optional DocxProfile for format-aware checks.

    Returns:
        ReviewReport with all findings, severity levels, and pass/fail status.
    """
    report = ReviewReport()

    # Step 1: Re-parse the output DOCX
    try:
        output_doc = parse_docx(output_path)
    except Exception as e:
        report.add(ReviewItem(
            severity="CRITICAL",
            category="format",
            location="output DOCX",
            message=f"Failed to parse output DOCX: {e}",
        ))
        report.finalize()
        return report

    # Step 2: Format checks (can run even if other checks fail)
    try:
        check_format(output_path, output_doc, dsd_doc, report)
    except Exception as e:
        report.add(ReviewItem(
            severity="WARNING",
            category="format",
            location="format_checker",
            message=f"Format check raised an error: {e}",
        ))

    # Step 3: Completeness checks
    try:
        check_completeness(dsd_doc, output_doc, report)
    except Exception as e:
        report.add(ReviewItem(
            severity="WARNING",
            category="completeness",
            location="completeness_checker",
            message=f"Completeness check raised an error: {e}",
        ))

    # Step 4: Number validation
    try:
        validate_numbers(dsd_doc, output_doc, report)
    except Exception as e:
        report.add(ReviewItem(
            severity="WARNING",
            category="number",
            location="number_validator",
            message=f"Number validation raised an error: {e}",
        ))

    # Step 5: Balance checks (on the output DOCX itself)
    try:
        check_balances(output_doc, report)
    except Exception as e:
        report.add(ReviewItem(
            severity="WARNING",
            category="balance",
            location="balance_checker",
            message=f"Balance check raised an error: {e}",
        ))

    # Finalize: compute summary and status
    report.finalize()
    return report

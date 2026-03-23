"""
map_sections skill — Map DSD (Korean) notes to DOCX (English) notes
and produce a list of Changes to transform the DOCX template.

Entry point: map_sections(dsd_doc, docx_doc) -> list[Change]

Two modes:
  1. Rule-based matching (implemented) — note number + title similarity
  2. LLM-assisted matching (TODO) — for ambiguous cases
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ir_schema import ParsedDocument
from skills.write_docx.change_model import Change
from skills.map_sections.section_matcher import (
    match_sections,
    find_unmatched_docx_notes,
    SectionMapping,
)
from skills.map_sections.structure_differ import (
    diff_all_sections,
    SectionDiff,
    YearRoll,
)
from skills.map_sections.change_generator import generate_changes


def map_sections(
    dsd_doc: ParsedDocument,
    docx_doc: ParsedDocument,
) -> list[Change]:
    """
    Map DSD sections to DOCX sections and produce Changes.

    Args:
        dsd_doc:  ParsedDocument from parse_dsd (Korean source, current year).
        docx_doc: ParsedDocument from parse_docx (English template, prior year).

    Returns:
        List of Change objects describing how to update the DOCX template.
    """
    # 1. Collect notes from both documents
    dsd_notes = dsd_doc.get_all_notes()
    docx_notes = docx_doc.get_all_notes()

    # 2. Match DSD notes to DOCX notes (rule-based)
    mappings = match_sections(dsd_notes, docx_notes)

    # 3. Find DOCX notes not matched (candidates for deletion)
    deleted_docx = find_unmatched_docx_notes(mappings, docx_notes)

    # 4. Diff matched section pairs
    section_diffs, year_roll = diff_all_sections(mappings, dsd_doc, docx_doc)

    # 5. Generate Change objects
    changes = generate_changes(section_diffs, year_roll, deleted_docx)

    return changes


def map_sections_detailed(
    dsd_doc: ParsedDocument,
    docx_doc: ParsedDocument,
) -> tuple[list[Change], list[SectionMapping], list[SectionDiff], YearRoll | None]:
    """
    Like map_sections() but also returns intermediate results for debugging.

    Returns:
        (changes, mappings, section_diffs, year_roll)
    """
    dsd_notes = dsd_doc.get_all_notes()
    docx_notes = docx_doc.get_all_notes()

    mappings = match_sections(dsd_notes, docx_notes)
    deleted_docx = find_unmatched_docx_notes(mappings, docx_notes)
    section_diffs, year_roll = diff_all_sections(mappings, dsd_doc, docx_doc)
    changes = generate_changes(section_diffs, year_roll, deleted_docx)

    return changes, mappings, section_diffs, year_roll

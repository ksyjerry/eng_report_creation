"""
translate skill — Translate Korean financial statement content to English.

Takes Change objects containing Korean text and produces English translations.
Uses a three-tier approach:
1. Auto-built glossary from matched DSD/DOCX prior-year data
2. IFRS standard terminology dictionary
3. PwC GenAI Gateway for remaining content (optional)

Entry point: translate_changes(changes, dsd_doc, docx_doc, api_key=None)
"""

from __future__ import annotations

import os
import re
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ir_schema import ChangeType, ParsedDocument
from skills.write_docx.change_model import Change
from skills.translate.glossary_builder import build_glossary, Glossary
from skills.translate.translator import (
    translate_label,
    translate_labels_batch,
    translate_paragraph,
    translate_note_title,
)

logger = logging.getLogger(__name__)

# Regex for detecting Korean
_KOREAN_RE = re.compile(r"[\uac00-\ud7af\u3130-\u318f]")


def _contains_korean(text: str) -> bool:
    """Check if text contains Korean characters."""
    return bool(_KOREAN_RE.search(text))


def _translate_change(
    change: Change,
    glossary: Glossary,
    api_key: str | None = None,
) -> Change:
    """
    Translate Korean text within a single Change object.

    Modifies the Change in-place and returns it.
    Translation targets depend on the change type:
    - UPDATE_VALUES: translate label cells (col 0 typically)
    - UPDATE_TEXT: translate the value field
    - ADD_ROW: translate label cells in row dicts
    - ADD_TABLE: translate content tuples
    - ADD_NOTE: translate title (value) and content tuples
    """

    if change.type == ChangeType.UPDATE_VALUES:
        # Translate label values in the values dict
        # Typically col 0 is the label; numeric columns stay as-is
        new_values: dict[int, str] = {}
        for col_idx, text in change.values.items():
            if _contains_korean(text):
                new_values[col_idx] = translate_label(
                    text, glossary, api_key=api_key
                )
            else:
                new_values[col_idx] = text
        change.values = new_values

    elif change.type == ChangeType.UPDATE_TEXT:
        if change.value and _contains_korean(change.value):
            change.value = translate_paragraph(
                change.value, glossary, api_key=api_key
            )

    elif change.type == ChangeType.ADD_ROW:
        new_rows: list[dict[int, str]] = []
        for row_dict in change.rows:
            new_row: dict[int, str] = {}
            for col_idx, text in row_dict.items():
                if _contains_korean(text):
                    new_row[col_idx] = translate_label(
                        text, glossary, api_key=api_key
                    )
                else:
                    new_row[col_idx] = text
            new_rows.append(new_row)
        change.rows = new_rows

    elif change.type in (ChangeType.ADD_TABLE, ChangeType.ADD_NOTE):
        # Translate the title (stored in value)
        if change.value and _contains_korean(change.value):
            change.value = translate_note_title(
                change.value, glossary, api_key=api_key
            )

        # Translate content tuples
        new_content: list[tuple[str, str]] = []
        for content_type, content_text in change.content:
            if _contains_korean(content_text):
                if content_type == "paragraph":
                    translated = translate_paragraph(
                        content_text, glossary, api_key=api_key
                    )
                elif content_type == "subtitle":
                    translated = translate_note_title(
                        content_text, glossary, api_key=api_key
                    )
                elif content_type == "table_row":
                    # Table rows are pipe-separated: translate label parts
                    parts = content_text.split(" | ")
                    translated_parts = []
                    for part in parts:
                        if _contains_korean(part):
                            translated_parts.append(
                                translate_label(part, glossary, api_key=api_key)
                            )
                        else:
                            translated_parts.append(part)
                    translated = " | ".join(translated_parts)
                else:
                    translated = translate_paragraph(
                        content_text, glossary, api_key=api_key
                    )
                new_content.append((content_type, translated))
            else:
                new_content.append((content_type, content_text))
        change.content = new_content

    elif change.type == ChangeType.DELETE_NOTE:
        # No translation needed for deletions, but translate the title
        # for logging/reference
        pass

    return change


def translate_changes(
    changes: list[Change],
    dsd_doc: ParsedDocument,
    docx_doc: ParsedDocument,
    api_key: str | None = None,
) -> list[Change]:
    """
    Translate Korean text in Change objects to English.

    Builds a glossary from the DSD/DOCX document pair, then translates
    all Korean content in the changes using glossary-first, API-fallback.

    Args:
        changes: List of Change objects (may contain Korean text).
        dsd_doc: Parsed Korean DSD document (for glossary building).
        docx_doc: Parsed English DOCX document (for glossary building).
        api_key: Optional PwC GenAI Gateway API key. If None, untranslated
                 items are marked with [NEEDS_TRANSLATION: ...].

    Returns:
        The same list of Change objects with Korean text translated to English.
    """
    # Build glossary from document pair
    glossary = build_glossary(dsd_doc, docx_doc)
    logger.info(f"Built glossary with {len(glossary)} entries")

    # Count Korean-containing changes for logging
    ko_count = 0
    for c in changes:
        has_ko = False
        if c.value and _contains_korean(c.value):
            has_ko = True
        for v in c.values.values():
            if _contains_korean(v):
                has_ko = True
                break
        if has_ko:
            ko_count += 1

    logger.info(f"Translating {ko_count} changes containing Korean text")

    # Translate each change
    for change in changes:
        _translate_change(change, glossary, api_key=api_key)

    return changes

"""
Split a DOCX document into sections based on paragraph styles.

ABCTitle paragraphs mark note boundaries (main notes).
Subtitle paragraphs mark subsections within a note.
Tables are associated with their containing section.
"""

from __future__ import annotations

import re
from lxml import etree
from docx import Document

from ir_schema import (
    Section, Note, NoteElement, ElementType, TableData, DocxProfile,
)
from utils.xml_helpers import w, find_w, findall_w

from .docx_element_indexer import ElementIndex
from .docx_table_parser import parse_table, ColumnMapping


def parse_sections(
    doc: Document,
    body_elements: list[ElementIndex],
    profile: DocxProfile,
) -> list[Section]:
    """
    Walk the document body elements and split into sections.

    Each ABCTitle paragraph starts a new note section.
    Content before the first ABCTitle goes into a "preamble" section.
    """
    title_style = profile.title_style or "ABCTitle"
    subtitle_style = profile.subtitle_style or "Subtitle"

    # Build a lookup: body_index → docx Table object
    table_map = _build_table_map(doc, body_elements)

    sections: list[Section] = []
    current_section: Section | None = None
    current_note: Note | None = None
    note_counter = 0
    section_counter = 0

    for elem in body_elements:
        if elem.tag == "p":
            style = _get_paragraph_style(elem.element)
            text = _get_paragraph_text(elem.element)

            if style == title_style or _style_matches_title(style, title_style):
                # Skip empty ABCTitle paragraphs (SBL has blank ones)
                if not text.strip():
                    continue

                # Skip ABCTitle paragraphs that are FS footers, not note titles
                # e.g., "The above ... should be read in conjunction with..."
                if _is_fs_footer(text):
                    # Treat as regular paragraph in current section
                    if current_note is not None:
                        current_note.elements.append(NoteElement(
                            type=ElementType.PARAGRAPH,
                            text=text.strip(),
                            depth=0,
                        ))
                    elif current_section is not None:
                        current_section.elements.append(NoteElement(
                            type=ElementType.PARAGRAPH,
                            text=text.strip(),
                            depth=0,
                        ))
                    continue

                # Start a new note/section
                # Flush previous section
                if current_note is not None and current_section is not None:
                    current_section.notes.append(current_note)
                if current_section is not None:
                    sections.append(current_section)

                note_counter += 1
                section_counter += 1
                number, clean_title = _extract_note_number(text, note_counter)

                current_section = Section(
                    section_type="notes",
                    section_index=section_counter,
                    title=clean_title or text.strip(),
                )
                current_note = Note(
                    id=f"note_{note_counter}",
                    number=number,
                    title=clean_title or text.strip(),
                )
                # Add the title paragraph as an element
                current_note.elements.append(NoteElement(
                    type=ElementType.PARAGRAPH,
                    text=text.strip(),
                    depth=0,
                    numbering=number,
                ))

            elif style == subtitle_style or _style_matches_subtitle(style, subtitle_style):
                # Subsection within current note
                if current_note is not None:
                    sub_number, sub_title = _extract_note_number(text, 0)
                    current_note.elements.append(NoteElement(
                        type=ElementType.SUBTITLE,
                        text=text.strip(),
                        depth=1,
                        numbering=sub_number,
                    ))
                elif current_section is None:
                    # Subtitle before any title → preamble section
                    section_counter += 1
                    current_section = Section(
                        section_type="preamble",
                        section_index=section_counter,
                        title="Preamble",
                    )
                    current_section.elements.append(NoteElement(
                        type=ElementType.SUBTITLE,
                        text=text.strip(),
                        depth=1,
                    ))

            else:
                # Regular paragraph
                if current_note is not None:
                    current_note.elements.append(NoteElement(
                        type=ElementType.PARAGRAPH,
                        text=text.strip(),
                        depth=0,
                    ))
                else:
                    # Before first ABCTitle → preamble
                    if current_section is None:
                        section_counter += 1
                        current_section = Section(
                            section_type="preamble",
                            section_index=section_counter,
                            title="Preamble",
                        )
                    current_section.elements.append(NoteElement(
                        type=ElementType.PARAGRAPH,
                        text=text.strip(),
                        depth=0,
                    ))

        elif elem.tag == "tbl":
            # Parse the table
            docx_tbl = table_map.get(elem.body_index)
            if docx_tbl is not None:
                table_data, col_map = parse_table(
                    docx_tbl,
                    source_index=elem.body_index,
                    profile=profile,
                )

                if current_note is not None:
                    current_note.elements.append(NoteElement(
                        type=ElementType.TABLE,
                        table=table_data,
                        depth=0,
                    ))
                else:
                    if current_section is None:
                        section_counter += 1
                        current_section = Section(
                            section_type="preamble",
                            section_index=section_counter,
                            title="Preamble",
                        )
                    current_section.elements.append(NoteElement(
                        type=ElementType.TABLE,
                        table=table_data,
                        depth=0,
                    ))

        # Other tags (bookmarkEnd, sectPr, etc.) are ignored

    # Flush last section
    if current_note is not None and current_section is not None:
        current_section.notes.append(current_note)
    if current_section is not None:
        sections.append(current_section)

    return sections


# ── Helpers ─────────────────────────────────────────────────────

def _build_table_map(
    doc: Document,
    body_elements: list[ElementIndex],
) -> dict[int, object]:
    """
    Map body_index → python-docx Table object.

    python-docx's doc.tables is a flat list; we match by comparing
    the underlying lxml element identity.
    """
    # Build element→Table lookup
    elem_to_table = {}
    for tbl in doc.tables:
        elem_to_table[id(tbl._tbl)] = tbl

    result = {}
    for elem in body_elements:
        if elem.tag == "tbl":
            tbl_obj = elem_to_table.get(id(elem.element))
            if tbl_obj is not None:
                result[elem.body_index] = tbl_obj

    return result


def _get_paragraph_style(p_element) -> str:
    """Get the style name from a <w:p> element."""
    p_pr = find_w(p_element, "w:pPr")
    if p_pr is not None:
        p_style = find_w(p_pr, "w:pStyle")
        if p_style is not None:
            return p_style.get(w("val"), "")
    return ""


def _get_paragraph_text(p_element) -> str:
    """Extract combined text from all <w:t> elements in a paragraph."""
    texts = []
    for t_el in p_element.iter(w("t")):
        if t_el.text:
            texts.append(t_el.text)
    return "".join(texts)


def _style_matches_title(style_id: str, expected: str) -> bool:
    """Check if a style ID matches the title style (handles aliases)."""
    # python-docx resolves style names, but raw XML uses style IDs
    # ABCTitle style might have ID "ABCTitle" or similar
    if not expected:
        return False
    return style_id.lower() == expected.lower()


def _style_matches_subtitle(style_id: str, expected: str) -> bool:
    """Check if a style ID matches the subtitle style."""
    if not expected:
        return False
    # Handle common aliases: "aff5" is often the internal ID for "Subtitle"
    subtitle_ids = {expected.lower(), "aff5", "subtitle"}
    return style_id.lower() in subtitle_ids


def _extract_note_number(text: str, fallback_number: int) -> tuple[str, str]:
    """
    Extract note number and clean title from paragraph text.

    Examples:
        "1. General Information" → ("1", "General Information")
        "General Information" → ("1", "General Information")  (using fallback)
        "2.1 Basis of Preparation" → ("2.1", "Basis of Preparation")
    """
    text = text.strip()
    if not text:
        return (str(fallback_number), "")

    # Pattern: "N." or "N.N" at start
    m = re.match(r"^(\d+(?:\.\d+)*)\s*\.?\s+(.+)$", text)
    if m:
        return (m.group(1), m.group(2).strip())

    # No number prefix → use fallback
    return (str(fallback_number), text)


def _is_fs_footer(text: str) -> bool:
    """
    Detect financial statement footer paragraphs that are styled as ABCTitle
    but are not actually note titles.

    Examples:
        "The above separate statements of cash flows should be read in
         conjunction with the accompanying notes."
    """
    lower = text.strip().lower()
    if "should be read in conjunction" in lower:
        return True
    if "the above" in lower and "statement" in lower:
        return True
    # Very long text is unlikely to be a note title
    if len(text.strip()) > 120:
        return True
    return False

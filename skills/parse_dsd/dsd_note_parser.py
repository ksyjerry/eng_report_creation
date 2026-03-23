"""
DSD Note parser.
Extracts notes from SECTION-2 blocks.
Detects note numbering patterns and builds Note structures.
"""

import re
from lxml import etree

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ir_schema import Note, NoteElement, ElementType, Section
from utils.xml_helpers import get_attr
from skills.parse_dsd.dsd_table_parser import parse_table, _get_cell_text


# Note numbering patterns (ordered by precedence)
_NOTE_PATTERNS = [
    # "1. 제목" - top-level note
    (r'^(\d+)\.\s+(.+)', 0),
    # "2.1.1 세부항목" - hierarchical
    (r'^(\d+\.\d+\.\d+)\s+(.+)', 2),
    # "2.1 세부항목" - hierarchical
    (r'^(\d+\.\d+)\s+(.+)', 1),
    # "(1) 소제목" - sub-note
    (r'^\((\d+)\)\s+(.+)', 1),
    # "① 항목" - circled number
    (r'^([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳])\s*(.+)', 2),
    # "가. 항목" - Korean letter
    (r'^([가나다라마바사아자차카타파하])\.\s+(.+)', 2),
]

# Map circled numbers to integers
_CIRCLED_NUMS = {c: str(i+1) for i, c in enumerate('①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳')}


def _detect_note_numbering(text: str) -> tuple[str, str, int] | None:
    """
    Detect if text starts with a note numbering pattern.

    Returns:
        (number, title, depth) or None if no pattern matched
    """
    text = text.strip()
    if not text:
        return None

    for pattern, depth in _NOTE_PATTERNS:
        m = re.match(pattern, text)
        if m:
            number = m.group(1)
            title = m.group(2).strip()
            # Normalize circled numbers
            if number in _CIRCLED_NUMS:
                number = _CIRCLED_NUMS[number]
            return (number, title, depth)

    return None


def _get_element_text(elem) -> str:
    """Get text content from a P or other element, handling &cr;."""
    text = etree.tostring(elem, method="text", encoding="unicode") or ""
    text = text.replace("&cr;", "\n")
    # Collapse whitespace within lines
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = re.sub(r'\s+', ' ', line).strip()
        if stripped:
            cleaned.append(stripped)
    return "\n".join(cleaned)


def parse_notes(section_elem, section_index: int = 0) -> Section:
    """
    Parse notes from a SECTION-2 element.

    Strategy:
    1. Walk through children (P, TABLE, etc.)
    2. When we encounter a P starting with "N. title", start a new Note
    3. Subsequent P and TABLE elements are added as NoteElements
    4. Sub-numbering ((1), ①, etc.) creates nested elements within the current note

    Args:
        section_elem: lxml Element for SECTION-2
        section_index: index for the section

    Returns:
        Section with notes populated
    """
    section = Section(
        section_type="notes",
        section_index=section_index,
    )

    # Get section title
    title_elem = section_elem.find('TITLE')
    if title_elem is not None:
        title_text = etree.tostring(title_elem, method="text", encoding="unicode") or ""
        section.title = re.sub(r'\s+', ' ', title_text).strip()

    # Walk through all elements in order
    notes: list[Note] = []
    current_note: Note | None = None
    note_counter = 0

    for elem in _iter_content_elements(section_elem):
        if elem.tag == 'P':
            text = _get_element_text(elem)
            if not text:
                continue

            # Check for note numbering
            numbering = _detect_note_numbering(text)

            if numbering:
                number, title, depth = numbering

                if depth == 0:
                    # Top-level note: start a new Note
                    current_note = Note(
                        id=f"note_{section_index}_{note_counter}",
                        number=number,
                        title=title,
                    )
                    notes.append(current_note)
                    note_counter += 1
                else:
                    # Sub-note: add as subtitle element
                    if current_note is None:
                        # Create implicit note for orphan sub-notes
                        current_note = Note(
                            id=f"note_{section_index}_{note_counter}",
                            number="0",
                            title="(서문)",
                        )
                        notes.append(current_note)
                        note_counter += 1

                    ne = NoteElement(
                        type=ElementType.SUBTITLE,
                        text=title,
                        depth=depth,
                        numbering=f"({number})" if depth == 1 and number.isdigit() else number,
                    )
                    current_note.elements.append(ne)
            else:
                # Regular paragraph
                if current_note is None:
                    # Text before the first note - create a preamble note
                    current_note = Note(
                        id=f"note_{section_index}_{note_counter}",
                        number="0",
                        title="(서문)",
                    )
                    notes.append(current_note)
                    note_counter += 1

                ne = NoteElement(
                    type=ElementType.PARAGRAPH,
                    text=text,
                    depth=0,
                )
                current_note.elements.append(ne)

        elif elem.tag == 'TABLE':
            border = get_attr(elem, 'BORDER', '0')
            # Parse the table
            table_data = parse_table(elem)

            if current_note is None:
                current_note = Note(
                    id=f"note_{section_index}_{note_counter}",
                    number="0",
                    title="(서문)",
                )
                notes.append(current_note)
                note_counter += 1

            ne = NoteElement(
                type=ElementType.TABLE,
                text="",
                depth=0,
                table=table_data,
            )
            current_note.elements.append(ne)

        elif elem.tag == 'PGBRK':
            if current_note is not None:
                ne = NoteElement(
                    type=ElementType.PAGE_BREAK,
                    text="",
                    depth=0,
                )
                current_note.elements.append(ne)

    # Filter out the preamble note if it's just whitespace
    filtered_notes = []
    for note in notes:
        if note.number == "0" and note.title == "(서문)":
            # Keep only if it has meaningful content
            has_content = any(
                (e.type == ElementType.PARAGRAPH and e.text.strip()) or
                e.type == ElementType.TABLE
                for e in note.elements
            )
            if has_content:
                filtered_notes.append(note)
        else:
            filtered_notes.append(note)

    section.notes = filtered_notes
    return section


def _iter_content_elements(section_elem):
    """
    Iterate through content elements in a SECTION-2,
    yielding P, TABLE, and PGBRK elements in document order.
    Skips TITLE, TABLE-GROUP (cover info), INSERTION, COMMENT, LIBRARY elements.
    """
    skip_tags = {'TITLE', 'INSERTION', 'COMMENT', 'LIBRARY', 'LIBRARYLIST', 'WARNING'}

    def _walk(parent):
        for child in parent:
            if child.tag in skip_tags:
                continue

            if child.tag == 'P':
                yield child
            elif child.tag == 'TABLE':
                yield child
            elif child.tag == 'PGBRK':
                yield child
            elif child.tag == 'TABLE-GROUP':
                # TABLE-GROUPs at the start are usually cover info, skip those
                aclass = get_attr(child, 'ACLASS', '')
                if aclass in ('COVER', 'COVER2'):
                    continue
                # Otherwise, yield tables inside
                for table in child.iter('TABLE'):
                    yield table
            elif child.tag == 'SPAN':
                # SPAN can contain text, treat as inline
                continue
            else:
                # Recurse into other container elements
                yield from _walk(child)

    yield from _walk(section_elem)

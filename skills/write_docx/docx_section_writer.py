"""
Add / delete note sections (a block of consecutive body elements:
title paragraph + body paragraphs + tables).

Clone & Modify: to add a note, find a reference note's elements in the
body, deepcopy all of them, update their texts, and insert the block
at the desired position.
"""

from __future__ import annotations

from copy import deepcopy
from lxml import etree

from utils.xml_helpers import w, find_w, findall_w

from .docx_cell_writer import set_cell_text


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def add_note_section(
    body_element,
    reference_range: tuple[int, int],
    content: list[tuple[str, str]],
    position: str = "after",
) -> None:
    """
    Clone a range of body elements and insert them as a new note section.

    Args:
        body_element:    The ``<w:body>`` lxml element.
        reference_range: (start_body_idx, end_body_idx) inclusive range of
                         body children that form the reference note.
        content:         List of ``(element_type, text)`` tuples.
                         ``element_type`` is ``"paragraph"`` or ``"table"``.
                         For paragraphs, text replaces the paragraph text.
                         For tables, text is currently ignored (table is
                         cloned as-is; use row/cell writers afterwards).
        position:        ``"after"`` or ``"before"`` the reference range.
    """
    children = list(body_element)
    start_idx, end_idx = reference_range

    if not (0 <= start_idx <= end_idx < len(children)):
        raise IndexError(
            f"reference_range ({start_idx}, {end_idx}) out of bounds "
            f"(body has {len(children)} children)"
        )

    # Deepcopy all elements in the range
    cloned: list = []
    for i in range(start_idx, end_idx + 1):
        cloned.append(deepcopy(children[i]))

    # Apply content overrides where possible
    content_iter = iter(content)
    for elem in cloned:
        tag = etree.QName(elem.tag).localname
        try:
            etype, etext = next(content_iter)
        except StopIteration:
            break

        if tag == "p" and etype == "paragraph":
            _set_paragraph_text(elem, etext)
        # For tables, the caller should use docx_table_writer / row_writer
        # after insertion to modify content.

    # Determine insertion point
    if position == "before":
        anchor = children[start_idx]
        for elem in cloned:
            anchor.addprevious(elem)
    else:
        anchor = children[end_idx]
        for elem in cloned:
            anchor.addnext(elem)
            anchor = elem  # next element goes after the one we just added


def delete_note_section(
    body_element,
    element_range: tuple[int, int],
) -> None:
    """
    Remove a contiguous range of body elements that form a note section.

    Args:
        body_element:  The ``<w:body>`` lxml element.
        element_range: (start_body_idx, end_body_idx) inclusive.
    """
    children = list(body_element)
    start_idx, end_idx = element_range

    if not (0 <= start_idx <= end_idx < len(children)):
        raise IndexError(
            f"element_range ({start_idx}, {end_idx}) out of bounds"
        )

    for i in range(start_idx, end_idx + 1):
        body_element.remove(children[i])


# ------------------------------------------------------------------
# Internals
# ------------------------------------------------------------------

def _set_paragraph_text(p_element, new_text: str) -> None:
    """
    Replace the visible text of a ``<w:p>`` element, preserving pPr/rPr.

    Works the same way as cell_writer: put all text in the last run that
    has a ``<w:t>``, blank out the rest.
    """
    runs = findall_w(p_element, "w:r")
    if not runs:
        return

    # Find last run with a <w:t>
    target_run = None
    target_ts = None
    for r in reversed(runs):
        ts = findall_w(r, "w:t")
        if ts:
            target_run = r
            target_ts = ts
            break

    if target_run is not None:
        target_ts[0].text = new_text
        target_ts[0].set(
            "{http://www.w3.org/XML/1998/namespace}space", "preserve"
        )
        for t in target_ts[1:]:
            t.text = ""
        for r in runs:
            if r is target_run:
                continue
            for t in findall_w(r, "w:t"):
                t.text = ""

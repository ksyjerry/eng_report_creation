"""
target_resolver.py — Resolve note-relative targets to body-level indices.

The change_generator produces targets like:
    "note:5:element:3:row:5"   → note 5, 3rd element, row 5
    "note:5"                    → entire note 5 section
    "header"                    → header/footer

The writer needs body-level targets like:
    "table:150:row:5"          → body child 150 (a table), row 5
    "start:120:end:135"        → body children 120-135 (a note section)

This module bridges that gap using the DOCX's parsed structure.
"""

from __future__ import annotations

from lxml import etree
from docx import Document

from ir_schema import ChangeType, ParsedDocument, ElementType
from utils.xml_helpers import w

from .change_model import Change, parse_target


def resolve_targets(
    changes: list[Change],
    docx_doc: ParsedDocument | None = None,
    template_path: str = "",
) -> list[Change]:
    """
    Resolve note-relative targets in changes to body-level indices.

    If docx_doc is not provided and template_path is given, we build
    the note→body mapping by scanning the DOCX XML directly.

    Returns a new list of Change objects with resolved targets.
    Changes that are already body-level (table:N, paragraph:N, header) pass through.
    """
    # Build note mapping
    if template_path:
        note_map = _build_note_map_from_docx(template_path)
    elif docx_doc:
        note_map = _build_note_map_from_ir(docx_doc)
    else:
        # No mapping available — return changes as-is
        return changes

    resolved = []
    skipped = 0

    for change in changes:
        target = parse_target(change.target)

        # Already body-level?
        if "table" in target and isinstance(target.get("table"), int):
            resolved.append(change)
            continue
        if "paragraph" in target and isinstance(target.get("paragraph"), int):
            resolved.append(change)
            continue
        if "header" in target:
            resolved.append(change)
            continue
        if "start" in target and "end" in target:
            resolved.append(change)
            continue

        # Note-relative target
        note_num = target.get("note")
        if note_num is None:
            resolved.append(change)
            continue

        note_key = str(note_num)
        note_info = note_map.get(note_key)
        if note_info is None:
            # Can't resolve — skip with warning
            skipped += 1
            continue

        new_change = _resolve_note_target(change, target, note_info)
        if new_change is not None:
            resolved.append(new_change)
        else:
            skipped += 1

    if skipped > 0:
        import sys
        print(f"  [target_resolver] Skipped {skipped} unresolvable changes",
              file=sys.stderr)

    return resolved


# ──────────────────────────────────────────────────────
# Note mapping structures
# ──────────────────────────────────────────────────────

class NoteBodyInfo:
    """Body-level index info for a note section."""
    def __init__(self):
        self.start_body_idx: int = -1   # first body child of this note
        self.end_body_idx: int = -1     # last body child of this note
        self.table_body_indices: list[int] = []  # body indices of tables in this note
        self.para_body_indices: list[int] = []   # body indices of paragraphs


def _build_note_map_from_docx(template_path: str) -> dict[str, NoteBodyInfo]:
    """
    Build note→body index mapping by scanning the DOCX XML.

    Strategy: find ABCTitle paragraphs, they mark note boundaries.
    Everything between two ABCTitle paragraphs belongs to one note.
    """
    import re
    import zipfile

    with zipfile.ZipFile(template_path, "r") as zf:
        with zf.open("word/document.xml") as f:
            tree = etree.parse(f)

    root = tree.getroot()
    body = root.find(w("body"))
    if body is None:
        return {}

    # First pass: find all body children and their types
    children = list(body)
    child_info = []  # (index, tag, style_id, text)

    for idx, child in enumerate(children):
        tag = etree.QName(child.tag).localname
        style_id = ""
        text = ""

        if tag == "p":
            # Get style
            pPr = child.find(w("pPr"))
            if pPr is not None:
                pStyle = pPr.find(w("pStyle"))
                if pStyle is not None:
                    style_id = pStyle.get(w("val"), "")
            # Get text
            for t_el in child.iter(w("t")):
                if t_el.text:
                    text += t_el.text

        child_info.append((idx, tag, style_id, text.strip()))

    # Second pass: identify note boundaries by ABCTitle style
    note_map: dict[str, NoteBodyInfo] = {}
    current_note_key: str | None = None
    current_info: NoteBodyInfo | None = None
    note_counter = 0

    for idx, tag, style_id, text in child_info:
        is_title = style_id.lower() in ("abctitle",)

        if is_title and text:
            # Skip FS footers
            lower = text.lower()
            if "should be read in conjunction" in lower:
                if current_info is not None:
                    if tag == "p":
                        current_info.para_body_indices.append(idx)
                    current_info.end_body_idx = idx
                continue
            if len(text) > 120:
                if current_info is not None:
                    if tag == "p":
                        current_info.para_body_indices.append(idx)
                    current_info.end_body_idx = idx
                continue

            # Flush previous note
            if current_info is not None and current_note_key is not None:
                note_map[current_note_key] = current_info

            # Extract note number
            note_counter += 1
            m = re.match(r"^(\d+(?:\.\d+)*)\s*\.?\s+", text)
            if m:
                note_key = m.group(1)
            else:
                note_key = str(note_counter)

            current_note_key = note_key
            current_info = NoteBodyInfo()
            current_info.start_body_idx = idx
            current_info.end_body_idx = idx
            current_info.para_body_indices.append(idx)

        elif current_info is not None:
            current_info.end_body_idx = idx
            if tag == "tbl":
                current_info.table_body_indices.append(idx)
            elif tag == "p":
                current_info.para_body_indices.append(idx)

    # Flush last note
    if current_info is not None and current_note_key is not None:
        note_map[current_note_key] = current_info

    return note_map


def _build_note_map_from_ir(docx_doc: ParsedDocument) -> dict[str, NoteBodyInfo]:
    """Build note mapping from parsed IR (less precise but no file access needed)."""
    note_map: dict[str, NoteBodyInfo] = {}

    for section in docx_doc.sections:
        for note in section.notes:
            info = NoteBodyInfo()
            for elem in note.elements:
                if elem.type == ElementType.TABLE and elem.table and elem.table.source_index >= 0:
                    info.table_body_indices.append(elem.table.source_index)
                    if info.start_body_idx < 0:
                        info.start_body_idx = elem.table.source_index
                    info.end_body_idx = elem.table.source_index

            if note.number:
                note_map[note.number] = info

    return note_map


# ──────────────────────────────────────────────────────
# Target resolution
# ──────────────────────────────────────────────────────

def _resolve_note_target(
    change: Change,
    target: dict,
    note_info: NoteBodyInfo,
) -> Change | None:
    """
    Resolve a note-relative target to a body-level target.
    Returns a new Change with resolved target, or None if unresolvable.
    """
    element_idx = target.get("element")
    row_idx = target.get("row")
    col_idx = target.get("col")

    if change.type == ChangeType.DELETE_NOTE:
        if note_info.start_body_idx < 0:
            return None
        new_target = f"start:{note_info.start_body_idx}:end:{note_info.end_body_idx}"
        return Change(
            type=change.type,
            target=new_target,
            value=change.value,
            values=change.values,
            rows=change.rows,
            content=change.content,
            reference_index=change.reference_index,
            position=change.position,
            spacer_indices=change.spacer_indices,
            old_year=change.old_year,
            new_year=change.new_year,
        )

    if change.type == ChangeType.ADD_NOTE:
        # Find a suitable reference point (end of closest preceding note)
        ref_idx = note_info.end_body_idx if note_info.end_body_idx >= 0 else -1
        new_target = f"start:{ref_idx}:end:{ref_idx}"
        return Change(
            type=change.type,
            target=new_target,
            value=change.value,
            values=change.values,
            rows=change.rows,
            content=change.content,
            reference_index=ref_idx,
            position=change.position or "after",
            spacer_indices=change.spacer_indices,
            old_year=change.old_year,
            new_year=change.new_year,
        )

    # For table-related changes within a note
    if element_idx is not None:
        # element_idx is the index of the table within this note's tables
        tables = note_info.table_body_indices
        if isinstance(element_idx, int) and 0 <= element_idx < len(tables):
            body_tbl_idx = tables[element_idx]
        elif tables:
            # Fallback: use first table if element_idx is out of range
            body_tbl_idx = tables[min(element_idx, len(tables) - 1)] if isinstance(element_idx, int) else tables[0]
        else:
            return None  # No tables in this note

        # Build body-level target
        parts = [f"table:{body_tbl_idx}"]
        if row_idx is not None:
            parts.append(f"row:{row_idx}")
        if col_idx is not None:
            parts.append(f"col:{col_idx}")
        new_target = ":".join(parts)

        return Change(
            type=change.type,
            target=new_target,
            value=change.value,
            values=change.values,
            rows=change.rows,
            content=change.content,
            reference_index=change.reference_index,
            position=change.position,
            spacer_indices=change.spacer_indices,
            old_year=change.old_year,
            new_year=change.new_year,
        )

    # Note-level without element — might be a section operation
    if change.type in (ChangeType.ADD_TABLE, ChangeType.DELETE_TABLE):
        if note_info.table_body_indices:
            body_idx = note_info.table_body_indices[-1]  # after last table
            return Change(
                type=change.type,
                target=f"table:{body_idx}",
                value=change.value,
                values=change.values,
                rows=change.rows,
                content=change.content,
                reference_index=body_idx,
                position=change.position or "after",
                spacer_indices=change.spacer_indices,
                old_year=change.old_year,
                new_year=change.new_year,
            )

    return None

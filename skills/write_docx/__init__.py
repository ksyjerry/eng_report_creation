"""
write_docx skill — Apply a list of Changes to a DOCX template and produce
a new DOCX file.

Entry point: write_docx(template_path, changes, output_path) → str
"""

from __future__ import annotations

import zipfile
from lxml import etree

from ir_schema import ChangeType
from utils.xml_helpers import w, findall_w

from .change_model import Change, parse_target
from .docx_cell_writer import set_cell_text
from .docx_row_writer import add_row, add_rows, delete_row
from .docx_table_writer import add_table, delete_table
from .docx_section_writer import add_note_section, delete_note_section
from .docx_header_writer import replace_years_in_header_xml
from .docx_assembler import assemble_docx
from .target_resolver import resolve_targets


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------

def write_docx(
    template_path: str,
    changes: list[Change],
    output_path: str,
) -> str:
    """
    Apply *changes* to the DOCX at *template_path* and write the result
    to *output_path*.

    Returns:
        The output path for convenience.
    """
    # ── 0. Resolve note-relative targets to body-level indices ────
    changes = resolve_targets(changes, template_path=template_path)

    # ── 1. Unpack the XMLs we need to modify ──────────────────────
    doc_xml, header_xmls = _load_xmls(template_path)
    body = doc_xml.find(w("body"))

    # Collect which header parts were modified so we only rewrite those.
    modified_parts: dict[str, etree._Element] = {}

    # ── 2. Apply changes in a sensible order ──────────────────────
    # Deletions first (high index → low index to preserve indices),
    # then modifications, then additions.
    deletions = [c for c in changes if c.type in (
        ChangeType.DELETE_ROW, ChangeType.DELETE_TABLE, ChangeType.DELETE_NOTE,
    )]
    modifications = [c for c in changes if c.type in (
        ChangeType.UPDATE_VALUES, ChangeType.UPDATE_TEXT,
    )]
    additions = [c for c in changes if c.type in (
        ChangeType.ADD_ROW, ChangeType.ADD_TABLE, ChangeType.ADD_NOTE,
    )]
    header_changes = [c for c in changes if c.type == ChangeType.RESTRUCTURE
                      or parse_target(c.target).get("header")]

    # Sort deletions by index descending so removing earlier elements
    # doesn't shift indices of later ones.
    deletions.sort(key=lambda c: _sort_key_descending(c.target), reverse=False)

    # -- Deletions --
    errors = []
    deleted_body_indices: list[tuple[int, int]] = []  # (start, count) of removed body elements
    for change in deletions:
        try:
            # Track what gets deleted for index adjustment
            target = parse_target(change.target)
            if change.type == ChangeType.DELETE_NOTE:
                start = target.get("paragraph", target.get("start"))
                end = target.get("end")
                if start is not None and end is not None:
                    deleted_body_indices.append((start, end - start + 1))
            elif change.type == ChangeType.DELETE_TABLE:
                tbl_idx = target.get("table")
                if tbl_idx is not None:
                    deleted_body_indices.append((tbl_idx, 1))
            _apply_deletion(body, change)
        except (IndexError, ValueError, KeyError) as e:
            errors.append(f"DELETE {change.target}: {e}")

    # Build adjustment function: for a given original body index,
    # compute how many elements were deleted below it.
    # Sort deleted ranges by start index ascending.
    deleted_body_indices.sort(key=lambda x: x[0])

    def _adjust_index(orig_idx: int) -> int:
        """Adjust a body index to account for deleted elements."""
        shift = 0
        for del_start, del_count in deleted_body_indices:
            if del_start < orig_idx:
                shift += min(del_count, orig_idx - del_start)
        return orig_idx - shift

    def _adjust_change_target(change: Change) -> Change:
        """Return a copy of the change with body indices adjusted for deletions."""
        if not deleted_body_indices:
            return change
        target = parse_target(change.target)
        tbl_idx = target.get("table")
        para_idx = target.get("paragraph")
        start_idx = target.get("start")
        end_idx = target.get("end")
        changed = False

        if tbl_idx is not None:
            new_tbl = _adjust_index(tbl_idx)
            if new_tbl != tbl_idx:
                tbl_idx = new_tbl
                changed = True
        if para_idx is not None:
            new_para = _adjust_index(para_idx)
            if new_para != para_idx:
                para_idx = new_para
                changed = True
        if start_idx is not None:
            new_start = _adjust_index(start_idx)
            if new_start != start_idx:
                start_idx = new_start
                changed = True
        if end_idx is not None:
            new_end = _adjust_index(end_idx)
            if new_end != end_idx:
                end_idx = new_end
                changed = True

        if not changed:
            return change

        # Rebuild target string
        parts = []
        if tbl_idx is not None:
            parts.append(f"table:{tbl_idx}")
        if para_idx is not None:
            parts.append(f"paragraph:{para_idx}")
        if start_idx is not None:
            parts.append(f"start:{start_idx}")
        if end_idx is not None:
            parts.append(f"end:{end_idx}")
        row_idx = target.get("row")
        if row_idx is not None:
            parts.append(f"row:{row_idx}")
        col_idx = target.get("col")
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
            reference_index=(_adjust_index(change.reference_index)
                             if change.reference_index is not None and change.reference_index >= 0
                             else change.reference_index),
            position=change.position,
            spacer_indices=change.spacer_indices,
            old_year=change.old_year,
            new_year=change.new_year,
        )

    # -- Modifications (with adjusted indices) --
    for change in modifications:
        try:
            adjusted = _adjust_change_target(change)
            _apply_modification(body, adjusted)
        except (IndexError, ValueError, KeyError) as e:
            errors.append(f"UPDATE {change.target}: {e}")

    # -- Additions (with adjusted indices) --
    for change in additions:
        try:
            adjusted = _adjust_change_target(change)
            _apply_addition(body, adjusted)
        except (IndexError, ValueError, KeyError) as e:
            errors.append(f"ADD {change.target}: {e}")

    if errors:
        import sys
        print(f"  [write_docx] {len(errors)} changes failed to apply:", file=sys.stderr)
        for err in errors[:10]:
            print(f"    - {err}", file=sys.stderr)
        if len(errors) > 10:
            print(f"    ... and {len(errors) - 10} more", file=sys.stderr)

    # -- Header/footer year changes --
    all_year_replacements: list[tuple[str, str]] = []
    for change in header_changes:
        target = parse_target(change.target)
        if target.get("header"):
            replacements = []
            if change.old_year and change.new_year:
                replacements.append((change.old_year, change.new_year))
            # Also support values dict for multiple replacements
            for old_y, new_y in change.values.items():
                replacements.append((str(old_y), str(new_y)))
            all_year_replacements.extend(replacements)
            if replacements:
                for hdr_name, hdr_root in header_xmls.items():
                    if replace_years_in_header_xml(hdr_root, replacements):
                        modified_parts[hdr_name] = hdr_root

    # -- Apply year rolling to document body (table headers + paragraph text) --
    if all_year_replacements:
        _apply_year_roll_to_tables(body, all_year_replacements)
        _apply_year_roll_to_paragraphs(body, all_year_replacements)

    # Also apply header changes specified via the direct year fields
    # on non-header-targeted changes (convenience).
    standalone_header_replacements: list[tuple[str, str]] = []
    for change in changes:
        if change.old_year and change.new_year and not parse_target(change.target).get("header"):
            standalone_header_replacements.append(
                (change.old_year, change.new_year)
            )
    # (These are typically handled by explicit header-targeted changes,
    #  so this is a no-op in most cases.)

    # ── 3. The document.xml is always considered modified ─────────
    modified_parts["word/document.xml"] = doc_xml

    # ── 4. Assemble the output DOCX ──────────────────────────────
    return assemble_docx(template_path, output_path, modified_parts)


# ------------------------------------------------------------------
# XML loading
# ------------------------------------------------------------------

def _load_xmls(
    docx_path: str,
) -> tuple[etree._Element, dict[str, etree._Element]]:
    """
    Open a DOCX and parse the XML parts we may need to modify.

    Returns:
        (document_xml_root, {zip_path: header_xml_root, ...})
    """
    doc_xml = None
    header_xmls: dict[str, etree._Element] = {}

    with zipfile.ZipFile(docx_path, "r") as zf:
        # document.xml
        with zf.open("word/document.xml") as f:
            doc_xml = etree.parse(f).getroot()

        # header*.xml and footer*.xml
        for name in zf.namelist():
            basename = name.split("/")[-1] if "/" in name else name
            if basename.startswith("header") or basename.startswith("footer"):
                if basename.endswith(".xml"):
                    with zf.open(name) as f:
                        header_xmls[name] = etree.parse(f).getroot()

    return doc_xml, header_xmls


# ------------------------------------------------------------------
# Change dispatchers
# ------------------------------------------------------------------

def _apply_deletion(body, change: Change) -> None:
    """Dispatch a deletion change."""
    target = parse_target(change.target)

    if change.type == ChangeType.DELETE_ROW:
        tbl_idx = target.get("table")
        row_idx = target.get("row")
        if tbl_idx is None or row_idx is None:
            raise ValueError(f"DELETE_ROW needs table and row in target: {change.target}")
        tbl_elem = _get_table_element(body, tbl_idx)
        delete_row(tbl_elem, row_idx)

    elif change.type == ChangeType.DELETE_TABLE:
        tbl_idx = target.get("table")
        if tbl_idx is None:
            raise ValueError(f"DELETE_TABLE needs table in target: {change.target}")
        children = list(body)
        delete_table(body, tbl_idx)

    elif change.type == ChangeType.DELETE_NOTE:
        start = target.get("paragraph", target.get("start"))
        end = target.get("end")
        if start is None or end is None:
            raise ValueError(
                f"DELETE_NOTE needs start and end body indices in target: "
                f"{change.target}"
            )
        delete_note_section(body, (start, end))


def _apply_modification(body, change: Change) -> None:
    """Dispatch an update change."""
    target = parse_target(change.target)

    if change.type == ChangeType.UPDATE_VALUES:
        tbl_idx = target.get("table")
        row_idx = target.get("row")
        if tbl_idx is None:
            raise ValueError(f"UPDATE_VALUES needs table in target: {change.target}")
        tbl_elem = _get_table_element(body, tbl_idx)

        if row_idx is not None:
            col_idx = target.get("col")
            if col_idx is not None:
                # Single cell update
                tc = _get_cell_element(tbl_elem, row_idx, col_idx)
                set_cell_text(tc, change.value)
            else:
                # Multi-cell update via values dict
                tr_list = findall_w(tbl_elem, "w:tr")
                if 0 <= row_idx < len(tr_list):
                    tr = tr_list[row_idx]
                    cells = findall_w(tr, "w:tc")
                    for col, text in change.values.items():
                        if 0 <= col < len(cells):
                            set_cell_text(cells[col], text)
        else:
            # values dict maps (row, col) tuples → text ... or row → {col → text}
            # We support values as {col_idx: text} when row is specified,
            # but also support a flat approach via multiple changes.
            pass

    elif change.type == ChangeType.UPDATE_TEXT:
        para_idx = target.get("paragraph")
        if para_idx is not None:
            children = list(body)
            if 0 <= para_idx < len(children):
                from .docx_section_writer import _set_paragraph_text
                _set_paragraph_text(children[para_idx], change.value)
        else:
            # Could be a cell text update
            tbl_idx = target.get("table")
            row_idx = target.get("row")
            col_idx = target.get("col")
            if tbl_idx is not None and row_idx is not None and col_idx is not None:
                tbl_elem = _get_table_element(body, tbl_idx)
                tc = _get_cell_element(tbl_elem, row_idx, col_idx)
                set_cell_text(tc, change.value)


def _apply_addition(body, change: Change) -> None:
    """Dispatch an addition change."""
    target = parse_target(change.target)

    if change.type == ChangeType.ADD_ROW:
        tbl_idx = target.get("table")
        ref_row = change.reference_index
        if tbl_idx is None:
            raise ValueError(f"ADD_ROW needs table in target: {change.target}")
        tbl_elem = _get_table_element(body, tbl_idx)
        if change.rows:
            add_rows(
                tbl_elem, ref_row, change.rows,
                position=change.position,
                spacer_indices=change.spacer_indices,
            )
        elif change.values:
            add_row(
                tbl_elem, ref_row, change.values,
                position=change.position,
                spacer_indices=change.spacer_indices,
            )

    elif change.type == ChangeType.ADD_TABLE:
        ref_idx = change.reference_index
        add_table(
            body, ref_idx,
            rows_data=change.rows or None,
            position=change.position,
            spacer_indices=change.spacer_indices,
        )

    elif change.type == ChangeType.ADD_NOTE:
        start = target.get("start", change.reference_index)
        end = target.get("end", change.reference_index)
        add_note_section(
            body,
            reference_range=(start, end),
            content=change.content,
            position=change.position,
        )


# ------------------------------------------------------------------
# Element lookup helpers
# ------------------------------------------------------------------

def _get_table_element(body, body_idx: int):
    """Return the <w:tbl> element at *body_idx* in the body.
    If body_idx points to a non-table, search nearby for the closest table."""
    children = list(body)
    if not (0 <= body_idx < len(children)):
        raise IndexError(f"body_idx {body_idx} out of range ({len(children)} children)")
    elem = children[body_idx]
    tag = etree.QName(elem.tag).localname
    if tag == "tbl":
        return elem
    # Search nearby (within ±3 elements) for a table
    for offset in [1, -1, 2, -2, 3, -3]:
        adj = body_idx + offset
        if 0 <= adj < len(children):
            adj_tag = etree.QName(children[adj].tag).localname
            if adj_tag == "tbl":
                return children[adj]
    raise ValueError(f"No table found near body index {body_idx} (found <{tag}>)")


def _get_cell_element(tbl_element, row_idx: int, col_idx: int):
    """Return the <w:tc> element at (row_idx, col_idx) in a table."""
    rows = findall_w(tbl_element, "w:tr")
    if not (0 <= row_idx < len(rows)):
        raise IndexError(f"row_idx {row_idx} out of range ({len(rows)} rows)")
    cells = findall_w(rows[row_idx], "w:tc")
    if not (0 <= col_idx < len(cells)):
        raise IndexError(f"col_idx {col_idx} out of range ({len(cells)} cells)")
    return cells[col_idx]


def _apply_year_roll_to_paragraphs(body, replacements: list[tuple[str, str]]) -> None:
    """
    Apply year replacements to all paragraphs in the document body.
    This handles dates like "December 31, 2024" → "December 31, 2025".
    """
    sorted_replacements = sorted(replacements, key=lambda p: p[0], reverse=True)

    for p in body.iter(w("p")):
        # Skip paragraphs inside tables (already handled)
        parent = p.getparent()
        if parent is not None:
            parent_tag = etree.QName(parent.tag).localname if parent.tag else ""
            if parent_tag == "tc":
                continue

        for t_elem in p.iter(w("t")):
            if t_elem.text is None:
                continue
            original = t_elem.text
            for old, new in sorted_replacements:
                if old in t_elem.text:
                    t_elem.text = t_elem.text.replace(old, new)
            if t_elem.text != original:
                t_elem.set(
                    "{http://www.w3.org/XML/1998/namespace}space", "preserve"
                )


def _apply_year_roll_to_tables(body, replacements: list[tuple[str, str]]) -> None:
    """
    Apply year replacements to all table header cells in the document body.
    Only replaces year strings that appear in the first 2 rows of each table
    (header rows) to avoid accidentally changing data values.

    Handles years split across multiple <w:t> elements (e.g., "202"+"4").
    """
    sorted_replacements = sorted(replacements, key=lambda p: p[0], reverse=True)

    for tbl in findall_w(body, "w:tbl"):
        rows = findall_w(tbl, "w:tr")
        # Only process the first 2 rows (likely headers)
        for tr in rows[:2]:
            # Use replace_years_in_header_xml which handles both simple
            # and cross-run replacement
            replace_years_in_header_xml(tr, sorted_replacements)


def _sort_key_descending(target: str) -> tuple:
    """
    Build a sort key from a target string so that higher indices sort first.
    We negate the numbers so a normal ascending sort gives descending order.
    """
    parsed = parse_target(target)
    return tuple(
        -v if isinstance(v, int) else 0
        for v in parsed.values()
    )

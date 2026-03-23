"""
Add / delete entire tables in the document body.

Clone & Modify: to add a table, deepcopy a reference ``<w:tbl>`` element,
clear or modify its rows, and insert it at the desired position in the
``<w:body>``.
"""

from __future__ import annotations

from copy import deepcopy
from lxml import etree

from utils.xml_helpers import w, findall_w

from .docx_row_writer import _set_row_cell_texts, _clear_vmerge


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def add_table(
    body_element,
    reference_body_idx: int,
    rows_data: list[dict[int, str]] | None = None,
    position: str = "after",
    spacer_indices: list[int] | None = None,
) -> None:
    """
    Insert a new table by cloning the body child at *reference_body_idx*.

    Args:
        body_element:       The ``<w:body>`` lxml element.
        reference_body_idx: 0-based index among ``<w:body>`` children.
        rows_data:          Optional list of row dicts (phys col → text).
                            If supplied, the cloned table's data rows are
                            replaced with these.
        position:           ``"after"`` or ``"before"`` the reference.
        spacer_indices:     Physical spacer column indices.
    """
    spacer_indices = spacer_indices or []
    children = list(body_element)
    if not (0 <= reference_body_idx < len(children)):
        raise IndexError(
            f"reference_body_idx {reference_body_idx} out of range"
        )

    ref_elem = children[reference_body_idx]
    tag = etree.QName(ref_elem.tag).localname
    if tag != "tbl":
        raise ValueError(
            f"Element at body index {reference_body_idx} is <{tag}>, "
            f"not <tbl>"
        )

    new_tbl = deepcopy(ref_elem)

    # Optionally replace row content
    if rows_data is not None:
        _replace_table_rows(new_tbl, rows_data, spacer_indices)

    if position == "before":
        ref_elem.addprevious(new_tbl)
    else:
        ref_elem.addnext(new_tbl)


def delete_table(body_element, body_idx: int) -> None:
    """Remove the table at *body_idx* from the document body."""
    children = list(body_element)
    if not (0 <= body_idx < len(children)):
        raise IndexError(f"body_idx {body_idx} out of range")

    target = children[body_idx]
    tag = etree.QName(target.tag).localname
    if tag != "tbl":
        raise ValueError(
            f"Element at body index {body_idx} is <{tag}>, not <tbl>"
        )

    body_element.remove(target)


# ------------------------------------------------------------------
# Internals
# ------------------------------------------------------------------

def _replace_table_rows(
    tbl_element,
    rows_data: list[dict[int, str]],
    spacer_indices: list[int],
) -> None:
    """
    Replace data rows (non-header) in a cloned table with *rows_data*.

    Heuristic: keep the first row (header) and the last row (total) as
    templates; remove everything in between and fill from *rows_data*.
    If *rows_data* is empty, just clear all data row texts.
    """
    all_rows = findall_w(tbl_element, "w:tr")
    if len(all_rows) < 2:
        return  # nothing useful to do

    # Use the second row as the template for data rows
    template_row = all_rows[1] if len(all_rows) > 1 else all_rows[0]

    # Remove existing data rows (keep first = header)
    for row in all_rows[1:]:
        tbl_element.remove(row)

    # Insert new rows based on template
    insert_after = all_rows[0]  # header row
    for row_values in rows_data:
        new_row = deepcopy(template_row)
        _clear_vmerge(new_row)
        _set_row_cell_texts(new_row, row_values, spacer_indices)
        insert_after.addnext(new_row)
        insert_after = new_row

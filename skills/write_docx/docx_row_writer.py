"""
Add / delete rows in DOCX tables.

Clone & Modify: to add a row we deepcopy an adjacent ``<w:tr>`` element,
update the cell texts, and insert it at the correct position inside the
``<w:tbl>``.
"""

from __future__ import annotations

from copy import deepcopy
from lxml import etree

from utils.xml_helpers import w, find_w, findall_w

from .docx_cell_writer import set_cell_text


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def add_row(
    tbl_element,
    reference_row_idx: int,
    values: dict[int, str],
    position: str = "after",
    spacer_indices: list[int] | None = None,
) -> None:
    """
    Insert a new row by cloning the row at *reference_row_idx*.

    Args:
        tbl_element:       The ``<w:tbl>`` lxml element.
        reference_row_idx: 0-based index among ``<w:tr>`` children.
        values:            Mapping of **physical** column index → text.
        position:          ``"after"`` or ``"before"`` the reference row.
        spacer_indices:    Physical column indices that are spacers —
                           these cells are left untouched.
    """
    spacer_indices = spacer_indices or []
    rows = findall_w(tbl_element, "w:tr")
    if not (0 <= reference_row_idx < len(rows)):
        raise IndexError(
            f"reference_row_idx {reference_row_idx} out of range "
            f"(table has {len(rows)} rows)"
        )

    ref_row = rows[reference_row_idx]
    new_row = deepcopy(ref_row)

    # Clear vMerge on the cloned row (new row should not inherit merges)
    _clear_vmerge(new_row)

    # Set cell texts, skipping spacers
    _set_row_cell_texts(new_row, values, spacer_indices)

    # Insert into the table at the right position
    if position == "before":
        ref_row.addprevious(new_row)
    else:
        ref_row.addnext(new_row)


def add_rows(
    tbl_element,
    reference_row_idx: int,
    rows_data: list[dict[int, str]],
    position: str = "after",
    spacer_indices: list[int] | None = None,
) -> None:
    """Convenience: insert multiple rows at once (in order)."""
    # When inserting "after", each successive row must be inserted after the
    # previously inserted one so they appear in the given order.
    insert_after_idx = reference_row_idx
    for row_values in rows_data:
        add_row(
            tbl_element,
            insert_after_idx,
            row_values,
            position=position,
            spacer_indices=spacer_indices,
        )
        if position == "after":
            # The newly inserted row is now directly after insert_after_idx,
            # so bump the index by 1 for the next insertion.
            insert_after_idx += 1


def delete_row(tbl_element, row_idx: int) -> None:
    """
    Remove the row at *row_idx* from the table.

    Handles vMerge: if the deleted row starts a vertical merge (restart),
    transfer ``restart`` to the next continuation row so the merge is not
    broken.
    """
    rows = findall_w(tbl_element, "w:tr")
    if not (0 <= row_idx < len(rows)):
        raise IndexError(
            f"row_idx {row_idx} out of range (table has {len(rows)} rows)"
        )

    target_row = rows[row_idx]

    # Check each cell for vMerge restart and transfer if needed
    if row_idx + 1 < len(rows):
        next_row = rows[row_idx + 1]
        _transfer_vmerge_restart(target_row, next_row)

    target_row.getparent().remove(target_row)


# ------------------------------------------------------------------
# Internals
# ------------------------------------------------------------------

def _set_row_cell_texts(
    tr_element,
    values: dict[int, str],
    spacer_indices: list[int],
) -> None:
    """Set text for cells in a row, skipping spacers."""
    cells = findall_w(tr_element, "w:tc")

    phys_col = 0
    for tc in cells:
        # Determine how many physical columns this cell spans
        span = 1
        tc_pr = find_w(tc, "w:tcPr")
        if tc_pr is not None:
            gs = find_w(tc_pr, "w:gridSpan")
            if gs is not None:
                try:
                    span = int(gs.get(w("val"), "1"))
                except ValueError:
                    span = 1

        if phys_col not in spacer_indices and phys_col in values:
            set_cell_text(tc, values[phys_col])

        phys_col += span


def _clear_vmerge(tr_element) -> None:
    """Remove all vMerge elements from cells in a row."""
    for tc in findall_w(tr_element, "w:tc"):
        tc_pr = find_w(tc, "w:tcPr")
        if tc_pr is not None:
            vm = find_w(tc_pr, "w:vMerge")
            if vm is not None:
                tc_pr.remove(vm)


def _transfer_vmerge_restart(from_row, to_row) -> None:
    """
    If *from_row* has cells with ``vMerge restart``, and the corresponding
    cell in *to_row* has ``vMerge`` (continuation), promote that cell to
    ``restart``.
    """
    from_cells = findall_w(from_row, "w:tc")
    to_cells = findall_w(to_row, "w:tc")

    for fc, tc in zip(from_cells, to_cells):
        fc_pr = find_w(fc, "w:tcPr")
        if fc_pr is None:
            continue
        fc_vm = find_w(fc_pr, "w:vMerge")
        if fc_vm is None:
            continue
        if fc_vm.get(w("val"), "") != "restart":
            continue

        # from_cell starts a merge → check if to_cell continues it
        tc_pr = find_w(tc, "w:tcPr")
        if tc_pr is None:
            continue
        tc_vm = find_w(tc_pr, "w:vMerge")
        if tc_vm is not None:
            # Promote continuation to restart
            tc_vm.set(w("val"), "restart")

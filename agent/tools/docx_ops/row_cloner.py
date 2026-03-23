"""
행 복제/삭제 — Clone & Modify 패턴.

원본: skills/write_docx/docx_row_writer.py
핵심: 행 추가 시 기존 행을 deepcopy하여 서식을 100% 보존.
"""

from __future__ import annotations

from copy import deepcopy
from lxml import etree

from .xml_helpers import w, find_w, findall_w
from .cell_writer import set_cell_text


def clone_row(
    tbl_element: etree._Element,
    source_row_idx: int,
    insert_after_idx: int,
    cell_texts: dict[int, str] | None = None,
    spacer_indices: list[int] | None = None,
) -> etree._Element:
    """
    테이블에서 source_row를 deepcopy하여 insert_after 뒤에 삽입.

    Args:
        tbl_element: lxml의 <w:tbl> 요소
        source_row_idx: 복제할 원본 행 인덱스
        insert_after_idx: 삽입할 위치 (이 행 다음)
        cell_texts: {physical_col: text} 새 텍스트 (None이면 원본 그대로)
        spacer_indices: spacer column 인덱스 목록 (이 열은 건너뜀)

    Returns:
        삽입된 새 <w:tr> 요소
    """
    spacer_indices = spacer_indices or []
    rows = findall_w(tbl_element, "w:tr")

    if not (0 <= source_row_idx < len(rows)):
        raise IndexError(
            f"source_row_idx {source_row_idx} out of range "
            f"(table has {len(rows)} rows)"
        )
    if not (0 <= insert_after_idx < len(rows)):
        raise IndexError(
            f"insert_after_idx {insert_after_idx} out of range "
            f"(table has {len(rows)} rows)"
        )

    ref_row = rows[source_row_idx]
    new_row = deepcopy(ref_row)

    # 복제된 행에서 vMerge 제거 (의도치 않은 병합 방지)
    _clear_vmerge(new_row)

    # 셀 텍스트 설정
    if cell_texts:
        _set_row_cell_texts(new_row, cell_texts, spacer_indices)

    # insert_after_idx 행 다음에 삽입
    rows[insert_after_idx].addnext(new_row)

    return new_row


def add_rows(
    tbl_element: etree._Element,
    reference_row_idx: int,
    rows_data: list[dict[int, str]],
    spacer_indices: list[int] | None = None,
) -> list[etree._Element]:
    """여러 행을 순서대로 삽입."""
    inserted = []
    insert_after = reference_row_idx
    for row_values in rows_data:
        new_row = clone_row(
            tbl_element,
            source_row_idx=reference_row_idx,
            insert_after_idx=insert_after,
            cell_texts=row_values,
            spacer_indices=spacer_indices,
        )
        inserted.append(new_row)
        insert_after += 1
    return inserted


def delete_row(tbl_element: etree._Element, row_idx: int) -> None:
    """
    테이블에서 특정 행 삭제.
    vMerge restart가 있으면 다음 행으로 이전.
    """
    rows = findall_w(tbl_element, "w:tr")
    if not (0 <= row_idx < len(rows)):
        raise IndexError(
            f"row_idx {row_idx} out of range (table has {len(rows)} rows)"
        )

    target_row = rows[row_idx]

    # vMerge restart → 다음 행으로 이전
    if row_idx + 1 < len(rows):
        _transfer_vmerge_restart(target_row, rows[row_idx + 1])

    target_row.getparent().remove(target_row)


# ------------------------------------------------------------------
# Internals
# ------------------------------------------------------------------

def _set_row_cell_texts(
    tr_element: etree._Element,
    values: dict[int, str],
    spacer_indices: list[int],
) -> None:
    """행의 셀 텍스트 설정. spacer column은 건너뜀."""
    cells = findall_w(tr_element, "w:tc")

    phys_col = 0
    for tc in cells:
        # gridSpan으로 병합된 셀의 span 계산
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


def _clear_vmerge(tr_element: etree._Element) -> None:
    """행의 모든 셀에서 vMerge 요소 제거."""
    for tc in findall_w(tr_element, "w:tc"):
        tc_pr = find_w(tc, "w:tcPr")
        if tc_pr is not None:
            vm = find_w(tc_pr, "w:vMerge")
            if vm is not None:
                tc_pr.remove(vm)


def _transfer_vmerge_restart(from_row: etree._Element, to_row: etree._Element) -> None:
    """삭제될 행의 vMerge restart를 다음 행으로 이전."""
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

        tc_pr = find_w(tc, "w:tcPr")
        if tc_pr is None:
            continue
        tc_vm = find_w(tc_pr, "w:vMerge")
        if tc_vm is not None:
            tc_vm.set(w("val"), "restart")

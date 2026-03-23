"""
Column 매핑 — Logical↔Physical column 변환 + Spacer 감지.

원본: skills/parse_docx/docx_table_parser.py의 _build_column_mapping
핵심: DOCX 테이블의 좁은 spacer column을 감지하여 논리적 인덱스와 물리적 인덱스를 매핑.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from lxml import etree

from .xml_helpers import w, find_w, findall_w

DEFAULT_SPACER_THRESHOLD = 200  # dxa 단위


@dataclass
class ColumnMapping:
    """Logical↔Physical column 매핑."""
    logical_to_physical: dict[int, list[int]] = field(default_factory=dict)
    physical_to_logical: dict[int, int] = field(default_factory=dict)
    spacer_indices: list[int] = field(default_factory=list)
    physical_widths: list[int] = field(default_factory=list)

    @property
    def num_logical_cols(self) -> int:
        return len(self.logical_to_physical)

    @property
    def num_physical_cols(self) -> int:
        return len(self.physical_widths)


def build_column_mapping(
    tbl_element: etree._Element,
    spacer_threshold: int = DEFAULT_SPACER_THRESHOLD,
) -> ColumnMapping:
    """
    테이블의 <w:tblGrid>에서 column 매핑 구축.
    Spacer column (0 < 너비 < threshold) 감지 및 제거.

    Args:
        tbl_element: lxml의 <w:tbl> 요소
        spacer_threshold: spacer 판별 너비 기준 (dxa)

    Returns:
        ColumnMapping 객체
    """
    grid_cols = findall_w(tbl_element, "w:tblGrid/w:gridCol")

    # 물리적 열 너비 수집
    physical_widths: list[int] = []
    for gc in grid_cols:
        w_val = gc.get(w("w"))
        if w_val is not None:
            try:
                physical_widths.append(int(w_val))
            except ValueError:
                physical_widths.append(0)
        else:
            physical_widths.append(0)

    # Spacer 감지 및 매핑 구축
    spacer_indices: list[int] = []
    logical_to_physical: dict[int, list[int]] = {}
    physical_to_logical: dict[int, int] = {}
    logical_idx = 0

    for phys_idx, width in enumerate(physical_widths):
        if 0 < width < spacer_threshold:
            spacer_indices.append(phys_idx)
        else:
            logical_to_physical[logical_idx] = [phys_idx]
            physical_to_logical[phys_idx] = logical_idx
            logical_idx += 1

    # tblGrid가 없는 경우 → 첫 행의 셀 수로 fallback
    if not physical_widths:
        rows = findall_w(tbl_element, "w:tr")
        if rows:
            first_row_cells = findall_w(rows[0], "w:tc")
            for i in range(len(first_row_cells)):
                logical_to_physical[i] = [i]
                physical_to_logical[i] = i

    return ColumnMapping(
        logical_to_physical=logical_to_physical,
        physical_to_logical=physical_to_logical,
        spacer_indices=spacer_indices,
        physical_widths=physical_widths,
    )


def logical_to_physical_col(mapping: ColumnMapping, logical_col: int) -> int | None:
    """논리적 열 인덱스 → 물리적 열 인덱스 변환."""
    phys_list = mapping.logical_to_physical.get(logical_col)
    if phys_list:
        return phys_list[0]
    return None


def physical_to_logical_col(mapping: ColumnMapping, physical_col: int) -> int | None:
    """물리적 열 인덱스 → 논리적 열 인덱스 변환."""
    return mapping.physical_to_logical.get(physical_col)

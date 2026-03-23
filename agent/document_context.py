"""
DocumentContext — Agent 세션 동안 공유되는 문서 상태.

모든 Tool이 같은 DOCX/DSD 문서를 참조하도록 하는 중앙 객체.
python-docx로 로드하되, lxml element에 직접 접근하여 서식 보존 조작.
"""

from __future__ import annotations

import os
from pathlib import Path
from lxml import etree
from docx import Document

from agent.tools.docx_ops.xml_helpers import w, findall_w, find_w, OOXML_NS


class DocumentContext:
    """Agent 세션 동안 공유되는 문서 상태."""

    def __init__(self):
        self.dsd_data: dict | None = None
        self.docx_doc: Document | None = None
        self.docx_path: str | None = None
        self._headers: list[etree._Element] = []
        self._footers: list[etree._Element] = []

    # ------------------------------------------------------------------
    # DOCX 로드/저장
    # ------------------------------------------------------------------

    def load_docx(self, path: str) -> None:
        """DOCX 파일을 메모리에 로드."""
        self.docx_path = path
        self.docx_doc = Document(path)
        self._load_headers_footers()

    def save_docx(self, output_path: str) -> str:
        """현재 문서 상태를 파일로 저장."""
        if self.docx_doc is None:
            raise RuntimeError("No DOCX loaded")
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        self.docx_doc.save(output_path)
        return output_path

    # ------------------------------------------------------------------
    # Body 접근
    # ------------------------------------------------------------------

    @property
    def body(self) -> etree._Element:
        """DOCX body element."""
        if self.docx_doc is None:
            raise RuntimeError("No DOCX loaded")
        return self.docx_doc.element.body

    def get_tables(self) -> list[etree._Element]:
        """모든 <w:tbl> 요소 반환."""
        return findall_w(self.body, ".//w:tbl")

    def get_table(self, index: int) -> etree._Element:
        """인덱스로 테이블 접근."""
        tables = self.get_tables()
        if not (0 <= index < len(tables)):
            raise IndexError(f"Table index {index} out of range (0-{len(tables)-1})")
        return tables[index]

    def get_paragraphs(self) -> list[etree._Element]:
        """본문의 모든 <w:p> 요소 반환 (테이블 내부 제외)."""
        all_paras = findall_w(self.body, "w:p")
        return all_paras

    def get_paragraph(self, index: int) -> etree._Element:
        """인덱스로 문단 접근."""
        paras = self.get_paragraphs()
        if not (0 <= index < len(paras)):
            raise IndexError(f"Paragraph index {index} out of range (0-{len(paras)-1})")
        return paras[index]

    def get_table_rows(self, table_index: int) -> list[etree._Element]:
        """테이블의 모든 <w:tr> 요소 반환."""
        tbl = self.get_table(table_index)
        return findall_w(tbl, "w:tr")

    def get_cell(self, table_index: int, row: int, col: int) -> etree._Element:
        """특정 셀의 <w:tc> 요소 반환.

        gridSpan 범위 매칭: phys_col <= col < phys_col + span
        정확 매칭 실패 시 가장 가까운 셀 반환.
        """
        rows = self.get_table_rows(table_index)
        if not (0 <= row < len(rows)):
            raise IndexError(f"Row {row} out of range (0-{len(rows)-1})")

        cells = findall_w(rows[row], "w:tc")
        # col은 physical column — gridSpan 범위 매칭
        phys_col = 0
        best_tc = None
        best_dist = float("inf")
        for tc in cells:
            span = _get_grid_span(tc)
            # 범위 매칭: col이 이 셀의 span 범위 안에 있으면 반환
            if phys_col <= col < phys_col + span:
                return tc
            # fallback: 가장 가까운 셀 추적
            dist = min(abs(phys_col - col), abs(phys_col + span - 1 - col))
            if dist < best_dist:
                best_dist = dist
                best_tc = tc
            phys_col += span

        # 정확 매칭 실패 시 가장 가까운 셀 반환
        if best_tc is not None:
            import logging
            logging.getLogger(__name__).warning(
                f"get_cell: exact match failed for col {col} in row {row}, "
                f"returning nearest cell (dist={best_dist})"
            )
            return best_tc

        raise IndexError(f"Column {col} out of range in row {row}")

    # ------------------------------------------------------------------
    # Header/Footer 접근
    # ------------------------------------------------------------------

    @property
    def headers(self) -> list[etree._Element]:
        return self._headers

    @property
    def footers(self) -> list[etree._Element]:
        return self._footers

    def _load_headers_footers(self) -> None:
        """DOCX 패키지에서 header/footer XML 로드 (중복 제거)."""
        self._headers = []
        self._footers = []
        if self.docx_doc is None:
            return

        seen_ids: set[int] = set()

        for section in self.docx_doc.sections:
            # Header
            for header_attr in ("header", "first_page_header", "even_page_header"):
                try:
                    header = getattr(section, header_attr, None)
                    if header is not None and header._element is not None:
                        eid = id(header._element)
                        if eid not in seen_ids:
                            seen_ids.add(eid)
                            self._headers.append(header._element)
                except Exception:
                    pass

            # Footer
            for footer_attr in ("footer", "first_page_footer", "even_page_footer"):
                try:
                    footer = getattr(section, footer_attr, None)
                    if footer is not None and footer._element is not None:
                        eid = id(footer._element)
                        if eid not in seen_ids:
                            seen_ids.add(eid)
                            self._footers.append(footer._element)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # DSD 로드 (기존 parse_dsd 활용)
    # ------------------------------------------------------------------

    def load_dsd(self, path: str) -> None:
        """DSD 파일을 파싱하여 로드."""
        from skills.parse_dsd import parse_dsd
        self.dsd_data = parse_dsd(path)

    # ------------------------------------------------------------------
    # 편의 메서드
    # ------------------------------------------------------------------

    def num_tables(self) -> int:
        return len(self.get_tables())

    def table_row_count(self, table_index: int) -> int:
        return len(self.get_table_rows(table_index))


def _get_grid_span(tc: etree._Element) -> int:
    """셀의 gridSpan 값 반환 (기본 1)."""
    tc_pr = find_w(tc, "w:tcPr")
    if tc_pr is not None:
        gs = find_w(tc_pr, "w:gridSpan")
        if gs is not None:
            try:
                return int(gs.get(w("val"), "1"))
            except ValueError:
                pass
    return 1

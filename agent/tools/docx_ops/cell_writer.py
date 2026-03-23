"""
셀 텍스트 교체 — 서식(rPr, pPr, tcPr)을 완벽히 보존.

원본: skills/write_docx/docx_cell_writer.py
핵심 알고리즘:
  1. 모든 Run에서 <w:t> 수집
  2. 텍스트가 있는 마지막 Run 찾기
  3. 그 Run의 첫 <w:t>에 새 텍스트 삽입
  4. 나머지 모든 <w:t> 비우기 (Run 구조 보존)
  5. Run이 없으면 인접 Run에서 rPr을 deepcopy하여 새 Run 생성
"""

from __future__ import annotations

from copy import deepcopy
from lxml import etree

from .xml_helpers import w, find_w, findall_w, OOXML_NS, XML_SPACE


def set_cell_text(tc_element: etree._Element, new_text: str) -> None:
    """
    <w:tc> 요소의 텍스트를 변경. 기존 Run 서식을 보존.

    Args:
        tc_element: lxml의 <w:tc> 요소
        new_text: 새 텍스트
    """
    paragraphs = findall_w(tc_element, "w:p")
    if not paragraphs:
        return

    # 모든 문단의 Run과 <w:t> 요소 수집
    all_runs: list[tuple[etree._Element, list[etree._Element]]] = []
    for p in paragraphs:
        for r in findall_w(p, "w:r"):
            ts = findall_w(r, "w:t")
            all_runs.append((r, ts))

    # 텍스트가 있는 마지막 Run 찾기
    target_run = None
    target_ts = None
    for r, ts in reversed(all_runs):
        if ts:
            target_run = r
            target_ts = ts
            break

    if target_run is not None:
        # 타겟 Run의 첫 <w:t>에 새 텍스트 삽입
        target_ts[0].text = new_text
        target_ts[0].set(XML_SPACE, "preserve")
        # 같은 Run의 나머지 <w:t> 비우기
        for t in target_ts[1:]:
            t.text = ""
        # 다른 Run의 모든 <w:t> 비우기
        for r, ts in all_runs:
            if r is target_run:
                continue
            for t in ts:
                t.text = ""
    else:
        # Run이 없으면 새 Run 생성
        _create_run_with_text(paragraphs[0], new_text)


def clear_cell_text(tc_element: etree._Element) -> None:
    """셀 텍스트 비우기."""
    set_cell_text(tc_element, "")


def _create_run_with_text(p_element: etree._Element, text: str) -> None:
    """
    문단에 새 Run을 추가. 기존 Run이 있으면 rPr을 deepcopy.
    """
    # 기존 Run에서 rPr 복제 시도
    rpr_source = None
    for existing_r in findall_w(p_element, "w:r"):
        rpr = find_w(existing_r, "w:rPr")
        if rpr is not None:
            rpr_source = deepcopy(rpr)
            break

    run = etree.SubElement(p_element, w("r"))
    if rpr_source is not None:
        run.insert(0, rpr_source)

    t = etree.SubElement(run, w("t"))
    t.text = text
    t.set(XML_SPACE, "preserve")

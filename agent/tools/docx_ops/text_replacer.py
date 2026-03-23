"""
Cross-run 텍스트 교체 — 연도 롤링 등에 사용.

원본: skills/write_docx/docx_header_writer.py
핵심: <w:t> 요소가 여러 Run에 걸쳐 분리된 텍스트도 올바르게 교체.

알고리즘:
  1. 각 <w:p> 내의 모든 <w:t> 텍스트를 연결
  2. 연결된 텍스트에 모든 replacement를 atomic하게 적용
  3. 원래 <w:t> 요소의 크기에 맞게 텍스트 재분배
  4. 마지막 요소가 overflow 흡수
"""

from __future__ import annotations

from lxml import etree

from .xml_helpers import w, XML_SPACE


def replace_text_in_element(
    root: etree._Element,
    replacements: list[tuple[str, str]],
) -> bool:
    """
    XML 트리 내 모든 문단에서 텍스트 교체. Cross-run 대응.

    Args:
        root: 검색 대상 XML 트리 루트
        replacements: [(old, new), ...] 교체 쌍

    Returns:
        교체가 발생했으면 True
    """
    # 큰 값부터 정렬하여 cascade 방지
    # 예: "2024"→"2025" 먼저 적용 후 "2023"→"2024" 적용하면
    # "2023"이 "2024"로 바뀐 뒤 다시 "2025"로 바뀌는 문제 방지
    sorted_replacements = sorted(
        replacements, key=lambda pair: pair[0], reverse=True
    )

    changed = False

    for p in root.iter(w("p")):
        t_elements = list(p.iter(w("t")))
        if not t_elements:
            continue

        # 모든 <w:t> 텍스트 연결
        texts = [t.text or "" for t in t_elements]
        concat = "".join(texts)

        # 모든 교체를 한 번에 적용 (atomic)
        new_concat = concat
        for old, new in sorted_replacements:
            new_concat = new_concat.replace(old, new)

        if new_concat == concat:
            continue

        # 변경된 텍스트를 원래 <w:t> 요소에 재분배
        changed = True
        _redistribute_text(t_elements, texts, new_concat)

    return changed


def _redistribute_text(
    t_elements: list[etree._Element],
    original_texts: list[str],
    new_full_text: str,
) -> None:
    """
    새 텍스트를 원래 <w:t> 요소들에 재분배.
    원래 세그먼트 길이를 최대한 유지하고, 나머지는 마지막 요소에 할당.
    """
    pos = 0
    for i, t_elem in enumerate(t_elements):
        orig_len = len(original_texts[i])
        if i == len(t_elements) - 1:
            # 마지막 요소가 나머지 전부 흡수
            t_elem.text = new_full_text[pos:]
        else:
            t_elem.text = new_full_text[pos: pos + orig_len]
        pos += orig_len
        t_elem.set(XML_SPACE, "preserve")

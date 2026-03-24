"""
Cross-run 텍스트 교체 — 연도 롤링 등에 사용.

원본: skills/write_docx/docx_header_writer.py
핵심: <w:t> 요소가 여러 Run에 걸쳐 분리된 텍스트도 올바르게 교체.

알고리즘:
  1. 각 <w:p> 내의 모든 <w:t> 텍스트를 연결
  2. 연결된 텍스트에 모든 replacement를 단일 패스로 적용 (cascade 방지)
  3. 원래 <w:t> 요소의 크기에 맞게 텍스트 재분배
  4. 마지막 요소가 overflow 흡수
"""

from __future__ import annotations

import re

from lxml import etree

from .xml_helpers import w, XML_SPACE


def replace_text_in_element(
    root: etree._Element,
    replacements: list[tuple[str, str]],
) -> bool:
    """
    XML 트리 내 모든 문단에서 텍스트 교체. Cross-run 대응.

    단일 패스 교체: 모든 교체 쌍을 하나의 정규식으로 결합하여
    한 번에 교체. 긴 패턴 우선 매칭으로 cascade 완전 방지.

    Args:
        root: 검색 대상 XML 트리 루트
        replacements: [(old, new), ...] 교체 쌍

    Returns:
        교체가 발생했으면 True
    """
    if not replacements:
        return False

    # 긴 패턴부터 정규식 alternation으로 결합 (단일 패스 교체)
    # 같은 길이면 알파벳 역순 (2024 before 2023)
    sorted_repls = sorted(replacements, key=lambda p: (-len(p[0]), p[0]), reverse=False)
    repl_map = {old: new for old, new in sorted_repls}

    # 정규식 패턴: 긴 것부터 | 로 연결
    escaped = [re.escape(old) for old, _ in sorted_repls]
    pattern = re.compile("|".join(escaped))

    changed = False

    for p in root.iter(w("p")):
        t_elements = list(p.iter(w("t")))
        if not t_elements:
            continue

        # 모든 <w:t> 텍스트 연결
        texts = [t.text or "" for t in t_elements]
        concat = "".join(texts)

        # 단일 패스 교체 — 매칭된 패턴을 map에서 lookup
        new_concat = pattern.sub(lambda m: repl_map[m.group(0)], concat)

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

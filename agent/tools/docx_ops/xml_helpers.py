"""
OOXML 네임스페이스 상수 및 XML 유틸리티 함수.

원본: utils/xml_helpers.py에서 OOXML 관련 부분만 추출.
"""

from __future__ import annotations

from lxml import etree


OOXML_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
}

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def w(tag: str) -> str:
    """OOXML wordprocessingml 네임스페이스 태그 생성."""
    return f"{{{OOXML_NS['w']}}}{tag}"


def find_w(element: etree._Element, path: str) -> etree._Element | None:
    """w: 네임스페이스로 요소 검색."""
    return element.find(path, OOXML_NS)


def findall_w(element: etree._Element, path: str) -> list[etree._Element]:
    """w: 네임스페이스로 모든 요소 검색."""
    return element.findall(path, OOXML_NS)


def get_w_val(element: etree._Element, child_tag: str, default: str = "") -> str:
    """자식 요소의 w:val 속성 값을 반환."""
    child = find_w(element, f"w:{child_tag}")
    if child is not None:
        return child.get(w("val"), default)
    return default


def get_w_attr(element: etree._Element, attr: str, default: str = "") -> str:
    """w: 네임스페이스 속성 값을 반환."""
    return element.get(w(attr), default)


def get_cell_text(tc_element: etree._Element) -> str:
    """<w:tc> 요소에서 모든 텍스트를 추출."""
    texts = []
    for t in tc_element.iter(w("t")):
        if t.text:
            texts.append(t.text)
    return "".join(texts)

"""
Index each paragraph and table's position in the document body XML.

This is critical for the writer: it needs to know the exact position
of each element so it can insert/modify at the correct location.
"""

from __future__ import annotations

from dataclasses import dataclass
from lxml import etree
from docx import Document

from utils.xml_helpers import w


@dataclass
class ElementIndex:
    """Position info for a single body-level element."""
    body_index: int          # index among body children
    tag: str                 # 'p', 'tbl', 'bookmarkEnd', etc.
    element: object = None   # lxml element reference


def index_body_elements(doc: Document) -> list[ElementIndex]:
    """
    Walk the document body and record the position of every child element.

    Returns a list of ElementIndex objects in document order.
    Skips sectPr (section properties) at the end.
    """
    body = doc.element.body
    result: list[ElementIndex] = []

    for idx, child in enumerate(body):
        tag = etree.QName(child.tag).localname
        result.append(ElementIndex(
            body_index=idx,
            tag=tag,
            element=child,
        ))

    return result


def get_paragraph_indices(elements: list[ElementIndex]) -> list[ElementIndex]:
    """Filter to only paragraph elements."""
    return [e for e in elements if e.tag == "p"]


def get_table_indices(elements: list[ElementIndex]) -> list[ElementIndex]:
    """Filter to only table elements."""
    return [e for e in elements if e.tag == "tbl"]

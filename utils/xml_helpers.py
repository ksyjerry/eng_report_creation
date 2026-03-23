"""
XML helper utilities for parsing DSD and DOCX files.
"""

from lxml import etree
from typing import Optional


def get_text_content(element) -> str:
    """
    Extract all text content from an XML element, including children.
    Replaces &cr; with newline.
    """
    if element is None:
        return ""
    text = etree.tostring(element, method="text", encoding="unicode") or ""
    text = text.replace("&cr;", "\n").strip()
    return text


def get_direct_text(element) -> str:
    """Get only the direct text of an element (not children)."""
    if element is None:
        return ""
    return (element.text or "").strip()


def get_attr(element, attr: str, default: str = "") -> str:
    """Safely get an attribute value."""
    if element is None:
        return default
    return element.get(attr, default)


def find_all_recursive(element, tag: str) -> list:
    """Find all descendants with a given tag name."""
    return element.findall(f".//{tag}")


def element_to_text_lines(element) -> list[str]:
    """
    Convert an XML element to a list of text lines,
    handling &cr; entities and nested elements.
    """
    raw = get_text_content(element)
    lines = raw.split("\n")
    return [line.strip() for line in lines if line.strip()]


# OOXML (DOCX) namespace helpers
OOXML_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
}


def w(tag: str) -> str:
    """Create a namespaced tag for OOXML wordprocessingml."""
    return f"{{{OOXML_NS['w']}}}{tag}"


def find_w(element, path: str):
    """Find element using w: namespace."""
    return element.find(path, OOXML_NS)


def findall_w(element, path: str) -> list:
    """Find all elements using w: namespace."""
    return element.findall(path, OOXML_NS)


def get_w_val(element, child_tag: str, default: str = "") -> str:
    """Get w:val attribute from a child element."""
    child = find_w(element, f"w:{child_tag}")
    if child is not None:
        return child.get(w("val"), default)
    return default


def get_w_attr(element, attr: str, default: str = "") -> str:
    """Get a w: namespaced attribute."""
    return element.get(w(attr), default)

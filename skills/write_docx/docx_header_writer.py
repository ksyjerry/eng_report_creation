"""
Update header and footer XMLs — typically to roll years forward.

Handles patterns like:
  - "2024" → "2025"
  - "December 31, 2024 and 2023" → "December 31, 2025 and 2024"
  - Runs split across multiple <w:t> elements
"""

from __future__ import annotations

import re
from lxml import etree

from utils.xml_helpers import w, findall_w


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def replace_years_in_header_xml(
    root: etree._Element,
    replacements: list[tuple[str, str]],
) -> bool:
    """
    Apply year string replacements to a parsed header/footer XML tree.

    Args:
        root:          The root element of header*.xml (parsed lxml tree).
        replacements:  List of ``(old_year, new_year)`` string pairs, e.g.
                       ``[("2024", "2025"), ("2023", "2024")]``.

    Returns:
        True if any replacement was made.

    The function handles two cases:
      1. A single ``<w:t>`` contains the year string → simple replace.
      2. The year string is split across adjacent ``<w:t>`` elements
         within the same ``<w:r>`` or across runs in the same paragraph
         → concatenate, replace, redistribute.
    """
    changed = False

    # Sort replacements so the larger (more recent) year is replaced first.
    # This prevents "2024" → "2025" from partially matching text that
    # contains "2024" as part of a longer replaced string.
    sorted_replacements = sorted(
        replacements, key=lambda pair: pair[0], reverse=True
    )

    # Use cross-run replacement which handles both single-element and
    # multi-element (split year) cases correctly by concatenating all
    # <w:t> texts in each paragraph and applying all replacements at once.
    # This avoids the cascade problem where Strategy 1 changes "2023"→"2024"
    # and then Strategy 2 changes that "2024"→"2025".
    if _cross_run_replacement(root, sorted_replacements):
        changed = True

    return changed


# ------------------------------------------------------------------
# Internals
# ------------------------------------------------------------------

def _cross_run_replacement(
    root: etree._Element,
    replacements: list[tuple[str, str]],
) -> bool:
    """
    Concatenate text across runs in each paragraph and apply replacements.
    """
    changed = False

    for p in root.iter(w("p")):
        t_elements = list(p.iter(w("t")))
        if not t_elements:
            continue

        # Build concatenated string and a mapping of char-index → t_element
        texts = [t.text or "" for t in t_elements]
        concat = "".join(texts)

        new_concat = concat
        for old, new in replacements:
            new_concat = new_concat.replace(old, new)

        if new_concat == concat:
            continue

        # Redistribute the new text back across the same <w:t> elements,
        # keeping the original lengths where possible.
        changed = True
        _redistribute_text(t_elements, texts, new_concat)

    return changed


def _redistribute_text(
    t_elements: list,
    original_texts: list[str],
    new_full_text: str,
) -> None:
    """
    Distribute *new_full_text* across *t_elements*, keeping the original
    segment lengths as closely as possible.

    If the new text is the same length as the original, each element gets
    exactly the same number of characters.  Otherwise, overflow goes into
    the last element.
    """
    pos = 0
    for i, t_elem in enumerate(t_elements):
        orig_len = len(original_texts[i])
        if i == len(t_elements) - 1:
            # Last element gets the remainder
            t_elem.text = new_full_text[pos:]
        else:
            t_elem.text = new_full_text[pos: pos + orig_len]
        pos += orig_len
        # Preserve spaces
        t_elem.set(
            "{http://www.w3.org/XML/1998/namespace}space", "preserve"
        )

"""
Replace cell text while preserving all formatting.

Core principle: never create XML elements from scratch.  Find the existing
runs inside the cell's paragraph(s), keep every rPr / pPr / tcPr intact,
and only swap out the text content.
"""

from __future__ import annotations

from copy import deepcopy
from lxml import etree

from utils.xml_helpers import w, find_w, findall_w, OOXML_NS


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def set_cell_text(tc_element, new_text: str) -> None:
    """
    Replace all visible text in a ``<w:tc>`` element with *new_text*,
    preserving formatting (tcPr, pPr, rPr).

    Strategy:
      1. Collect all ``<w:r>`` runs across all ``<w:p>`` paragraphs.
      2. Put *new_text* into the **last run that contains a <w:t>** (this
         is the dominant run in most financial-statement cells).
      3. Blank out every other run's ``<w:t>`` elements.
      4. If the cell has **no runs at all**, create one minimal run
         inside the first paragraph (cloning rPr from a sibling cell
         would be ideal, but as a fallback we create a bare ``<w:r>``).
    """
    paragraphs = findall_w(tc_element, "w:p")
    if not paragraphs:
        return

    # Gather every run across all paragraphs
    all_runs: list[tuple] = []  # (run_element, [t_elements])
    for p in paragraphs:
        for r in findall_w(p, "w:r"):
            ts = findall_w(r, "w:t")
            all_runs.append((r, ts))

    # Find the last run that has at least one <w:t>
    target_run = None
    target_ts = None
    for r, ts in reversed(all_runs):
        if ts:
            target_run = r
            target_ts = ts
            break

    if target_run is not None:
        # Put all text into the first <w:t> of the target run
        target_ts[0].text = new_text
        # Ensure xml:space="preserve" so leading/trailing spaces survive
        target_ts[0].set(
            "{http://www.w3.org/XML/1998/namespace}space", "preserve"
        )
        # Blank out remaining <w:t> in the same run
        for t in target_ts[1:]:
            t.text = ""
        # Blank out every OTHER run's <w:t> elements
        for r, ts in all_runs:
            if r is target_run:
                continue
            for t in ts:
                t.text = ""
    else:
        # No runs with text at all → create a minimal run in the first para
        _create_run_with_text(paragraphs[0], new_text)


def clear_cell_text(tc_element) -> None:
    """Remove all visible text from a cell, preserving structure."""
    set_cell_text(tc_element, "")


# ------------------------------------------------------------------
# Internals
# ------------------------------------------------------------------

def _create_run_with_text(p_element, text: str) -> None:
    """
    Append a new ``<w:r><w:t>text</w:t></w:r>`` to a paragraph.

    If the paragraph already has an ``<w:rPr>`` on any existing run, clone
    it so the new run inherits the same formatting.
    """
    nsmap = {"w": OOXML_NS["w"]}

    # Try to borrow rPr from an existing run in this paragraph
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
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

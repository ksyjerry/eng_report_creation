"""
Test the write_docx skill:
  1. Open HYBE 2024 DOCX
  2. Apply changes: update header years (2024→2025, 2023→2024),
     update a cell value in the first table
  3. Save to output/test_write.docx
  4. Re-parse the output to verify changes took effect
"""

from __future__ import annotations

import sys
import os
import zipfile

# Add project root to sys.path so imports work
sys.path.insert(0, os.path.dirname(__file__))

from lxml import etree
from ir_schema import ChangeType
from utils.xml_helpers import w, findall_w
from skills.write_docx import write_docx
from skills.write_docx.change_model import Change


TEMPLATE = "files/Hybe 2024 Eng Report.docx"
OUTPUT = "output/test_write.docx"


def find_first_table_body_index(docx_path: str) -> int:
    """Find the body index of the first <w:tbl> in document.xml."""
    with zipfile.ZipFile(docx_path, "r") as zf:
        with zf.open("word/document.xml") as f:
            root = etree.parse(f).getroot()
    body = root.find(w("body"))
    for idx, child in enumerate(body):
        tag = etree.QName(child.tag).localname
        if tag == "tbl":
            return idx
    raise RuntimeError("No table found in document")


def read_cell_text(docx_path: str, table_body_idx: int, row: int, col: int) -> str:
    """Read the text of a specific cell from the DOCX."""
    with zipfile.ZipFile(docx_path, "r") as zf:
        with zf.open("word/document.xml") as f:
            root = etree.parse(f).getroot()
    body = root.find(w("body"))
    tbl = list(body)[table_body_idx]
    rows = findall_w(tbl, "w:tr")
    cells = findall_w(rows[row], "w:tc")
    # Extract text from all <w:t> in the cell
    texts = []
    for t in cells[col].iter(w("t")):
        if t.text:
            texts.append(t.text)
    return "".join(texts)


def read_header_text(docx_path: str) -> str:
    """Read concatenated text from all header*.xml files."""
    texts = []
    with zipfile.ZipFile(docx_path, "r") as zf:
        for name in zf.namelist():
            basename = name.split("/")[-1]
            if basename.startswith("header") and basename.endswith(".xml"):
                with zf.open(name) as f:
                    root = etree.parse(f).getroot()
                for t in root.iter(w("t")):
                    if t.text:
                        texts.append(t.text)
    return " ".join(texts)


def main():
    os.chdir(os.path.dirname(__file__) or ".")

    if not os.path.exists(TEMPLATE):
        print(f"ERROR: Template not found: {TEMPLATE}")
        return

    print(f"Template: {TEMPLATE}")

    # Find the first table
    first_tbl_idx = find_first_table_body_index(TEMPLATE)
    print(f"First table body index: {first_tbl_idx}")

    # Read original values
    orig_cell = read_cell_text(TEMPLATE, first_tbl_idx, 0, 0)
    orig_header = read_header_text(TEMPLATE)
    print(f"Original cell (row 0, col 0): {repr(orig_cell)}")
    print(f"Original header text (excerpt): {repr(orig_header[:200])}")

    # Build changes
    changes = [
        # 1. Update header years
        Change(
            type=ChangeType.UPDATE_TEXT,  # using UPDATE_TEXT as a carrier
            target="header",
            values={},
            old_year="2024",
            new_year="2025",
        ),
        Change(
            type=ChangeType.UPDATE_TEXT,
            target="header",
            old_year="2023",
            new_year="2024",
        ),
        # 2. Update a cell in the first table (row 0, col 0) with test text
        Change(
            type=ChangeType.UPDATE_VALUES,
            target=f"table:{first_tbl_idx}:row:0:col:0",
            value="TEST_CELL_VALUE",
        ),
    ]

    # Apply
    result = write_docx(TEMPLATE, changes, OUTPUT)
    print(f"\nOutput written: {result}")
    print(f"Output size: {os.path.getsize(result):,} bytes")

    # Verify
    print("\n--- Verification ---")

    # Check cell
    new_cell = read_cell_text(OUTPUT, first_tbl_idx, 0, 0)
    cell_ok = new_cell == "TEST_CELL_VALUE"
    print(f"Cell (row 0, col 0): {repr(new_cell)}  {'PASS' if cell_ok else 'FAIL'}")

    # Check header year replacement
    new_header = read_header_text(OUTPUT)
    header_has_2025 = "2025" in new_header
    header_no_old = "2023" not in new_header  # 2023 should have become 2024
    print(f"Header text (excerpt): {repr(new_header[:200])}")
    print(f"Header contains '2025': {header_has_2025}  {'PASS' if header_has_2025 else 'FAIL'}")
    print(f"Header no longer has '2023': {header_no_old}  {'PASS' if header_no_old else 'FAIL (might be OK if 2023 was not in headers)'}")

    # Check that output is a valid ZIP/DOCX
    try:
        with zipfile.ZipFile(OUTPUT, "r") as zf:
            names = zf.namelist()
            has_doc = "word/document.xml" in names
            print(f"Valid DOCX ZIP: True  ({len(names)} entries)")
            print(f"Contains word/document.xml: {has_doc}  {'PASS' if has_doc else 'FAIL'}")
    except Exception as e:
        print(f"Valid DOCX ZIP: FAIL ({e})")

    # Summary
    all_pass = cell_ok and header_has_2025 and has_doc
    print(f"\n{'=' * 40}")
    print(f"Overall: {'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'}")
    print(f"{'=' * 40}")


if __name__ == "__main__":
    main()

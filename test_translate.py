"""
Test script for the translate skill.
Tests glossary building with HYBE files (DSD 2025 + DOCX 2024).
Tests translation of Korean labels using glossary + IFRS terms (no API needed).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from collections import Counter


def print_separator(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def test_glossary_building():
    """Test glossary auto-building from HYBE DSD + DOCX pair."""
    from skills.parse_dsd import parse_dsd
    from skills.parse_docx import parse_docx
    from skills.translate.glossary_builder import build_glossary

    dsd_path = "files/Hybe 2025 Eng Report.dsd"
    docx_path = "files/Hybe 2024 Eng Report.docx"

    if not os.path.exists(dsd_path):
        print(f"  SKIP: DSD file not found: {dsd_path}")
        return None, None, None
    if not os.path.exists(docx_path):
        print(f"  SKIP: DOCX file not found: {docx_path}")
        return None, None, None

    print("  Parsing DSD...")
    dsd_doc = parse_dsd(dsd_path)
    print(f"    Notes: {len(dsd_doc.get_all_notes())}")
    print(f"    Financial statements: {len(dsd_doc.get_financial_statements())}")

    print("  Parsing DOCX...")
    docx_doc = parse_docx(docx_path)
    print(f"    Notes: {len(docx_doc.get_all_notes())}")
    print(f"    Financial statements: {len(docx_doc.get_financial_statements())}")

    print("\n  Building glossary...")
    glossary = build_glossary(dsd_doc, docx_doc)

    print(f"\n  Total glossary entries: {len(glossary)}")

    # Count by source
    source_counts = Counter(glossary.sources.values())
    print(f"\n  Entries by source:")
    for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        print(f"    {source}: {count}")

    # Show sample entries by source
    print(f"\n  Sample glossary entries (10 value-matched):")
    value_matched = [
        (ko, en) for ko, en in glossary.entries.items()
        if glossary.sources.get(ko) == "value_match"
    ]
    for ko, en in value_matched[:10]:
        print(f"    {ko} -> {en}")

    if len(value_matched) < 10:
        print(f"\n  Sample glossary entries (title/header matched):")
        other = [
            (ko, en) for ko, en in glossary.entries.items()
            if glossary.sources.get(ko) in ("title_match", "header_match")
        ]
        for ko, en in other[:10]:
            print(f"    {ko} -> {en}  [{glossary.sources[ko]}]")

    return glossary, dsd_doc, docx_doc


def test_label_translation(glossary):
    """Test translating Korean labels using glossary + IFRS terms."""
    from skills.translate.translator import translate_label, translate_note_title

    if glossary is None:
        print("  SKIP: No glossary available")
        return

    test_labels = [
        "현금및현금성자산",
        "매출채권",
        "재고자산",
        "유형자산",
        "무형자산",
        "매출액",
        "매출원가",
        "영업이익",
        "당기순이익",
        "자본총계",
        "이익잉여금",
        "감가상각비",
        "충당부채",
        "관계기업투자",
        "사용권자산",
        "리스부채",
        "확정급여부채",
        "법인세비용",
        "주당이익",
        "기타포괄손익누계액",
    ]

    print(f"  Testing {len(test_labels)} Korean labels (no API):\n")
    for label in test_labels:
        result = translate_label(label, glossary, api_key=None)
        marker = ""
        if result.startswith("[NEEDS_TRANSLATION"):
            marker = " [UNRESOLVED]"
        print(f"    {label:<25} -> {result}{marker}")

    # Test note titles
    print(f"\n  Testing note title translation:\n")
    test_titles = [
        ("현금및현금성자산", "5"),
        ("유형자산", "12"),
        ("충당부채", "18"),
        ("특수관계자와의 거래", "25"),
        ("우발부채 및 약정사항", "30"),
    ]
    for title, num in test_titles:
        result = translate_note_title(title, glossary, note_number=num)
        print(f"    Note {num}: {title} -> {result}")


def test_change_translation(glossary, dsd_doc, docx_doc):
    """Test translating Change objects."""
    from ir_schema import ChangeType
    from skills.write_docx.change_model import Change
    from skills.translate import translate_changes

    if glossary is None:
        print("  SKIP: No documents available")
        return

    # Create some synthetic Change objects with Korean text
    test_changes = [
        Change(
            type=ChangeType.UPDATE_VALUES,
            target="table:5:row:3",
            values={0: "현금및현금성자산", 1: "412,039,917", 2: "350,000,000"},
        ),
        Change(
            type=ChangeType.UPDATE_VALUES,
            target="table:5:row:4",
            values={0: "매출채권", 1: "123,456,789", 2: "111,111,111"},
        ),
        Change(
            type=ChangeType.ADD_ROW,
            target="table:12:element:0",
            rows=[
                {0: "사용권자산", 1: "50,000,000", 2: "45,000,000"},
                {0: "리스부채", 1: "48,000,000", 2: "43,000,000"},
            ],
        ),
        Change(
            type=ChangeType.ADD_NOTE,
            target="note:99",
            value="파생상품",
            content=[
                ("paragraph", "당기말 현재 파생상품의 내역은 다음과 같습니다."),
                ("table_row", "구분 | 금액 | 공정가치"),
            ],
        ),
    ]

    print(f"  Translating {len(test_changes)} synthetic changes...\n")

    translated = translate_changes(
        test_changes, dsd_doc, docx_doc, api_key=None
    )

    for i, change in enumerate(translated):
        print(f"  Change {i+1} ({change.type.value}):")
        if change.values:
            for col, val in change.values.items():
                print(f"    col {col}: {val}")
        if change.rows:
            for j, row in enumerate(change.rows):
                print(f"    row {j}: {row}")
        if change.value:
            print(f"    value: {change.value}")
        if change.content:
            for ctype, ctext in change.content:
                print(f"    {ctype}: {ctext}")
        print()


def main():
    print_separator("Test 1: Glossary Building (HYBE)")
    glossary, dsd_doc, docx_doc = test_glossary_building()

    print_separator("Test 2: Label Translation (Glossary + IFRS)")
    test_label_translation(glossary)

    print_separator("Test 3: Change Object Translation")
    test_change_translation(glossary, dsd_doc, docx_doc)

    print_separator("Done")


if __name__ == "__main__":
    main()

"""
Test script for the map_sections skill.
Tests with HYBE and SBL file pairs.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from collections import Counter
from ir_schema import ChangeType


def print_separator(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_mappings(mappings):
    print(f"  Total mappings: {len(mappings)}")
    by_method = Counter(m.match_method for m in mappings)
    for method, count in sorted(by_method.items()):
        print(f"    {method}: {count}")

    print(f"\n  Matched pairs:")
    for m in mappings:
        dsd_label = f"DSD #{m.dsd_note.number}: {m.dsd_note.title[:40]}"
        if m.docx_note:
            docx_label = f"DOCX #{m.docx_note.number}: {m.docx_note.title[:40]}"
            print(f"    {dsd_label:<50} -> {docx_label:<50} [{m.match_method} conf={m.confidence:.2f}]")
        else:
            print(f"    {dsd_label:<50} -> (UNMATCHED) [{m.match_method}]")


def print_diffs(section_diffs, year_roll):
    if year_roll:
        print(f"  Year roll: {year_roll.old_current}/{year_roll.old_prior} -> {year_roll.new_current}/{year_roll.new_prior}")
    else:
        print(f"  Year roll: None detected")

    by_mag = Counter(sd.magnitude.value for sd in section_diffs)
    print(f"\n  Diff magnitudes:")
    for mag, count in sorted(by_mag.items()):
        print(f"    {mag}: {count}")


def print_changes(changes):
    print(f"  Total changes: {len(changes)}")
    by_type = Counter(c.type.value for c in changes)
    for ctype, count in sorted(by_type.items()):
        print(f"    {ctype}: {count}")

    print(f"\n  Sample changes (first 15):")
    for c in changes[:15]:
        detail = ""
        if c.old_year:
            detail = f" [{c.old_year} -> {c.new_year}]"
        elif c.value:
            detail = f" [{c.value[:50]}]"
        elif c.values:
            n_vals = len(c.values)
            detail = f" [{n_vals} cell(s) updated]"
        print(f"    {c.type.value:20s} target={c.target:40s}{detail}")


def test_hybe():
    print_separator("HYBE Test")

    dsd_path = os.path.join(os.path.dirname(__file__), "files", "Hybe 2025 Eng Report.dsd")
    docx_path = os.path.join(os.path.dirname(__file__), "files", "Hybe 2024 Eng Report.docx")

    if not os.path.exists(dsd_path):
        print(f"  SKIP: DSD file not found: {dsd_path}")
        return
    if not os.path.exists(docx_path):
        print(f"  SKIP: DOCX file not found: {docx_path}")
        return

    from skills.parse_dsd import parse_dsd
    from skills.parse_docx import parse_docx
    from skills.map_sections import map_sections_detailed

    print("  Parsing DSD...")
    dsd_doc = parse_dsd(dsd_path)
    print(f"    DSD: {dsd_doc.meta.company}, periods={dsd_doc.meta.period_current}/{dsd_doc.meta.period_prior}")
    print(f"    DSD notes: {len(dsd_doc.get_all_notes())}")
    for n in dsd_doc.get_all_notes()[:5]:
        print(f"      #{n.number}: {n.title} ({len(n.elements)} elements)")

    print("\n  Parsing DOCX...")
    docx_doc = parse_docx(docx_path)
    print(f"    DOCX: {docx_doc.meta.company}, periods={docx_doc.meta.period_current}/{docx_doc.meta.period_prior}")
    print(f"    DOCX notes: {len(docx_doc.get_all_notes())}")
    for n in docx_doc.get_all_notes()[:5]:
        print(f"      #{n.number}: {n.title} ({len(n.elements)} elements)")

    print("\n  Running map_sections...")
    changes, mappings, section_diffs, year_roll = map_sections_detailed(dsd_doc, docx_doc)

    print("\n--- MAPPINGS ---")
    print_mappings(mappings)

    print("\n--- DIFFS ---")
    print_diffs(section_diffs, year_roll)

    print("\n--- CHANGES ---")
    print_changes(changes)


def test_sbl():
    print_separator("SBL Test")

    dsd_path = os.path.join(os.path.dirname(__file__), "files", "SBL_2024_별도감사보고서.dsd")
    docx_path = os.path.join(os.path.dirname(__file__), "files", "SBL_2023_English report_vF.docx")

    if not os.path.exists(dsd_path):
        print(f"  SKIP: DSD file not found: {dsd_path}")
        return
    if not os.path.exists(docx_path):
        print(f"  SKIP: DOCX file not found: {docx_path}")
        return

    from skills.parse_dsd import parse_dsd
    from skills.parse_docx import parse_docx
    from skills.map_sections import map_sections_detailed

    print("  Parsing DSD...")
    dsd_doc = parse_dsd(dsd_path)
    print(f"    DSD: {dsd_doc.meta.company}, periods={dsd_doc.meta.period_current}/{dsd_doc.meta.period_prior}")
    print(f"    DSD notes: {len(dsd_doc.get_all_notes())}")
    for n in dsd_doc.get_all_notes()[:5]:
        print(f"      #{n.number}: {n.title} ({len(n.elements)} elements)")

    print("\n  Parsing DOCX...")
    docx_doc = parse_docx(docx_path)
    print(f"    DOCX: {docx_doc.meta.company}, periods={docx_doc.meta.period_current}/{docx_doc.meta.period_prior}")
    print(f"    DOCX notes: {len(docx_doc.get_all_notes())}")
    for n in docx_doc.get_all_notes()[:5]:
        print(f"      #{n.number}: {n.title} ({len(n.elements)} elements)")

    print("\n  Running map_sections...")
    changes, mappings, section_diffs, year_roll = map_sections_detailed(dsd_doc, docx_doc)

    print("\n--- MAPPINGS ---")
    print_mappings(mappings)

    print("\n--- DIFFS ---")
    print_diffs(section_diffs, year_roll)

    print("\n--- CHANGES ---")
    print_changes(changes)


if __name__ == "__main__":
    test_hybe()
    test_sbl()
    print("\n\nDone.")

"""
Test the review skill using HYBE files:
  1. Parse the DSD (2025) as the ground truth
  2. Use the existing DOCX (2024) as a stand-in "output" to test the review pipeline
  3. Run review — should report number mismatches (2024 data != 2025 data)
  4. Print the review report summary
"""

from __future__ import annotations

import sys
import os

# Add project root to sys.path so imports work
sys.path.insert(0, os.path.dirname(__file__))

from skills.parse_dsd import parse_dsd
from skills.review import review


DSD_FILE = "files/Hybe 2025 Eng Report.dsd"
DOCX_FILE = "files/Hybe 2024 Eng Report.docx"


def main():
    os.chdir(os.path.dirname(__file__) or ".")

    # Verify files exist
    if not os.path.exists(DSD_FILE):
        print(f"ERROR: DSD file not found: {DSD_FILE}")
        return
    if not os.path.exists(DOCX_FILE):
        print(f"ERROR: DOCX file not found: {DOCX_FILE}")
        return

    print(f"DSD source (2025): {DSD_FILE}")
    print(f"Output DOCX (2024, stand-in): {DOCX_FILE}")
    print()

    # Step 1: Parse DSD
    print("Parsing DSD...")
    dsd_doc = parse_dsd(DSD_FILE)
    print(f"  Company: {dsd_doc.meta.company}")
    print(f"  Periods: {dsd_doc.meta.period_current} / {dsd_doc.meta.period_prior}")
    print(f"  Financial statements: {len(dsd_doc.get_financial_statements())}")
    print(f"  Notes: {len(dsd_doc.get_all_notes())}")
    print()

    # Step 2: Run review (DOCX 2024 vs DSD 2025)
    print("Running review...")
    report = review(DOCX_FILE, dsd_doc)
    print()

    # Step 3: Print report
    print(report)

    # Step 4: Print summary
    print("=" * 50)
    print(f"Status: {report.status}")
    print(f"Total items: {report.summary.get('total', 0)}")
    print()
    print("By severity:")
    for sev, cnt in report.summary.get("by_severity", {}).items():
        print(f"  {sev}: {cnt}")
    print()
    print("By category:")
    for cat, cnt in report.summary.get("by_category", {}).items():
        print(f"  {cat}: {cnt}")

    # Expectation: since 2024 DOCX has 2024 data but DSD has 2025 data,
    # we should see number mismatches
    criticals = report.summary.get("by_severity", {}).get("CRITICAL", 0)
    warnings = report.summary.get("by_severity", {}).get("WARNING", 0)
    print()
    if criticals > 0 or warnings > 0:
        print(f"EXPECTED: Found {criticals} critical and {warnings} warning items")
        print("(This is correct — 2024 DOCX data doesn't match 2025 DSD data)")
    else:
        print("NOTE: No mismatches found — review pipeline may need investigation")


if __name__ == "__main__":
    main()

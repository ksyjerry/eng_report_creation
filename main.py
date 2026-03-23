"""
Financial Statement Translation Pipeline
=========================================

Transforms a Korean financial statement (DSD) into an English financial
statement (DOCX) by updating a prior-year English template.

Usage:
    python main.py <dsd_file> <docx_template> [output_file]

Example:
    python main.py files/Hybe\ 2025\ Eng\ Report.dsd files/Hybe\ 2024\ Eng\ Report.docx
    python main.py files/SBL_2024_별도감사보고서.dsd files/SBL_2023_English\ report_vF.docx
"""

import os
import sys
import time
import argparse
from dataclasses import asdict

from config import OUTPUT_DIR, GENAI_API_KEY, MAX_REVIEW_ITERATIONS

from skills.parse_dsd import parse_dsd
from skills.parse_docx import parse_docx
from skills.map_sections import map_sections
from skills.translate import translate_changes
from skills.write_docx import write_docx
from skills.review import review


def log(phase: str, msg: str):
    print(f"[{phase}] {msg}")


def run_pipeline(dsd_path: str, docx_path: str, output_path: str = "",
                 api_key: str = "", skip_review: bool = False, verbose: bool = False):
    """
    Run the full translation pipeline.

    Args:
        dsd_path: Path to the current-year Korean DSD file
        docx_path: Path to the prior-year English DOCX template
        output_path: Path for the output DOCX (auto-generated if empty)
        api_key: PwC GenAI Gateway API key for LLM translation (optional)
        skip_review: Skip the review phase
        verbose: Print detailed progress
    """
    start_time = time.time()

    # ── Phase 1: Parse ──────────────────────────────────────
    log("PARSE", f"Parsing DSD: {os.path.basename(dsd_path)}")
    t0 = time.time()
    dsd_doc = parse_dsd(dsd_path)
    log("PARSE", f"  DSD done in {time.time()-t0:.1f}s — "
        f"Company: {dsd_doc.meta.company}, "
        f"Type: {dsd_doc.meta.doc_type.value}, "
        f"Period: {dsd_doc.meta.period_current}/{dsd_doc.meta.period_prior}, "
        f"FS: {len(dsd_doc.get_financial_statements())}, "
        f"Notes: {len(dsd_doc.get_all_notes())}")

    log("PARSE", f"Parsing DOCX: {os.path.basename(docx_path)}")
    t0 = time.time()
    docx_doc = parse_docx(docx_path)
    log("PARSE", f"  DOCX done in {time.time()-t0:.1f}s — "
        f"Company: {docx_doc.meta.company}, "
        f"Profile: spacing={docx_doc.docx_profile.spacing_strategy.value}, "
        f"merge={docx_doc.docx_profile.merge_strategy.value}, "
        f"Notes: {len(docx_doc.get_all_notes())}")

    # ── Phase 2: Map & Diff ─────────────────────────────────
    log("MAP", "Mapping sections and generating change plan...")
    t0 = time.time()
    changes = map_sections(dsd_doc, docx_doc)
    log("MAP", f"  Done in {time.time()-t0:.1f}s — {len(changes)} changes generated")

    if verbose:
        _print_change_summary(changes)

    # ── Phase 3: Translate ──────────────────────────────────
    log("TRANSLATE", "Translating Korean content to English...")
    t0 = time.time()
    translated_changes = translate_changes(
        changes, dsd_doc, docx_doc,
        api_key=api_key or GENAI_API_KEY or None
    )
    log("TRANSLATE", f"  Done in {time.time()-t0:.1f}s")

    # Count translations
    needs_translation = sum(
        1 for c in translated_changes
        if _has_needs_translation(c)
    )
    if needs_translation > 0:
        log("TRANSLATE", f"  ⚠ {needs_translation} items still need translation (no API key)")

    # ── Phase 4: Write ──────────────────────────────────────
    if not output_path:
        company = dsd_doc.meta.company.split("(")[0].strip()
        company = company.replace("주식회사 ", "").replace("와 그 종속회사", "").strip()
        year = dsd_doc.meta.period_current
        output_path = os.path.join(OUTPUT_DIR, f"{company}_{year}_Eng_Report.docx")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    log("WRITE", f"Writing output: {os.path.basename(output_path)}")
    t0 = time.time()
    result_path = write_docx(docx_path, translated_changes, output_path)
    log("WRITE", f"  Done in {time.time()-t0:.1f}s → {result_path}")

    # ── Phase 5: Review ─────────────────────────────────────
    if not skip_review:
        for iteration in range(MAX_REVIEW_ITERATIONS):
            log("REVIEW", f"Reviewing output (iteration {iteration + 1}/{MAX_REVIEW_ITERATIONS})...")
            t0 = time.time()
            report = review(result_path, dsd_doc, docx_doc.docx_profile)
            log("REVIEW", f"  Done in {time.time()-t0:.1f}s — Status: {report.status}")
            log("REVIEW", f"  {report.summary}")

            if report.status == "PASS":
                log("REVIEW", "  ✓ All checks passed!")
                break
            elif iteration < MAX_REVIEW_ITERATIONS - 1:
                log("REVIEW", f"  Issues found, but auto-fix not yet implemented. "
                    f"See report for details.")
                # TODO: implement auto-fix from review report
                break
            else:
                log("REVIEW", "  Max iterations reached. Manual review needed.")

    total_time = time.time() - start_time
    log("DONE", f"Pipeline complete in {total_time:.1f}s")
    log("DONE", f"Output: {result_path}")

    return result_path


def _has_needs_translation(change) -> bool:
    """Check if a change still has untranslated Korean text."""
    marker = "[NEEDS_TRANSLATION:"
    if hasattr(change, 'value') and isinstance(change.value, str) and marker in change.value:
        return True
    if hasattr(change, 'values') and isinstance(change.values, dict):
        for v in change.values.values():
            if isinstance(v, str) and marker in v:
                return True
    if hasattr(change, 'content') and isinstance(change.content, list):
        for item in change.content:
            if isinstance(item, (list, tuple)) and len(item) > 1:
                if isinstance(item[1], str) and marker in item[1]:
                    return True
    return False


def _print_change_summary(changes):
    """Print a summary of changes by type."""
    from collections import Counter
    counts = Counter(c.type.value if hasattr(c.type, 'value') else str(c.type) for c in changes)
    log("MAP", "  Change breakdown:")
    for ctype, count in sorted(counts.items()):
        log("MAP", f"    {ctype}: {count}")


def main():
    parser = argparse.ArgumentParser(
        description="Translate Korean financial statements (DSD) to English (DOCX)"
    )
    parser.add_argument("dsd_file", help="Path to Korean DSD file (current year)")
    parser.add_argument("docx_template", help="Path to English DOCX template (prior year)")
    parser.add_argument("output", nargs="?", default="",
                        help="Output DOCX path (optional, auto-generated if omitted)")
    parser.add_argument("--api-key", default="",
                        help="PwC GenAI Gateway API key (or set PwC_LLM_API_KEY env var)")
    parser.add_argument("--skip-review", action="store_true",
                        help="Skip the review phase")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print detailed progress")

    args = parser.parse_args()

    run_pipeline(
        dsd_path=args.dsd_file,
        docx_path=args.docx_template,
        output_path=args.output,
        api_key=args.api_key,
        skip_review=args.skip_review,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()

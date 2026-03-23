"""
change_generator.py — Generate Change objects from semantic structure diffs.

Conservative policy:
  - Only generate UPDATE_VALUES for numeric cells in matched rows (confidence >= 0.5)
  - Only generate UPDATE_TEXT for year rolling in headers
  - NEVER generate ADD_ROW, DELETE_ROW, ADD_TABLE, DELETE_TABLE, ADD_NOTE, DELETE_NOTE
  - Unmatched rows/tables/notes are logged but no destructive changes are emitted

An untouched DOCX table is 100x better than a corrupted one.
"""

from __future__ import annotations

import re
import logging
from ir_schema import ChangeType, ElementType
from skills.write_docx.change_model import Change
from skills.map_sections.structure_differ import (
    SectionDiff, YearRoll, TableDiff, DiffMagnitude, TableMatch, RowMatch,
    _is_numeric_text,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Helpers: column mapping for numeric updates
# ──────────────────────────────────────────────

def _detect_period_columns(table, year_roll: YearRoll | None) -> dict[str, int]:
    """
    Detect which columns in a table correspond to 'current' and 'prior' periods
    by scanning header rows for year strings or Korean period markers.

    Validates detected columns against data rows — if a detected column has no
    actual numeric values in data rows, shifts to the nearest column that does.

    Returns dict like {"current": 2, "prior": 3} (column indices).
    """
    if not year_roll or not year_roll.is_rolling:
        return {}

    # Korean period markers
    current_markers = {"당기", "당기말", "당분기", "당분기말"}
    prior_markers = {"전기", "전기말", "전분기", "전분기말"}

    # Collect ALL candidate columns for each period from headers
    current_candidates: list[int] = []
    prior_candidates: list[int] = []

    for header_row in table.headers:
        for col_idx, cell in enumerate(header_row.cells):
            text = cell.text.strip()
            if not text:
                continue
            if year_roll.old_current in text or year_roll.new_current in text:
                current_candidates.append(col_idx)
            elif year_roll.old_prior in text or year_roll.new_prior in text:
                prior_candidates.append(col_idx)
            elif any(m in text for m in current_markers):
                current_candidates.append(col_idx)
            elif any(m in text for m in prior_markers):
                prior_candidates.append(col_idx)

    if not current_candidates and not prior_candidates:
        return {}

    # Build a set of columns that have actual numeric values in data rows
    value_cols: set[int] = set()
    for row in table.rows[:10]:  # check first 10 data rows
        for col_idx, cell in enumerate(row.cells):
            if _has_actual_numeric_value(cell.text):
                value_cols.add(col_idx)

    result: dict[str, int] = {}

    # For each period, pick the candidate column that has actual values
    for period, candidates in [("current", current_candidates), ("prior", prior_candidates)]:
        best = None
        for c in candidates:
            if c in value_cols:
                best = c
                break
        if best is None and candidates:
            # No candidate has values — try adjacent columns (header may span spacer+value)
            for c in candidates:
                for adj in (c + 1, c - 1):
                    if adj in value_cols:
                        best = adj
                        break
                if best is not None:
                    break
        if best is not None:
            result[period] = best

    return result


def _has_actual_numeric_value(text: str) -> bool:
    """Return True if text has an actual numeric value (not just empty/dash/spacer)."""
    t = text.strip()
    if not t or t in ('-', '–', '—', '\\', ''):
        return False
    return _is_numeric_text(t)


def _parse_num_value(text: str) -> float | None:
    """Parse a numeric value from text for comparison."""
    import re
    t = text.strip()
    if not t or t in ('-', '–', '—', '\\'):
        return 0.0
    neg = t.startswith('(') and t.endswith(')')
    if neg:
        t = t[1:-1]
    t = re.sub(r'[₩$€¥£\s,]', '', t)
    if not t:
        return 0.0
    try:
        val = float(t)
        return -val if neg else val
    except ValueError:
        return None


def _validate_row_match(
    dsd_row, docx_row,
    dsd_period_cols: dict[str, int],
    docx_period_cols: dict[str, int],
    match_method: str,
) -> bool:
    """
    Validate a row match by checking if DSD prior period value matches
    DOCX current period value. Returns False to skip this row's changes
    if there's clear evidence of a wrong match.
    """
    # Only validate for similar_label matches (position_fallback already validated)
    if match_method not in ("similar_label",):
        return True

    if "prior" not in dsd_period_cols or "current" not in docx_period_cols:
        return True  # can't validate, allow

    dsd_prior_col = dsd_period_cols["prior"]
    docx_current_col = docx_period_cols["current"]

    if dsd_prior_col >= len(dsd_row.cells) or docx_current_col >= len(docx_row.cells):
        return True

    dsd_v = _parse_num_value(dsd_row.cells[dsd_prior_col].text)
    docx_v = _parse_num_value(docx_row.cells[docx_current_col].text)

    if dsd_v is None or docx_v is None:
        return True

    # If both are zero or very small, allow
    if abs(dsd_v) < 1 and abs(docx_v) < 1:
        return True

    # If values match exactly, definitely correct
    if abs(dsd_v - docx_v) < 1.5:
        return True

    # If values are very different (>2x ratio), likely wrong match
    if abs(dsd_v) > 0 and abs(docx_v) > 0:
        ratio = max(abs(dsd_v), abs(docx_v)) / min(abs(dsd_v), abs(docx_v))
        if ratio > 2.0:
            logger.info(
                "Skipping likely wrong similar_label match: DSD prior=%s, DOCX current=%s (ratio=%.1f)",
                dsd_v, docx_v, ratio,
            )
            return False

    return True


def _build_numeric_column_map(
    dsd_row,
    docx_row,
    dsd_period_cols: dict[str, int],
    docx_period_cols: dict[str, int],
) -> dict[int, int]:
    """
    Build a mapping from DSD column index → DOCX column index for numeric cells.

    Strategy:
      1. If period columns are detected, map current→current, prior→prior.
      2. Otherwise, collect columns with ACTUAL numeric values (skip empty/dash/spacer)
         and map them in order.
    """
    dsd_numeric_cols: list[int] = []
    for i, cell in enumerate(dsd_row.cells):
        if _has_actual_numeric_value(cell.text):
            dsd_numeric_cols.append(i)

    docx_numeric_cols: list[int] = []
    for i, cell in enumerate(docx_row.cells):
        if _has_actual_numeric_value(cell.text):
            docx_numeric_cols.append(i)

    col_map: dict[int, int] = {}

    # If we have period column info, use it for direct mapping
    if dsd_period_cols and docx_period_cols:
        if "current" in dsd_period_cols and "current" in docx_period_cols:
            col_map[dsd_period_cols["current"]] = docx_period_cols["current"]
        if "prior" in dsd_period_cols and "prior" in docx_period_cols:
            col_map[dsd_period_cols["prior"]] = docx_period_cols["prior"]

        # If we already mapped all DSD numeric cols via period info, we're done
        mapped_dsd = set(col_map.keys())
        remaining_dsd = [c for c in dsd_numeric_cols if c not in mapped_dsd]
        mapped_docx = set(col_map.values())
        remaining_docx = [c for c in docx_numeric_cols if c not in mapped_docx]

        # Map remaining numeric columns in order
        for d, x in zip(remaining_dsd, remaining_docx):
            col_map[d] = x
    else:
        # No period info — map numeric columns in order
        for d, x in zip(dsd_numeric_cols, docx_numeric_cols):
            col_map[d] = x

    return col_map


def _to_physical_columns(values: dict[int, str], docx_table) -> dict[int, str]:
    """
    Convert logical column indices to physical column indices using the
    table's logical_to_physical mapping. If no mapping exists, return as-is.
    """
    if not hasattr(docx_table, 'logical_to_physical') or not docx_table.logical_to_physical:
        return values

    phys_values: dict[int, str] = {}
    for log_col, text in values.items():
        phys_col = docx_table.logical_to_physical.get(log_col)
        if phys_col is not None:
            phys_values[phys_col] = text
        else:
            # No mapping — use logical index as-is (might be correct for DSD tables)
            phys_values[log_col] = text
    return phys_values


# ──────────────────────────────────────────────
# Year rolling changes
# ──────────────────────────────────────────────

def _generate_year_roll_changes(year_roll: YearRoll) -> list[Change]:
    """
    Generate header/period text replacement changes for year rolling.
    This is the ONLY safe text change — replacing year strings in headers/footers.
    """
    changes: list[Change] = []

    if not year_roll.is_rolling:
        return changes

    # Current year replacement
    changes.append(Change(
        type=ChangeType.UPDATE_TEXT,
        target="header",
        old_year=year_roll.old_current,
        new_year=year_roll.new_current,
    ))

    # Prior year replacement
    if year_roll.old_prior and year_roll.new_prior:
        changes.append(Change(
            type=ChangeType.UPDATE_TEXT,
            target="header",
            old_year=year_roll.old_prior,
            new_year=year_roll.new_prior,
        ))

    return changes


# ──────────────────────────────────────────────
# Table-level changes (conservative)
# ──────────────────────────────────────────────

def _generate_table_changes(
    section_diff: SectionDiff,
    docx_note_number: str,
) -> list[Change]:
    """
    Generate UPDATE_VALUES changes for matched table rows.

    Conservative rules:
      - Only process tables that have a TableMatch (both sides exist)
      - Only update numeric cells in rows matched with confidence >= 0.5
      - Skip header rows entirely
      - DON'T generate ADD_ROW, DELETE_ROW, ADD_TABLE, DELETE_TABLE
    """
    changes: list[Change] = []
    year_roll = section_diff.year_roll

    for td in section_diff.table_diffs:
        # Skip new/deleted tables — we do NOT add or delete tables
        if td.is_new:
            logger.info(
                "Skipping new DSD table %d in note %s (flagged for review)",
                td.dsd_table_idx, docx_note_number,
            )
            continue

        if td.is_deleted:
            logger.info(
                "Keeping DOCX table %d in note %s (not in DSD, but not deleting)",
                td.docx_table_idx, docx_note_number,
            )
            continue

        if td.table_match is None:
            continue

        tm = td.table_match
        if td.dsd_table is None or td.docx_table is None:
            continue

        docx_tbl_idx = td.docx_table_idx

        # Detect period columns for smart column mapping
        dsd_period_cols = _detect_period_columns(td.dsd_table, year_roll)
        docx_period_cols = _detect_period_columns(td.docx_table, year_roll)

        # Combined row lists for indexing
        dsd_all_rows = td.dsd_table.headers + td.dsd_table.rows
        docx_all_rows = td.docx_table.headers + td.docx_table.rows

        # Process matched rows
        for rm in tm.row_matches:
            if rm.confidence < 0.5:
                logger.debug(
                    "Skipping low-confidence match (%.2f) for DSD row %d → DOCX row %d",
                    rm.confidence, rm.dsd_row_idx, rm.docx_row_idx,
                )
                continue

            dsd_row = dsd_all_rows[rm.dsd_row_idx]
            docx_row = docx_all_rows[rm.docx_row_idx]

            # Validate match using value cross-check
            if not _validate_row_match(
                dsd_row, docx_row, dsd_period_cols, docx_period_cols, rm.match_method
            ):
                continue

            # Build numeric column mapping
            col_map = _build_numeric_column_map(
                dsd_row, docx_row, dsd_period_cols, docx_period_cols
            )

            # Generate value updates for numeric cells only
            values: dict[int, str] = {}
            for dsd_col_idx, docx_col_idx in col_map.items():
                if dsd_col_idx >= len(dsd_row.cells):
                    continue
                if docx_col_idx >= len(docx_row.cells):
                    continue

                dsd_text = dsd_row.cells[dsd_col_idx].text.strip()
                docx_text = docx_row.cells[docx_col_idx].text.strip()

                # Only update if both cells have actual numeric values and they differ
                if (_has_actual_numeric_value(dsd_text) and _has_actual_numeric_value(docx_text)
                        and dsd_text != docx_text):
                    values[docx_col_idx] = dsd_text

            if values:
                # Convert logical column indices to physical column indices
                # (DOCX tables may have spacer columns removed during parsing)
                phys_values = _to_physical_columns(values, td.docx_table)
                changes.append(Change(
                    type=ChangeType.UPDATE_VALUES,
                    target=f"note:{docx_note_number}:element:{docx_tbl_idx}:row:{rm.docx_row_idx}",
                    values=phys_values,
                ))

        # Log unmatched rows (no changes generated)
        if tm.unmatched_dsd_rows:
            labels = []
            for idx in tm.unmatched_dsd_rows:
                if idx < len(dsd_all_rows):
                    label = ""
                    for cell in dsd_all_rows[idx].cells:
                        if cell.text.strip():
                            label = cell.text.strip()[:40]
                            break
                    labels.append(f"  row {idx}: {label}")
            logger.info(
                "Unmatched DSD rows in note %s table %d (flagged for review):\n%s",
                docx_note_number, docx_tbl_idx, "\n".join(labels),
            )

        if tm.unmatched_docx_rows:
            labels = []
            for idx in tm.unmatched_docx_rows:
                if idx < len(docx_all_rows):
                    label = ""
                    for cell in docx_all_rows[idx].cells:
                        if cell.text.strip():
                            label = cell.text.strip()[:40]
                            break
                    labels.append(f"  row {idx}: {label}")
            logger.info(
                "Unmatched DOCX rows in note %s table %d (kept as-is):\n%s",
                docx_note_number, docx_tbl_idx, "\n".join(labels),
            )

    return changes


# ──────────────────────────────────────────────
# Note-level changes (conservative)
# ──────────────────────────────────────────────

def _generate_note_changes(section_diff: SectionDiff) -> list[Change]:
    """
    Generate changes for a single section diff.

    Conservative: we do NOT generate ADD_NOTE for unmatched DSD notes.
    We only generate UPDATE_VALUES for matched table rows.
    """
    changes: list[Change] = []
    mapping = section_diff.mapping

    # Unmatched DSD note → skip entirely (flag for review, don't add)
    if mapping.docx_note is None:
        logger.info(
            "Skipping unmatched DSD note %s '%s' (flagged for review, not adding)",
            mapping.dsd_note.number, mapping.dsd_note.title,
        )
        return changes

    # Matched pair → generate conservative table-level changes
    docx_num = mapping.docx_note.number
    changes.extend(_generate_table_changes(section_diff, docx_num))

    return changes


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def generate_changes(
    section_diffs: list[SectionDiff],
    year_roll: YearRoll | None,
    deleted_docx_notes: list | None = None,
) -> list[Change]:
    """
    Generate all Change objects from structure differences.

    Conservative policy:
      - Year rolling text changes (UPDATE_TEXT) for headers
      - UPDATE_VALUES for numeric cells in semantically matched rows
      - NO add_row, delete_row, add_table, delete_table, add_note, delete_note

    Args:
        section_diffs: List of SectionDiff for matched note pairs.
        year_roll: Detected year rolling (or None).
        deleted_docx_notes: DOCX notes not matched to any DSD note.
            (Logged but NOT deleted — conservative policy.)

    Returns:
        List of Change objects ready for the write_docx skill.
    """
    changes: list[Change] = []

    # 1. Year rolling changes (applied globally)
    if year_roll and year_roll.is_rolling:
        changes.extend(_generate_year_roll_changes(year_roll))

    # 2. Per-section changes (UPDATE_VALUES only)
    for sd in section_diffs:
        changes.extend(_generate_note_changes(sd))

    # 3. Deleted notes — DO NOT delete. Just log them.
    if deleted_docx_notes:
        for note in deleted_docx_notes:
            logger.info(
                "DOCX note %s '%s' has no DSD match — kept as-is (not deleting)",
                note.number, note.title,
            )

    return changes

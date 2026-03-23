"""
structure_differ.py — Conservative semantic matching between DSD/DOCX tables.

Instead of matching rows by position index (which causes catastrophic corruption
when DSD and DOCX have different header counts, spacer columns, or row ordering),
this module matches rows by LABEL TEXT and only flags numeric cells for update.

Key principles:
  - Match rows by their label (first non-empty text cell), NOT by position
  - Never delete or add rows/tables — flag unmatched items for review
  - Header rows are never modified (except year rolling)
  - Only numeric cells in matched rows are candidates for update
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from ir_schema import (
    Note, NoteElement, ElementType, TableData, TableRow, CellValue,
    FinancialStatement, ParsedDocument,
)
from skills.map_sections.section_matcher import SectionMapping
from skills.translate.ifrs_terms import IFRS_TERMS, lookup_ifrs_term, lookup_ifrs_partial


class DiffMagnitude(Enum):
    IDENTICAL = "identical"
    MINOR = "minor"             # Values only changed
    MODERATE = "moderate"       # Some rows unmatched
    MAJOR = "major"             # Many rows unmatched or structural mismatch


# ──────────────────────────────────────────────
# Row / Table match dataclasses
# ──────────────────────────────────────────────

@dataclass
class RowMatch:
    """A matched pair of rows between DSD and DOCX tables."""
    dsd_row_idx: int        # index in DSD combined (headers+rows) list
    docx_row_idx: int       # index in DOCX combined (headers+rows) list
    confidence: float       # 0.0–1.0
    match_method: str       # "exact_label", "similar_label", "position_fallback"


@dataclass
class TableMatch:
    """Full match result for a DSD/DOCX table pair."""
    dsd_table_idx: int              # table-only index within DSD note
    docx_table_idx: int             # table-only index within DOCX note
    dsd_table: Optional[TableData] = None
    docx_table: Optional[TableData] = None
    row_matches: list[RowMatch] = field(default_factory=list)
    unmatched_dsd_rows: list[int] = field(default_factory=list)
    unmatched_docx_rows: list[int] = field(default_factory=list)
    header_row_count: int = 0       # number of header rows to skip in DOCX


@dataclass
class TableDiff:
    """Differences between a DSD table and the corresponding DOCX table."""
    dsd_table_idx: int
    docx_table_idx: int
    dsd_table: Optional[TableData] = None
    docx_table: Optional[TableData] = None
    table_match: Optional[TableMatch] = None
    is_new: bool = False            # table exists in DSD but not DOCX
    is_deleted: bool = False        # table exists in DOCX but not DSD
    magnitude: DiffMagnitude = DiffMagnitude.IDENTICAL


@dataclass
class YearRoll:
    """Detected year rolling between periods."""
    old_current: str = ""       # e.g., "2024"
    old_prior: str = ""         # e.g., "2023"
    new_current: str = ""       # e.g., "2025"
    new_prior: str = ""         # e.g., "2024"

    @property
    def is_rolling(self) -> bool:
        return bool(self.new_current and self.old_current
                     and self.new_current != self.old_current)


@dataclass
class SectionDiff:
    """Full diff result for one matched section pair."""
    mapping: SectionMapping
    year_roll: Optional[YearRoll] = None
    table_diffs: list[TableDiff] = field(default_factory=list)
    paragraph_count_diff: int = 0
    magnitude: DiffMagnitude = DiffMagnitude.IDENTICAL


# ──────────────────────────────────────────────
# Helpers: label extraction & similarity
# ──────────────────────────────────────────────

_NUM_RE = re.compile(
    r'^[\s\-–—()]*'                    # leading whitespace / dashes / parens
    r'[\d,.\s]*'                       # digits, commas, dots, spaces
    r'[\s\-–—()]*$'                    # trailing
)


def _is_numeric_text(text: str) -> bool:
    """Return True if the text looks like a number (including negative, commas, parens)."""
    t = text.strip()
    if not t or t == '-' or t == '–' or t == '—':
        return True  # treat dashes/empty as "numeric-ish" (placeholders)
    # Remove parens used for negatives: (1,234) -> 1,234
    t = t.strip('()')
    # Remove currency symbols and whitespace
    t = re.sub(r'[₩$€¥£\s,]', '', t)
    if not t:
        return True
    try:
        float(t)
        return True
    except ValueError:
        return False


def _get_row_label(row: TableRow) -> str:
    """
    Extract the label from a row: the first non-empty, non-numeric cell text.
    This is typically column 0 (the line-item description).
    """
    for cell in row.cells:
        text = cell.text.strip()
        if text and not _is_numeric_text(text):
            return text
    return ""


def _normalize_label(label: str) -> str:
    """Normalize a label for comparison: lowercase, strip whitespace/punctuation."""
    s = label.strip().lower()
    # Remove common suffixes like colons, periods
    s = re.sub(r'[\s:;,.\-–—]+$', '', s)
    # Collapse multiple spaces
    s = re.sub(r'\s+', ' ', s)
    return s


def _translate_korean_label(korean_label: str) -> str:
    """
    Translate a Korean row label to English using IFRS terms dictionary.
    Returns the English translation, or empty string if not found.
    """
    text = korean_label.strip()
    if not text:
        return ""
    # Exact match
    eng = lookup_ifrs_term(text)
    if eng:
        return eng
    # Partial/substring match
    eng = lookup_ifrs_partial(text)
    if eng:
        return eng
    return ""


def _is_korean(text: str) -> bool:
    """Check if text contains Korean characters."""
    return bool(re.search(r'[\uac00-\ud7af\u3130-\u318f]', text))


def _label_similarity(label_a: str, label_b: str) -> float:
    """
    Compute similarity between two labels, including cross-language matching.
    Returns 0.0–1.0.

    Strategies:
      1. Exact match after normalization → 1.0
      2. One contains the other → 0.8
      3. Cross-language: translate Korean label via IFRS terms → compare → 0.9
      4. Jaccard token similarity
    """
    if not label_a or not label_b:
        return 0.0

    na = _normalize_label(label_a)
    nb = _normalize_label(label_b)

    if not na or not nb:
        return 0.0

    # Exact match
    if na == nb:
        return 1.0

    # Containment
    if na in nb or nb in na:
        shorter = min(len(na), len(nb))
        longer = max(len(na), len(nb))
        return 0.7 + 0.3 * (shorter / longer)

    # Cross-language matching: if one is Korean and other is English
    ko_label, en_label = "", ""
    if _is_korean(label_a) and not _is_korean(label_b):
        ko_label, en_label = label_a, label_b
    elif _is_korean(label_b) and not _is_korean(label_a):
        ko_label, en_label = label_b, label_a

    if ko_label and en_label:
        translated = _translate_korean_label(ko_label)
        if translated:
            trans_norm = _normalize_label(translated)
            en_norm = _normalize_label(en_label)
            if trans_norm and en_norm:
                # Exact translated match
                if trans_norm == en_norm:
                    return 0.95
                # Containment after translation
                if trans_norm in en_norm or en_norm in trans_norm:
                    shorter = min(len(trans_norm), len(en_norm))
                    longer = max(len(trans_norm), len(en_norm))
                    return 0.7 + 0.25 * (shorter / longer)
                # Jaccard on translated tokens
                trans_tokens = set(trans_norm.split())
                en_tokens = set(en_norm.split())
                if trans_tokens and en_tokens:
                    overlap = len(trans_tokens & en_tokens)
                    union = len(trans_tokens | en_tokens)
                    jaccard = overlap / union if union > 0 else 0.0
                    if jaccard >= 0.3:
                        return 0.6 + 0.3 * jaccard

    # Jaccard on word tokens (same-language fallback)
    tokens_a = set(na.split())
    tokens_b = set(nb.split())
    if not tokens_a or not tokens_b:
        return 0.0

    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union > 0 else 0.0


def _is_header_row(row: TableRow, row_idx: int) -> bool:
    """
    Heuristic: a row is a header row if:
      - It's marked as is_header_row, OR
      - It's in position 0 or 1 and has no numeric-looking data cells
    """
    if row.is_header_row:
        return True
    if row_idx <= 1:
        # Check if all cells are non-numeric or empty
        has_numeric = False
        for cell in row.cells:
            t = cell.text.strip()
            if t and _is_numeric_text(t):
                # But skip dashes/empty — those could be in headers too
                clean = re.sub(r'[₩$€¥£\s,().\-–—]', '', t)
                if clean and clean.replace('.', '').isdigit():
                    has_numeric = True
                    break
        if not has_numeric:
            return True
    return False


def _detect_header_row_count(table: TableData) -> int:
    """Count header rows in a table (explicit headers + implicit header-like rows)."""
    count = len(table.headers)
    # Also check if the first data rows look like headers
    for i, row in enumerate(table.rows):
        if _is_header_row(row, count + i):
            count += 1
        else:
            break
    return max(count, 1)  # At least 1 header row


# ──────────────────────────────────────────────
# Value-based validation for position matches
# ──────────────────────────────────────────────

def _parse_num(text: str) -> float | None:
    """Try to parse a numeric cell value."""
    t = text.strip()
    if not t or t in ('-', '–', '—'):
        return 0.0
    neg = False
    if t.startswith('(') and t.endswith(')'):
        neg = True
        t = t[1:-1]
    t = re.sub(r'[₩$€¥£\s,]', '', t)
    if not t:
        return 0.0
    try:
        val = float(t)
        return -val if neg else val
    except ValueError:
        return None


def _validate_position_match(
    dsd_row: TableRow,
    docx_row: TableRow,
    same_row_count: bool,
    has_prior_matches: bool,
) -> float:
    """
    Validate a position-based row match by checking numeric value overlap.
    Returns confidence 0.0–0.7.

    Logic:
      - If at least one numeric cell has the same value → 0.65 (confirmed)
      - If both rows have numeric cells but none match → 0.35 (low confidence, below threshold)
      - If neither row has numeric cells → 0.55 if same count, else 0.45
    """
    dsd_nums = []
    for c in dsd_row.cells:
        v = _parse_num(c.text)
        if v is not None and c.text.strip() not in ('', '-', '–', '—'):
            dsd_nums.append(v)

    docx_nums = []
    for c in docx_row.cells:
        v = _parse_num(c.text)
        if v is not None and c.text.strip() not in ('', '-', '–', '—'):
            docx_nums.append(v)

    if dsd_nums and docx_nums:
        # Check if any numeric value appears in both rows
        dsd_set = set(dsd_nums)
        docx_set = set(docx_nums)
        if dsd_set & docx_set:
            return 0.65  # Value overlap confirmed
        # No overlap — this is likely a wrong match
        return 0.35
    else:
        # No numeric cells to validate — use structural signals
        if same_row_count and has_prior_matches:
            return 0.55
        elif same_row_count:
            return 0.5
        else:
            return 0.4


# ──────────────────────────────────────────────
# Row matching algorithm
# ──────────────────────────────────────────────

def match_table_rows(dsd_table: TableData, docx_table: TableData) -> TableMatch:
    """
    Match DSD data rows to DOCX data rows by label text.

    Algorithm:
      1. Skip header rows in both tables.
      2. For each DSD data row, extract its label.
      3. For each DOCX data row, extract its label.
      4. Pass 1: exact label matches (after normalization).
      5. Pass 2: similar label matches (similarity >= 0.6).
      6. Pass 3: position fallback ONLY if tables have same data row count
         AND very few rows remain unmatched.
      7. Everything else goes into unmatched lists (NO delete/add).
    """
    dsd_header_count = len(dsd_table.headers)
    docx_header_count = len(docx_table.headers)

    dsd_all_rows = dsd_table.headers + dsd_table.rows
    docx_all_rows = docx_table.headers + docx_table.rows

    # Determine which rows are data rows (skip headers + empty/formatting rows)
    dsd_data_indices: list[int] = []
    for i in range(dsd_header_count, len(dsd_all_rows)):
        row = dsd_all_rows[i]
        if not row.is_empty:
            dsd_data_indices.append(i)

    docx_data_indices: list[int] = []
    for i in range(docx_header_count, len(docx_all_rows)):
        row = docx_all_rows[i]
        if not row.is_empty:
            docx_data_indices.append(i)

    # Extract labels
    dsd_labels: dict[int, str] = {}
    for idx in dsd_data_indices:
        dsd_labels[idx] = _get_row_label(dsd_all_rows[idx])

    docx_labels: dict[int, str] = {}
    for idx in docx_data_indices:
        docx_labels[idx] = _get_row_label(docx_all_rows[idx])

    matches: list[RowMatch] = []
    matched_dsd: set[int] = set()
    matched_docx: set[int] = set()

    # --- Pass 1: Exact label matches ---
    for dsd_idx in dsd_data_indices:
        dsd_label = dsd_labels[dsd_idx]
        if not dsd_label:
            continue
        dsd_norm = _normalize_label(dsd_label)
        if not dsd_norm:
            continue

        for docx_idx in docx_data_indices:
            if docx_idx in matched_docx:
                continue
            docx_label = docx_labels[docx_idx]
            if not docx_label:
                continue
            docx_norm = _normalize_label(docx_label)
            if dsd_norm == docx_norm:
                matches.append(RowMatch(
                    dsd_row_idx=dsd_idx,
                    docx_row_idx=docx_idx,
                    confidence=1.0,
                    match_method="exact_label",
                ))
                matched_dsd.add(dsd_idx)
                matched_docx.add(docx_idx)
                break

    # --- Pass 2: Similar label matches ---
    remaining_dsd = [i for i in dsd_data_indices if i not in matched_dsd]
    remaining_docx = [i for i in docx_data_indices if i not in matched_docx]

    for dsd_idx in remaining_dsd:
        dsd_label = dsd_labels[dsd_idx]
        if not dsd_label:
            continue

        best_docx_idx = -1
        best_sim = 0.0
        for docx_idx in remaining_docx:
            if docx_idx in matched_docx:
                continue
            docx_label = docx_labels[docx_idx]
            if not docx_label:
                continue
            sim = _label_similarity(dsd_label, docx_label)
            if sim > best_sim:
                best_sim = sim
                best_docx_idx = docx_idx

        if best_docx_idx >= 0 and best_sim >= 0.6:
            matches.append(RowMatch(
                dsd_row_idx=dsd_idx,
                docx_row_idx=best_docx_idx,
                confidence=best_sim,
                match_method="similar_label",
            ))
            matched_dsd.add(dsd_idx)
            matched_docx.add(best_docx_idx)

    # --- Pass 3: Position fallback with value validation ---
    # Match remaining rows by position, then validate with numeric value overlap.
    remaining_dsd = [i for i in dsd_data_indices if i not in matched_dsd]
    remaining_docx = [i for i in docx_data_indices if i not in matched_docx]

    # Match by position up to the shorter list's length
    match_count = min(len(remaining_dsd), len(remaining_docx))
    if match_count > 0:
        # Higher base confidence if tables have same row count
        same_count = len(dsd_data_indices) == len(docx_data_indices)
        has_prior_matches = len(matches) > 0

        for dsd_idx, docx_idx in zip(remaining_dsd[:match_count], remaining_docx[:match_count]):
            # Validate: check if numeric cells have any value overlap
            dsd_row = dsd_all_rows[dsd_idx]
            docx_row = docx_all_rows[docx_idx]
            conf = _validate_position_match(dsd_row, docx_row, same_count, has_prior_matches)

            matches.append(RowMatch(
                dsd_row_idx=dsd_idx,
                docx_row_idx=docx_idx,
                confidence=conf,
                match_method="position_fallback",
            ))
            matched_dsd.add(dsd_idx)
            matched_docx.add(docx_idx)

    # Collect unmatched
    final_unmatched_dsd = [i for i in dsd_data_indices if i not in matched_dsd]
    final_unmatched_docx = [i for i in docx_data_indices if i not in matched_docx]

    return TableMatch(
        dsd_table_idx=-1,  # caller sets this
        docx_table_idx=-1,  # caller sets this
        dsd_table=dsd_table,
        docx_table=docx_table,
        row_matches=matches,
        unmatched_dsd_rows=final_unmatched_dsd,
        unmatched_docx_rows=final_unmatched_docx,
        header_row_count=docx_header_count,
    )


# ──────────────────────────────────────────────
# Table-level matching (by position within note)
# ──────────────────────────────────────────────

def _count_elements(elements: list[NoteElement], etype: ElementType) -> int:
    return sum(1 for e in elements if e.type == etype)


def _get_tables(elements: list[NoteElement]) -> list[tuple[int, TableData]]:
    """Return (table_only_index, TableData) pairs for all table elements."""
    result = []
    table_counter = 0
    for e in elements:
        if e.type == ElementType.TABLE and e.table is not None:
            result.append((table_counter, e.table))
            table_counter += 1
    return result


def _diff_tables(
    dsd_tables: list[tuple[int, TableData]],
    docx_tables: list[tuple[int, TableData]],
) -> list[TableDiff]:
    """
    Compare tables by position order but use SEMANTIC row matching within each pair.

    Conservative policy:
      - Tables that exist in both → match rows semantically
      - Extra DSD tables → flag as new (but DON'T generate ADD_TABLE changes)
      - Extra DOCX tables → flag as deleted (but DON'T generate DELETE_TABLE changes)
    """
    diffs: list[TableDiff] = []
    max_len = max(len(dsd_tables), len(docx_tables)) if dsd_tables or docx_tables else 0

    for i in range(max_len):
        has_dsd = i < len(dsd_tables)
        has_docx = i < len(docx_tables)

        if has_dsd and has_docx:
            dsd_idx, dsd_tbl = dsd_tables[i]
            docx_idx, docx_tbl = docx_tables[i]

            # Semantic row matching
            tm = match_table_rows(dsd_tbl, docx_tbl)
            tm.dsd_table_idx = dsd_idx
            tm.docx_table_idx = docx_idx

            # Determine magnitude
            if not tm.row_matches:
                mag = DiffMagnitude.MAJOR
            elif tm.unmatched_dsd_rows or tm.unmatched_docx_rows:
                mag = DiffMagnitude.MODERATE
            else:
                mag = DiffMagnitude.MINOR

            diffs.append(TableDiff(
                dsd_table_idx=dsd_idx,
                docx_table_idx=docx_idx,
                dsd_table=dsd_tbl,
                docx_table=docx_tbl,
                table_match=tm,
                magnitude=mag,
            ))

        elif has_dsd and not has_docx:
            dsd_idx, dsd_tbl = dsd_tables[i]
            diffs.append(TableDiff(
                dsd_table_idx=dsd_idx,
                docx_table_idx=-1,
                dsd_table=dsd_tbl,
                is_new=True,
                magnitude=DiffMagnitude.MAJOR,
            ))

        elif has_docx and not has_dsd:
            docx_idx, docx_tbl = docx_tables[i]
            diffs.append(TableDiff(
                dsd_table_idx=-1,
                docx_table_idx=docx_idx,
                docx_table=docx_tbl,
                is_deleted=True,
                magnitude=DiffMagnitude.MAJOR,
            ))

    return diffs


# ──────────────────────────────────────────────
# Year roll detection
# ──────────────────────────────────────────────

def detect_year_roll(
    dsd_doc: ParsedDocument,
    docx_doc: ParsedDocument,
) -> Optional[YearRoll]:
    """Detect year rolling by comparing document metadata periods."""
    dsd_meta = dsd_doc.meta
    docx_meta = docx_doc.meta

    if not dsd_meta.period_current or not docx_meta.period_current:
        return None

    yr = YearRoll(
        old_current=docx_meta.period_current,
        old_prior=docx_meta.period_prior,
        new_current=dsd_meta.period_current,
        new_prior=dsd_meta.period_prior,
    )
    return yr if yr.is_rolling else None


# ──────────────────────────────────────────────
# Section diffing
# ──────────────────────────────────────────────

def diff_section(mapping: SectionMapping) -> SectionDiff:
    """Compare a matched DSD/DOCX section pair and produce a SectionDiff."""
    dsd_note = mapping.dsd_note
    docx_note = mapping.docx_note

    # Unmatched DSD note — entirely new section (flag only, don't add)
    if docx_note is None:
        return SectionDiff(
            mapping=mapping,
            magnitude=DiffMagnitude.MAJOR,
        )

    # Compare tables with semantic row matching
    dsd_tables = _get_tables(dsd_note.elements)
    docx_tables = _get_tables(docx_note.elements)
    table_diffs = _diff_tables(dsd_tables, docx_tables)

    # Compare paragraph counts (informational only)
    dsd_para_count = _count_elements(dsd_note.elements, ElementType.PARAGRAPH)
    docx_para_count = _count_elements(docx_note.elements, ElementType.PARAGRAPH)
    para_diff = dsd_para_count - docx_para_count

    # Overall magnitude
    if table_diffs:
        worst = max(td.magnitude.value for td in table_diffs)
        mag_map = {m.value: m for m in DiffMagnitude}
        overall_mag = mag_map.get(worst, DiffMagnitude.MINOR)
    elif abs(para_diff) > 3:
        overall_mag = DiffMagnitude.MODERATE
    elif abs(para_diff) > 0:
        overall_mag = DiffMagnitude.MINOR
    else:
        overall_mag = DiffMagnitude.IDENTICAL

    return SectionDiff(
        mapping=mapping,
        table_diffs=table_diffs,
        paragraph_count_diff=para_diff,
        magnitude=overall_mag,
    )


def diff_all_sections(
    mappings: list[SectionMapping],
    dsd_doc: ParsedDocument,
    docx_doc: ParsedDocument,
) -> tuple[list[SectionDiff], Optional[YearRoll]]:
    """
    Diff all matched section pairs and detect year rolling.

    Returns:
        (list of SectionDiff, YearRoll or None)
    """
    year_roll = detect_year_roll(dsd_doc, docx_doc)

    section_diffs = []
    for mapping in mappings:
        sd = diff_section(mapping)
        sd.year_roll = year_roll
        section_diffs.append(sd)

    return section_diffs, year_roll

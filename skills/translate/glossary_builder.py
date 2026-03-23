"""
glossary_builder.py — Auto-build Korean↔English glossary from matched prior-year data.

Compares DSD (Korean, current year) with DOCX (English, prior year).
When numeric values match between DSD prior-year column and DOCX current-year column,
the row labels form a glossary pair (Korean → English).

Also seeds the glossary from known note title mappings and IFRS terms.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ir_schema import (
    ParsedDocument, Section, Note, NoteElement, ElementType,
    TableData, TableRow, FinancialStatement,
)
from skills.map_sections.section_matcher import KO_EN_TITLE_MAP
from skills.translate.ifrs_terms import IFRS_TERMS


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

_NUM_RE = re.compile(r"[^\d.\-]")  # keep digits, dots, minus


def _extract_number(text: str) -> str | None:
    """
    Extract a normalized numeric string from a cell.
    Removes commas, whitespace, parentheses (for negatives).
    Returns None if the cell is not numeric.
    """
    if not text:
        return None
    t = text.strip()
    if not t or t == "-" or t == "—" or t == "–":
        return None

    # Handle parenthesized negatives: (1,234) -> -1234
    negative = False
    if t.startswith("(") and t.endswith(")"):
        negative = True
        t = t[1:-1]

    # Remove commas and spaces
    t = t.replace(",", "").replace(" ", "").replace("\u00a0", "")

    # Check if it's a number
    cleaned = _NUM_RE.sub("", t)
    if not cleaned:
        return None

    try:
        val = float(cleaned)
        if negative:
            val = -val
        # Normalize: remove trailing .0
        if val == int(val):
            return str(int(val))
        return str(val)
    except ValueError:
        return None


def _is_korean(text: str) -> bool:
    """Check if text contains Korean characters."""
    return bool(re.search(r"[\uac00-\ud7af\u3130-\u318f]", text))


def _is_english(text: str) -> bool:
    """Check if text contains English alphabetic characters."""
    return bool(re.search(r"[a-zA-Z]", text))


def _clean_label(text: str) -> str:
    """Clean a label for matching: strip whitespace, numbering prefixes."""
    t = text.strip()
    # Remove leading numbering like "(1)", "①", "1.", "1)"
    t = re.sub(r"^[\d\.\)\(①②③④⑤⑥⑦⑧⑨⑩\s]+", "", t).strip()
    return t


def _get_row_label(row: TableRow) -> str:
    """Extract the text label from the first non-empty cell in a row."""
    for cell in row.cells:
        text = cell.text.strip()
        if text and _extract_number(text) is None:
            return text
    return ""


def _get_row_numbers(row: TableRow) -> list[str]:
    """Extract all numeric values from a row, preserving order."""
    nums = []
    for cell in row.cells:
        n = _extract_number(cell.text)
        if n is not None:
            nums.append(n)
    return nums


# ──────────────────────────────────────────────
# Glossary building from table value matching
# ──────────────────────────────────────────────

def _match_tables_by_values(
    ko_tables: list[TableData],
    en_tables: list[TableData],
) -> dict[str, str]:
    """
    Match Korean and English tables by finding rows with identical numeric values.
    When numbers match, the labels form a glossary pair.

    Strategy:
    - For each Korean table, try to find an English table with overlapping values.
    - Match rows within those tables by their numeric signature.
    """
    glossary: dict[str, str] = {}

    # Build index: numeric signature -> (label, table) for English tables
    en_row_index: dict[tuple[str, ...], list[str]] = {}
    for tbl in en_tables:
        all_rows = tbl.headers + tbl.rows
        for row in all_rows:
            label = _get_row_label(row)
            nums = _get_row_numbers(row)
            if label and nums and _is_english(label):
                key = tuple(nums)
                en_row_index.setdefault(key, []).append(label)

    # Match Korean rows against English rows
    for tbl in ko_tables:
        all_rows = tbl.headers + tbl.rows
        for row in all_rows:
            ko_label = _get_row_label(row)
            nums = _get_row_numbers(row)
            if not ko_label or not nums or not _is_korean(ko_label):
                continue

            key = tuple(nums)
            if key in en_row_index:
                en_labels = en_row_index[key]
                if len(en_labels) == 1:
                    # Unique match — high confidence
                    glossary[_clean_label(ko_label)] = _clean_label(en_labels[0])
                elif len(en_labels) <= 3:
                    # Multiple matches — take first (usually correct for
                    # same-position matching)
                    glossary[_clean_label(ko_label)] = _clean_label(en_labels[0])

    return glossary


def _extract_all_tables(doc: ParsedDocument) -> list[TableData]:
    """Extract all tables from a ParsedDocument (both FS and notes)."""
    tables: list[TableData] = []

    # Financial statements
    for fs in doc.get_financial_statements():
        if fs.table:
            tables.append(fs.table)

    # Notes
    for note in doc.get_all_notes():
        for elem in note.elements:
            if elem.type == ElementType.TABLE and elem.table:
                tables.append(elem.table)

    return tables


# ──────────────────────────────────────────────
# Glossary building from note titles
# ──────────────────────────────────────────────

def _build_title_glossary(
    dsd_doc: ParsedDocument,
    docx_doc: ParsedDocument,
) -> dict[str, str]:
    """
    Build glossary from note title matching.
    Uses the known KO_EN_TITLE_MAP as seed, then augments with
    actual matched DSD/DOCX note titles.
    """
    glossary: dict[str, str] = {}

    # Seed from section_matcher's known mappings
    glossary.update(KO_EN_TITLE_MAP)

    # Match actual DSD Korean titles to DOCX English titles by note number
    dsd_notes = dsd_doc.get_all_notes()
    docx_notes = docx_doc.get_all_notes()

    docx_by_number: dict[str, Note] = {}
    for note in docx_notes:
        num = note.number.strip().rstrip(".")
        if num:
            docx_by_number[num] = note

    for dsd_note in dsd_notes:
        num = dsd_note.number.strip().rstrip(".")
        if num in docx_by_number:
            ko_title = _clean_label(dsd_note.title)
            en_title = _clean_label(docx_by_number[num].title)
            if ko_title and en_title and _is_korean(ko_title) and _is_english(en_title):
                glossary[ko_title] = en_title

    return glossary


# ──────────────────────────────────────────────
# Glossary building from table headers
# ──────────────────────────────────────────────

def _build_header_glossary(
    ko_tables: list[TableData],
    en_tables: list[TableData],
) -> dict[str, str]:
    """
    Build glossary from table titles and unit descriptions.
    """
    glossary: dict[str, str] = {}

    # Pair tables by index (rough alignment)
    for i, ko_tbl in enumerate(ko_tables):
        if i >= len(en_tables):
            break
        en_tbl = en_tables[i]

        # Table title
        if ko_tbl.title and en_tbl.title:
            ko_t = _clean_label(ko_tbl.title)
            en_t = _clean_label(en_tbl.title)
            if _is_korean(ko_t) and _is_english(en_t):
                glossary[ko_t] = en_t

        # Unit
        if ko_tbl.unit and en_tbl.unit:
            ko_u = ko_tbl.unit.strip()
            en_u = en_tbl.unit.strip()
            if ko_u and en_u:
                glossary[ko_u] = en_u

    return glossary


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

@dataclass
class Glossary:
    """A Korean→English translation glossary with provenance tracking."""
    entries: dict[str, str] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)  # ko -> source type

    def add(self, korean: str, english: str, source: str = "unknown"):
        """Add a glossary entry (will not overwrite existing)."""
        ko = korean.strip()
        en = english.strip()
        if ko and en and ko not in self.entries:
            self.entries[ko] = en
            self.sources[ko] = source

    def add_or_update(self, korean: str, english: str, source: str = "unknown"):
        """Add or update a glossary entry."""
        ko = korean.strip()
        en = english.strip()
        if ko and en:
            self.entries[ko] = en
            self.sources[ko] = source

    def lookup(self, korean: str) -> str | None:
        """Look up a Korean term. Returns English or None."""
        text = korean.strip()
        return self.entries.get(text)

    def lookup_partial(self, korean: str) -> str | None:
        """Find the longest matching glossary entry within the text."""
        text = korean.strip()
        if not text:
            return None

        if text in self.entries:
            return self.entries[text]

        best_match = None
        best_len = 0
        for ko, en in self.entries.items():
            if ko in text and len(ko) > best_len:
                best_match = en
                best_len = len(ko)

        return best_match

    def __len__(self) -> int:
        return len(self.entries)

    def __contains__(self, korean: str) -> bool:
        return korean.strip() in self.entries


def build_glossary(
    dsd_doc: ParsedDocument,
    docx_doc: ParsedDocument,
) -> Glossary:
    """
    Build a comprehensive Korean→English glossary from DSD and DOCX documents.

    Sources (in priority order):
    1. Value-matched table rows (highest confidence)
    2. Number-matched note titles
    3. Table header/unit matching
    4. Known note title mappings (from section_matcher)
    5. IFRS standard terms (lowest priority, broadest coverage)

    Args:
        dsd_doc: Parsed Korean DSD document
        docx_doc: Parsed English DOCX document

    Returns:
        Glossary with Korean→English entries and source provenance
    """
    glossary = Glossary()

    # 1. IFRS terms as base layer (lowest priority — added first so higher
    #    priority sources will overwrite via add_or_update)
    for ko, en in IFRS_TERMS.items():
        glossary.add(ko, en, source="ifrs")

    # 2. Known note title mappings
    for ko, en in KO_EN_TITLE_MAP.items():
        glossary.add_or_update(ko, en, source="title_map")

    # 3. Title matching from actual documents
    title_glossary = _build_title_glossary(dsd_doc, docx_doc)
    for ko, en in title_glossary.items():
        glossary.add_or_update(ko, en, source="title_match")

    # 4. Table header matching
    ko_tables = _extract_all_tables(dsd_doc)
    en_tables = _extract_all_tables(docx_doc)
    header_glossary = _build_header_glossary(ko_tables, en_tables)
    for ko, en in header_glossary.items():
        glossary.add_or_update(ko, en, source="header_match")

    # 5. Value-matched rows (highest confidence)
    value_glossary = _match_tables_by_values(ko_tables, en_tables)
    for ko, en in value_glossary.items():
        glossary.add_or_update(ko, en, source="value_match")

    return glossary

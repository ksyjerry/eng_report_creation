"""
section_matcher.py — Match DSD (Korean) notes to DOCX (English) notes.

Primary match: by note number (DSD note "5" matches DOCX note "5").
Secondary match: by title similarity using Korean→English lookup table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from ir_schema import Note


# ──────────────────────────────────────────────
# Korean → English note-title mapping
# ──────────────────────────────────────────────

KO_EN_TITLE_MAP: dict[str, str] = {
    # General / Basis
    "연결회사의 개요": "General Information",
    "회사의 개요": "General Information",
    "일반사항": "General Information",
    "일반 사항": "General Information",
    "재무제표 작성기준": "Basis of Preparation",
    "재무제표의 작성기준": "Basis of Preparation",
    "중요한 회계정책": "Significant Accounting Policies",
    "유의적인 회계정책": "Significant Accounting Policies",
    "중요한 회계추정 및 가정": "Significant Estimates and Assumptions",
    "중요한 회계적 판단": "Critical Accounting Judgments",

    # Assets
    "현금및현금성자산": "Cash and Cash Equivalents",
    "현금 및 현금성자산": "Cash and Cash Equivalents",
    "단기금융상품": "Short-term Financial Instruments",
    "공정가치 측정 금융자산": "Financial Assets at Fair Value",
    "당기손익-공정가치 측정 금융자산": "Financial Assets at FVTPL",
    "기타포괄손익-공정가치 측정 금융자산": "Financial Assets at FVOCI",
    "매출채권": "Trade Receivables",
    "매출채권 및 기타채권": "Trade and Other Receivables",
    "기타금융자산": "Other Financial Assets",
    "기타자산": "Other Assets",
    "기타비유동자산": "Other Non-current Assets",
    "재고자산": "Inventories",
    "선급금": "Advance Payments",
    "선급비용": "Prepaid Expenses",
    "관계기업 및 공동기업 투자": "Investments in Joint Ventures and Associates",
    "관계기업 투자": "Investments in Associates",
    "관계기업및공동기업투자": "Investments in Joint Ventures and Associates",
    "종속기업 투자": "Investments in Subsidiaries",
    "종속기업투자": "Investments in Subsidiaries",
    "유형자산": "Property and Equipment",
    "유형 자산": "Property and Equipment",
    "투자부동산": "Investment Property",
    "무형자산": "Intangible Assets",
    "무형 자산": "Intangible Assets",
    "사용권자산": "Right-of-use Assets",
    "리스": "Leases",

    # Liabilities
    "매입채무": "Trade Payables",
    "매입채무 및 기타채무": "Trade and Other Payables",
    "기타금융부채": "Other Financial Liabilities",
    "기타부채": "Other Liabilities",
    "차입금": "Borrowings",
    "차입금 및 사채": "Borrowings and Bonds",
    "사채": "Bonds Payable",
    "전환사채": "Convertible Bonds",
    "충당부채": "Provisions",
    "충당 부채": "Provisions",
    "확정급여": "Defined Benefit",
    "확정급여부채": "Defined Benefit Liability",
    "확정급여제도": "Defined Benefit Plans",
    "퇴직급여": "Employee Benefits",
    "종업원급여": "Employee Benefits",
    "이연수익": "Deferred Revenue",

    # Equity
    "자본금": "Share Capital",
    "자본 금": "Share Capital",
    "자본잉여금": "Share Premium",
    "기타자본": "Other Components of Equity",
    "기타자본구성요소": "Other Components of Equity",
    "기타자본항목": "Other Components of Equity",
    "이익잉여금": "Retained Earnings",
    "주식기준보상": "Share-based Payments",
    "주식기준보상거래": "Share-based Payment Transactions",
    "자기주식": "Treasury Shares",
    "배당금": "Dividends",

    # Income statement
    "수익": "Revenue",
    "매출": "Revenue",
    "매출액": "Revenue",
    "매출원가": "Cost of Sales",
    "판매비와관리비": "Selling and Administrative Expenses",
    "판매비와 관리비": "Selling and Administrative Expenses",
    "판관비": "Selling and Administrative Expenses",
    "기타수익": "Other Income",
    "기타비용": "Other Expenses",
    "기타수익과 기타비용": "Other Income and Expenses",
    "금융수익": "Finance Income",
    "금융비용": "Finance Costs",
    "금융수익과 금융비용": "Finance Income and Costs",
    "금융수익 및 금융비용": "Finance Income and Costs",
    "법인세": "Tax Expense",
    "법인세비용": "Income Tax Expense",
    "주당이익": "Earnings per Share",
    "주당순이익": "Earnings per Share",

    # Cash flow / Other
    "현금흐름": "Cash Flows",
    "현금흐름표": "Cash Flows",
    "현금흐름표 관련": "Cash Flows",
    "우발부채": "Contingencies",
    "우발부채와 약정사항": "Contingencies and Commitments",
    "우발부채 및 약정사항": "Contingencies and Commitments",
    "약정사항": "Commitments",
    "특수관계자": "Related Party",
    "특수관계자 거래": "Related Party Transactions",
    "특수관계자와의 거래": "Related Party Transactions",
    "금융위험관리": "Financial Risk Management",
    "금융위험 관리": "Financial Risk Management",
    "공정가치": "Fair Value",
    "금융상품": "Financial Instruments",
    "금융상품의 범주별 분류": "Categories of Financial Instruments",
    "영업부문": "Operating Segment",
    "부문 정보": "Segment Information",
    "부문정보": "Segment Information",
    "영업부문 정보": "Operating Segment Information",
    "사업결합": "Business Combinations",
    "보고기간후 사건": "Events after the Reporting Period",
    "보고기간 후 사건": "Events after the Reporting Period",
    "제정 및 개정 기준서": "New and Amended Standards",
}

# Build a reverse lookup (English → set of Korean titles)
_EN_TERMS: dict[str, list[str]] = {}
for _ko, _en in KO_EN_TITLE_MAP.items():
    _EN_TERMS.setdefault(_en.lower(), []).append(_ko)


# ──────────────────────────────────────────────
# Section Mapping result
# ──────────────────────────────────────────────

@dataclass
class SectionMapping:
    """Result of matching a DSD note to a DOCX note."""
    dsd_note: Note
    docx_note: Optional[Note]
    confidence: float = 0.0       # 0.0 to 1.0
    match_method: str = ""        # "number", "title", "number+title", "unmatched"


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _normalize_number(num: str) -> str:
    """Normalize a note number: strip dots, whitespace, leading zeros."""
    num = num.strip().rstrip(".")
    # Handle "2.1" style sub-notes → keep as-is
    if "." in num:
        return num
    # Remove leading zeros for top-level
    return num.lstrip("0") or "0"


def _translate_title(ko_title: str) -> str:
    """Translate a Korean note title to English using the lookup table."""
    title = ko_title.strip()
    # Direct lookup
    if title in KO_EN_TITLE_MAP:
        return KO_EN_TITLE_MAP[title]
    # Try after stripping numbers/periods/whitespace prefix
    cleaned = re.sub(r"^[\d.\s\-–—]+", "", title).strip()
    if cleaned in KO_EN_TITLE_MAP:
        return KO_EN_TITLE_MAP[cleaned]
    return ""


def _tokenize(text: str) -> set[str]:
    """Tokenize to lowercase words."""
    return set(re.findall(r"[a-zA-Z]+", text.lower()))


def _title_similarity(ko_title: str, en_title: str) -> float:
    """
    Compute similarity between a Korean title and an English title.
    Returns 0.0–1.0.

    Strategy:
    1. Translate Korean title via lookup table.
    2. If translation found, compare with English title token overlap.
    3. If no direct translation, try substring matching against all known
       English equivalents.
    """
    if not ko_title or not en_title:
        return 0.0

    translated = _translate_title(ko_title)
    en_tokens = _tokenize(en_title)

    if not en_tokens:
        return 0.0

    if translated:
        trans_tokens = _tokenize(translated)
        if not trans_tokens:
            return 0.0
        overlap = len(trans_tokens & en_tokens)
        union = len(trans_tokens | en_tokens)
        return overlap / union if union > 0 else 0.0

    # Fallback: try each known English term and see if any is a reasonable
    # substring match of the docx title
    en_lower = en_title.lower()
    best = 0.0
    for eng_term in _EN_TERMS:
        # Check if the English term appears as substring
        if eng_term in en_lower:
            # Check if any of the Korean variants is a substring of the Korean title
            ko_clean = re.sub(r"^[\d.\s\-–—]+", "", ko_title).strip()
            for ko_variant in _EN_TERMS[eng_term]:
                if ko_variant in ko_clean or ko_clean in ko_variant:
                    score = len(eng_term) / max(len(en_lower), 1)
                    best = max(best, score)
    return best


# ──────────────────────────────────────────────
# Main matching
# ──────────────────────────────────────────────

def match_sections(
    dsd_notes: list[Note],
    docx_notes: list[Note],
) -> list[SectionMapping]:
    """
    Match DSD notes to DOCX notes using rule-based matching.

    Two-pass approach:
      Pass 1: Number match + title confirmation. If the number-matched DOCX note
              has good title similarity (>= 0.3), accept. Otherwise, check if a
              *different* DOCX note has much better title similarity — if so,
              defer to pass 2.
      Pass 2: Title-only matching for deferred and remaining notes.

    Returns one SectionMapping per DSD note.
    """
    # Build lookup by normalized number for DOCX notes
    docx_by_number: dict[str, Note] = {}
    for note in docx_notes:
        norm = _normalize_number(note.number)
        if norm and norm != "0":
            docx_by_number[norm] = note

    # Track which DOCX notes have been claimed
    claimed_docx: set[str] = set()  # by note.id

    mappings: list[SectionMapping] = []
    deferred_dsd: list[Note] = []   # DSD notes to handle in pass 2

    # === Pass 1: number + title confirmation ===
    for dsd_note in dsd_notes:
        dsd_num = _normalize_number(dsd_note.number)

        if dsd_num in docx_by_number and dsd_num != "0":
            docx_note = docx_by_number[dsd_num]
            sim = _title_similarity(dsd_note.title, docx_note.title)

            if sim >= 0.3:
                # Good number+title match — accept
                conf = 0.8 + 0.2 * sim
                mappings.append(SectionMapping(
                    dsd_note=dsd_note,
                    docx_note=docx_note,
                    confidence=conf,
                    match_method="number+title",
                ))
                claimed_docx.add(docx_note.id)
                continue

            # Number matches but title is poor — check if a different DSD note
            # might be a better match for this DOCX note by title
            best_other_dsd_sim = 0.0
            for other_dsd in dsd_notes:
                if other_dsd is dsd_note:
                    continue
                other_sim = _title_similarity(other_dsd.title, docx_note.title)
                best_other_dsd_sim = max(best_other_dsd_sim, other_sim)

            if best_other_dsd_sim >= 0.4:
                # Another DSD note has a better claim on this DOCX note — defer
                deferred_dsd.append(dsd_note)
                continue

            # Also check if a better DOCX match exists for this DSD note
            best_title_sim = 0.0
            for other in docx_notes:
                if other.id == docx_note.id:
                    continue
                other_sim = _title_similarity(dsd_note.title, other.title)
                best_title_sim = max(best_title_sim, other_sim)

            if best_title_sim >= 0.5:
                # A much better DOCX title match exists — defer to pass 2
                deferred_dsd.append(dsd_note)
                continue

            # No better option — accept the number match
            conf = 0.8 + 0.2 * sim
            mappings.append(SectionMapping(
                dsd_note=dsd_note,
                docx_note=docx_note,
                confidence=conf,
                match_method="number",
            ))
            claimed_docx.add(docx_note.id)
        else:
            # No number match available
            deferred_dsd.append(dsd_note)

    # === Pass 2: title-only matching for deferred notes ===
    for dsd_note in deferred_dsd:
        best_match: Optional[Note] = None
        best_sim = 0.0
        for docx_note in docx_notes:
            if docx_note.id in claimed_docx:
                continue
            sim = _title_similarity(dsd_note.title, docx_note.title)
            if sim > best_sim:
                best_sim = sim
                best_match = docx_note

        if best_match and best_sim >= 0.4:
            mappings.append(SectionMapping(
                dsd_note=dsd_note,
                docx_note=best_match,
                confidence=best_sim,
                match_method="title",
            ))
            claimed_docx.add(best_match.id)
        else:
            # No match — this is a new note in the DSD
            mappings.append(SectionMapping(
                dsd_note=dsd_note,
                docx_note=None,
                confidence=0.0,
                match_method="unmatched",
            ))

    return mappings


def find_unmatched_docx_notes(
    mappings: list[SectionMapping],
    docx_notes: list[Note],
) -> list[Note]:
    """Return DOCX notes that were not matched to any DSD note (candidates for deletion)."""
    matched_ids = {
        m.docx_note.id for m in mappings
        if m.docx_note is not None
    }
    return [n for n in docx_notes if n.id not in matched_ids]

"""
DSD Financial Statement parser.
Extracts the 4 main financial statement tables from SECTION-1 blocks.
Identifies statement type from table content and headers.
"""

import re
from lxml import etree

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ir_schema import FinancialStatement, StatementType, TableData, Section
from utils.xml_helpers import get_attr
from skills.parse_dsd.dsd_table_parser import parse_table, _get_cell_text


# Keywords to identify financial statement type from first few rows or title context
_FS_TYPE_PATTERNS = {
    StatementType.BALANCE_SHEET: [
        r'자\s*산', r'부\s*채', r'재무상태표', r'유동자산', r'비유동자산',
    ],
    StatementType.INCOME_STATEMENT: [
        r'매\s*출\s*액', r'매출원가', r'영업이익', r'포괄손익', r'손익계산서',
        r'당기순이익', r'영업수익',
    ],
    StatementType.CHANGES_IN_EQUITY: [
        r'자본금', r'자본잉여금', r'이익잉여금', r'자본변동',
        r'전기초\s*잔액', r'당기초\s*잔액', r'기초\s*잔액',
    ],
    StatementType.CASH_FLOW: [
        r'영업활동.*현금', r'투자활동.*현금', r'재무활동.*현금',
        r'현금흐름', r'현금및현금성자산',
    ],
}


def _detect_statement_type(table_data: TableData, context_text: str = "") -> StatementType:
    """
    Detect financial statement type from table content.
    Examines the first ~10 rows and any context text before the table.
    """
    # Collect text from first rows and headers
    sample_texts = []
    for row in table_data.headers:
        for cell in row.cells:
            if cell.text:
                sample_texts.append(cell.text)
    for row in table_data.rows[:15]:
        for cell in row.cells:
            if cell.text:
                sample_texts.append(cell.text)

    combined = " ".join(sample_texts) + " " + context_text

    # Score each type
    scores = {}
    for st, patterns in _FS_TYPE_PATTERNS.items():
        score = 0
        for pat in patterns:
            if re.search(pat, combined):
                score += 1
        scores[st] = score

    # CE detection: check if headers contain multiple equity-like columns
    header_text = " ".join(
        c.text for row in table_data.headers for c in row.cells if c.text
    )
    if re.search(r'자본금.*자본잉여금|자본잉여금.*이익잉여금', header_text):
        scores[StatementType.CHANGES_IN_EQUITY] += 3

    # Return the type with highest score, defaulting to BS
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return StatementType.BALANCE_SHEET
    return best


def _extract_unit(section_elem, table_elem) -> str:
    """Extract unit string (e.g., '(단위: 천원)') from tables preceding the FS table."""
    # Look for a BORDER=0 table just before the BORDER=1 table
    # that contains unit information
    prev = table_elem.getprevious()
    while prev is not None:
        if prev.tag == 'TABLE':
            text = etree.tostring(prev, method="text", encoding="unicode") or ""
            m = re.search(r'\(단위\s*:\s*[^)]+\)', text)
            if m:
                return m.group(0)
        elif prev.tag == 'P':
            text = (prev.text or "") + "".join(
                etree.tostring(c, method="text", encoding="unicode") or ""
                for c in prev
            )
            m = re.search(r'\(단위\s*:\s*[^)]+\)', text)
            if m:
                return m.group(0)
        prev = prev.getprevious()
    return ""


def _extract_title_context(section_elem, table_elem) -> str:
    """
    Extract context text from elements between section start and this table.
    Used for FS type detection.
    """
    texts = []
    prev = table_elem.getprevious()
    count = 0
    while prev is not None and count < 10:
        text = etree.tostring(prev, method="text", encoding="unicode") or ""
        text = text.replace("&cr;", " ").strip()
        if text:
            texts.append(text)
        prev = prev.getprevious()
        count += 1
    return " ".join(reversed(texts))


def _extract_periods_from_section(section_elem) -> list[str]:
    """
    Extract period info from TU elements with AUNIT=PERIODFROM2/PERIODTO2
    or from table headers.
    """
    periods = []

    # Method 1: TU elements with AUNIT attributes
    for tu in section_elem.iter('TU'):
        aunit = get_attr(tu, 'AUNIT', '')
        aunitvalue = get_attr(tu, 'AUNITVALUE', '')
        if 'PERIODTO' in aunit and aunitvalue:
            # Format: YYYYMMDD -> YYYY.MM.DD
            if len(aunitvalue) == 8:
                formatted = f"{aunitvalue[:4]}.{aunitvalue[4:6]}.{aunitvalue[6:8]}"
                if formatted not in periods:
                    periods.append(formatted)

    # Method 2: Parse from header text patterns like "제21(당) 기말" / "2025년 12월 31일"
    if not periods:
        for table in section_elem.iter('TABLE'):
            if get_attr(table, 'BORDER', '0') == '0':
                text = etree.tostring(table, method="text", encoding="unicode") or ""
                # Find date patterns
                for m in re.finditer(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', text):
                    y, mo, d = m.groups()
                    formatted = f"{y}.{mo.zfill(2)}.{d.zfill(2)}"
                    if formatted not in periods:
                        periods.append(formatted)

    return periods


def parse_financial_statements(section_elem, section_index: int = 0) -> Section:
    """
    Parse financial statements from a SECTION-1 element.
    Identifies BORDER=1 tables as main FS tables.

    Args:
        section_elem: lxml Element for SECTION-1
        section_index: index of this section in the document

    Returns:
        Section with financial_statements populated
    """
    section = Section(
        section_type="financial_statement",
        section_index=section_index,
    )

    # Get section title
    title_elem = section_elem.find('TITLE')
    if title_elem is not None:
        title_text = etree.tostring(title_elem, method="text", encoding="unicode") or ""
        section.title = re.sub(r'\s+', ' ', title_text).strip()

    # Skip non-FS sections (audit report, internal control, etc.)
    skip_keywords = ['감사인', '감사보고서', '내부회계', '외부감사']
    if any(kw in section.title for kw in skip_keywords):
        section.section_type = "other"
        return section

    # Extract periods from section
    periods = _extract_periods_from_section(section_elem)

    # Find all BORDER=1 tables directly under this SECTION-1
    # (not in nested SECTION-2)
    fs_tables = []
    for table in section_elem.iterchildren():
        _collect_border1_tables(table, fs_tables, skip_section2=True)

    # Also search in TABLE-GROUP elements
    for tg in section_elem.iter('TABLE-GROUP'):
        for table in tg.iter('TABLE'):
            if get_attr(table, 'BORDER', '0') == '1':
                if table not in [t for t, _ in fs_tables]:
                    fs_tables.append((table, ""))

    # Parse each BORDER=1 table as a financial statement
    seen_types = set()
    for idx, (table_elem, _ctx) in enumerate(fs_tables):
        table_data = parse_table(table_elem)
        context = _extract_title_context(section_elem, table_elem)
        unit = _extract_unit(section_elem, table_elem)
        table_data.unit = unit
        table_data.source_index = idx

        stmt_type = _detect_statement_type(table_data, context)

        # Avoid duplicate types - if we already have a BS, try harder
        if stmt_type in seen_types:
            # Try next best type or use index-based heuristic
            fs_order = [
                StatementType.BALANCE_SHEET,
                StatementType.INCOME_STATEMENT,
                StatementType.CHANGES_IN_EQUITY,
                StatementType.CASH_FLOW,
            ]
            for candidate in fs_order:
                if candidate not in seen_types:
                    stmt_type = candidate
                    break

        seen_types.add(stmt_type)

        # Build title from statement type
        type_titles = {
            StatementType.BALANCE_SHEET: "재무상태표",
            StatementType.INCOME_STATEMENT: "포괄손익계산서",
            StatementType.CHANGES_IN_EQUITY: "자본변동표",
            StatementType.CASH_FLOW: "현금흐름표",
        }

        fs = FinancialStatement(
            id=f"fs_{section_index}_{idx}",
            statement_type=stmt_type,
            title=type_titles.get(stmt_type, ""),
            periods=periods,
            table=table_data,
        )
        section.financial_statements.append(fs)

    return section


def _collect_border1_tables(elem, result: list, skip_section2: bool = True):
    """
    Recursively collect BORDER=1 TABLE elements, optionally skipping SECTION-2.
    Each result item is (table_elem, context_text).
    """
    if skip_section2 and elem.tag == 'SECTION-2':
        return

    if elem.tag == 'TABLE' and get_attr(elem, 'BORDER', '0') == '1':
        # Check if this looks like a real FS table (has THEAD or enough rows)
        thead = elem.find('.//THEAD')
        tbody = elem.find('.//TBODY')
        row_count = len(elem.findall('.//TR'))
        # Only include tables with headers and multiple rows (FS tables are big)
        if thead is not None and row_count >= 5:
            result.append((elem, ""))
        return

    for child in elem:
        _collect_border1_tables(child, result, skip_section2)

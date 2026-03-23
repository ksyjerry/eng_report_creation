"""
parse_dsd skill - Parse Korean financial statement DSD files.

DSD files are ZIP archives (DART XML format) containing:
  - contents.xml: The main document with financial statements and notes
  - meta.xml: Document metadata

Entry point: parse_dsd(file_path) -> ParsedDocument
"""

import os
import re
import shutil
from lxml import etree

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ir_schema import (
    ParsedDocument, DocumentMeta, DocType, Section,
)
from utils.xml_helpers import get_attr
from skills.parse_dsd.dsd_extractor import extract_dsd
from skills.parse_dsd.dsd_fs_parser import parse_financial_statements
from skills.parse_dsd.dsd_note_parser import parse_notes


def _detect_doc_type(doc_name: str) -> DocType:
    """
    Detect document type from DOCUMENT-NAME text.
    '연결' -> CONSOLIDATED, '별도' -> SEPARATE.
    Default to SEPARATE if neither found.
    """
    if '연결' in doc_name:
        return DocType.CONSOLIDATED
    elif '별도' in doc_name:
        return DocType.SEPARATE
    # Heuristic: if it says '감사보고서' without '연결', it's likely separate
    return DocType.SEPARATE


def _extract_company_name(root) -> str:
    """Extract company name from COMPANY-NAME element or body content."""
    # Try COMPANY-NAME element
    cn = root.find('.//COMPANY-NAME')
    if cn is not None:
        text = (cn.text or "").strip()
        if text:
            return text

    # Try to find company name from cover/body text
    # Look for patterns like "주식회사 XXX" or "XXX 주식회사"
    for elem in root.iter('TD'):
        text = (elem.text or "").strip()
        usermark = get_attr(elem, 'USERMARK', '')
        if 'F-14' in usermark or 'BT14' in usermark:
            # Large bold text is likely company name
            if text and ('주식회사' in text or '㈜' in text or len(text) > 3):
                # Clean up
                text = re.sub(r'\s+', ' ', text).strip()
                return text

    # Fallback: search in P elements
    for p in root.iter('P'):
        text = (p.text or "").strip()
        if '주식회사' in text and len(text) < 50:
            return re.sub(r'\s+', ' ', text).strip()

    return ""


def _extract_periods(root) -> tuple[str, str]:
    """
    Extract current and prior period from TU elements.
    Returns (current_period, prior_period) as year strings.
    """
    period_to_dates = []

    for tu in root.iter('TU'):
        aunit = get_attr(tu, 'AUNIT', '')
        aunitvalue = get_attr(tu, 'AUNITVALUE', '')
        if 'PERIODTO' in aunit and aunitvalue and len(aunitvalue) >= 4:
            year = aunitvalue[:4]
            if year not in period_to_dates:
                period_to_dates.append(year)

    if len(period_to_dates) >= 2:
        # Sort descending - current period first
        period_to_dates.sort(reverse=True)
        return period_to_dates[0], period_to_dates[1]
    elif len(period_to_dates) == 1:
        current = period_to_dates[0]
        prior = str(int(current) - 1)
        return current, prior

    return "", ""


def parse_dsd(file_path: str) -> ParsedDocument:
    """
    Parse a DSD file into a ParsedDocument IR structure.

    Args:
        file_path: Path to the .dsd file

    Returns:
        ParsedDocument with metadata, financial statements, and notes
    """
    # Extract ZIP and parse XML
    extracted = extract_dsd(file_path)
    temp_dir = extracted['temp_dir']

    try:
        tree = extracted['contents_tree']
        root = tree.getroot()

        # === Extract metadata ===
        doc_header = root.find('.//DOCUMENT-HEADER')
        doc_name_elem = root.find('.//DOCUMENT-NAME')
        doc_name = ""
        if doc_name_elem is not None:
            doc_name = (doc_name_elem.text or "").strip()

        doc_type = _detect_doc_type(doc_name)
        company = _extract_company_name(root)
        period_current, period_prior = _extract_periods(root)

        meta = DocumentMeta(
            company=company,
            period_current=period_current,
            period_prior=period_prior,
            doc_type=doc_type,
            source_format="dsd",
        )

        # === Parse sections ===
        sections: list[Section] = []
        section_counter = 0

        body = root.find('.//BODY')
        if body is None:
            body = root  # fallback

        # Find all SECTION-1 and SECTION-2 elements
        for elem in body.iter():
            if elem.tag == 'SECTION-1':
                section = parse_financial_statements(elem, section_counter)
                sections.append(section)
                section_counter += 1

                # Also look for SECTION-2 nested inside SECTION-1
                for s2 in elem.iter('SECTION-2'):
                    note_section = parse_notes(s2, section_counter)
                    sections.append(note_section)
                    section_counter += 1

            elif elem.tag == 'SECTION-2':
                # Top-level SECTION-2 (not nested in SECTION-1)
                # Check if it's already been processed via SECTION-1 iteration
                parent = elem.getparent()
                if parent is not None and parent.tag == 'SECTION-1':
                    continue  # Already processed above
                note_section = parse_notes(elem, section_counter)
                sections.append(note_section)
                section_counter += 1

        doc = ParsedDocument(
            meta=meta,
            sections=sections,
        )

        return doc

    finally:
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)

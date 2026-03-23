"""
translator.py — Translation engine for Korean→English financial statements.

Uses a glossary-first approach:
1. Exact glossary match
2. IFRS standard term match (exact or partial)
3. PwC GenAI Gateway fallback (optional — requires API key)

If no API key is provided, untranslated items are marked with
"[NEEDS_TRANSLATION: original Korean text]".
"""

from __future__ import annotations

import re
import logging
from typing import Optional

from skills.translate.glossary_builder import Glossary
from skills.translate.ifrs_terms import lookup_ifrs_term, lookup_ifrs_partial
from skills.translate.prompts import (
    SYSTEM_PROMPT,
    translate_paragraph_prompt,
    translate_table_labels_prompt,
    translate_note_title_prompt,
    format_glossary_context,
)


logger = logging.getLogger(__name__)

# Regex patterns
_KOREAN_RE = re.compile(r"[\uac00-\ud7af\u3130-\u318f]")
_NUMBER_RE = re.compile(
    r"^[\s\(\)\-–—,.\d%]+$"  # purely numeric / formatting
)


def _contains_korean(text: str) -> bool:
    """Check if text contains any Korean characters."""
    return bool(_KOREAN_RE.search(text))


def _is_purely_numeric(text: str) -> bool:
    """Check if text is purely numbers/formatting (no translation needed)."""
    return bool(_NUMBER_RE.match(text.strip())) if text.strip() else True


# ──────────────────────────────────────────────
# PwC GenAI Gateway wrapper
# ──────────────────────────────────────────────

def _call_llm_api(
    user_prompt: str,
    api_key: str,
    base_url: str = "",
    model: str = "",
    max_tokens: int = 4096,
) -> str:
    """
    Call the PwC GenAI Gateway for translation.

    Uses the sync client from utils.genai_client to avoid async complexity
    in the translation pipeline.

    Returns the response text, or empty string on failure.
    """
    try:
        from utils.genai_client import GenAIClient
        from config import GENAI_BASE_URL, GENAI_MODEL

        client = GenAIClient(
            base_url=base_url or GENAI_BASE_URL,
            api_key=api_key,
            model=model or GENAI_MODEL,
        )
        return client.complete_sync(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.warning(f"GenAI Gateway call failed: {e}")
        return ""


# ──────────────────────────────────────────────
# Single-label translation
# ──────────────────────────────────────────────

def translate_label(
    korean: str,
    glossary: Glossary,
    api_key: str | None = None,
    table_context: str = "",
) -> str:
    """
    Translate a single Korean label (table cell, row label, etc.).

    Priority:
    1. Exact glossary match
    2. Exact IFRS term match
    3. Partial glossary match
    4. Partial IFRS term match
    5. PwC GenAI Gateway (if key provided)
    6. [NEEDS_TRANSLATION: ...] marker
    """
    text = korean.strip()
    if not text:
        return ""

    # Skip if no Korean characters (already English, or purely numeric)
    if not _contains_korean(text):
        return text

    # Skip purely numeric
    if _is_purely_numeric(text):
        return text

    # 1. Exact glossary match
    result = glossary.lookup(text)
    if result:
        return result

    # 2. Exact IFRS term match
    result = lookup_ifrs_term(text)
    if result:
        return result

    # 3. Partial glossary match
    result = glossary.lookup_partial(text)
    if result:
        return result

    # 4. Partial IFRS match
    result = lookup_ifrs_partial(text)
    if result:
        return result

    # 5. PwC GenAI Gateway
    if api_key:
        glossary_ctx = format_glossary_context(glossary.entries, max_entries=30)
        prompt = translate_table_labels_prompt(
            labels=[text],
            glossary_context=glossary_ctx,
            table_context=table_context,
        )
        api_result = _call_llm_api(prompt, api_key)
        if api_result:
            # Parse the numbered response: "1. Translation"
            for line in api_result.splitlines():
                line = line.strip()
                match = re.match(r"^\d+\.\s*(.+)$", line)
                if match:
                    return match.group(1).strip()
                # If no numbering, return the whole line
                if line:
                    return line

    # 6. Mark as needing translation
    return f"[NEEDS_TRANSLATION: {text}]"


# ──────────────────────────────────────────────
# Batch label translation
# ──────────────────────────────────────────────

def translate_labels_batch(
    labels: list[str],
    glossary: Glossary,
    api_key: str | None = None,
    table_context: str = "",
) -> list[str]:
    """
    Translate a batch of Korean labels efficiently.

    First resolves all labels that can be handled by glossary/IFRS.
    Then sends remaining unresolved labels to the API in a single batch call.
    """
    results: list[str | None] = [None] * len(labels)
    unresolved_indices: list[int] = []
    unresolved_labels: list[str] = []

    # First pass: glossary/IFRS resolution
    for i, label in enumerate(labels):
        text = label.strip()
        if not text or not _contains_korean(text) or _is_purely_numeric(text):
            results[i] = text
            continue

        # Try glossary
        result = glossary.lookup(text)
        if result:
            results[i] = result
            continue

        # Try IFRS exact
        result = lookup_ifrs_term(text)
        if result:
            results[i] = result
            continue

        # Try partial matches
        result = glossary.lookup_partial(text)
        if result:
            results[i] = result
            continue

        result = lookup_ifrs_partial(text)
        if result:
            results[i] = result
            continue

        # Unresolved
        unresolved_indices.append(i)
        unresolved_labels.append(text)

    # Second pass: batch API call for unresolved labels
    if unresolved_labels and api_key:
        glossary_ctx = format_glossary_context(glossary.entries, max_entries=30)
        prompt = translate_table_labels_prompt(
            labels=unresolved_labels,
            glossary_context=glossary_ctx,
            table_context=table_context,
        )
        api_result = _call_llm_api(prompt, api_key)
        if api_result:
            translations = _parse_numbered_list(api_result, len(unresolved_labels))
            for idx, trans in zip(unresolved_indices, translations):
                results[idx] = trans

    # Fill remaining with NEEDS_TRANSLATION markers
    for i in range(len(results)):
        if results[i] is None:
            results[i] = f"[NEEDS_TRANSLATION: {labels[i].strip()}]"

    return results  # type: ignore[return-value]


def _parse_numbered_list(text: str, expected_count: int) -> list[str]:
    """Parse a numbered list response from the API."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    results: list[str] = []

    for line in lines:
        # Try "N. translation" format
        match = re.match(r"^\d+\.\s*(.+)$", line)
        if match:
            results.append(match.group(1).strip())
        elif line and not line.startswith("#"):
            results.append(line)

    # Pad or truncate to expected count
    while len(results) < expected_count:
        results.append("")
    return results[:expected_count]


# ──────────────────────────────────────────────
# Paragraph translation
# ──────────────────────────────────────────────

def translate_paragraph(
    korean_text: str,
    glossary: Glossary,
    api_key: str | None = None,
    surrounding_english: str = "",
) -> str:
    """
    Translate a Korean paragraph. Always uses API if available (paragraphs
    require contextual translation), but provides glossary for consistency.
    """
    text = korean_text.strip()
    if not text:
        return ""

    if not _contains_korean(text):
        return text

    # Short single-term text: try glossary/IFRS first
    if len(text) < 40 and "\n" not in text:
        result = glossary.lookup(text)
        if result:
            return result
        result = lookup_ifrs_term(text)
        if result:
            return result

    # For paragraphs, prefer API
    if api_key:
        glossary_ctx = format_glossary_context(glossary.entries, max_entries=40)
        prompt = translate_paragraph_prompt(
            korean_text=text,
            glossary_context=glossary_ctx,
            surrounding_english=surrounding_english,
        )
        result = _call_llm_api(prompt, api_key)
        if result:
            return result

    # Fallback: try partial glossary only if the match covers most of the text
    result = glossary.lookup_partial(text)
    if result:
        matching_key = None
        for ko in glossary.entries:
            if ko in text and (matching_key is None or len(ko) > len(matching_key)):
                matching_key = ko
        if matching_key and len(matching_key) >= len(text) * 0.7:
            return result

    return f"[NEEDS_TRANSLATION: {text}]"


# ──────────────────────────────────────────────
# Note title translation
# ──────────────────────────────────────────────

def translate_note_title(
    korean_title: str,
    glossary: Glossary,
    note_number: str = "",
    api_key: str | None = None,
) -> str:
    """
    Translate a note section title.
    """
    text = korean_title.strip()
    if not text:
        return ""

    if not _contains_korean(text):
        return text

    # Clean: remove leading number/dot prefix for lookup
    cleaned = re.sub(r"^[\d.\s\-–—]+", "", text).strip()

    # 1. Glossary exact match
    result = glossary.lookup(cleaned) or glossary.lookup(text)
    if result:
        return result

    # 2. IFRS exact match
    result = lookup_ifrs_term(cleaned) or lookup_ifrs_term(text)
    if result:
        return result

    # 3. Partial matches
    result = glossary.lookup_partial(cleaned)
    if result:
        return result

    # 4. PwC GenAI Gateway
    if api_key:
        glossary_ctx = format_glossary_context(glossary.entries, max_entries=30)
        prompt = translate_note_title_prompt(
            korean_title=cleaned,
            note_number=note_number,
            glossary_context=glossary_ctx,
        )
        result = _call_llm_api(prompt, api_key)
        if result:
            # Remove any quotes the API might add
            result = result.strip('"').strip("'")
            return result

    return f"[NEEDS_TRANSLATION: {text}]"

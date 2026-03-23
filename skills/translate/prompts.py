"""
prompts.py — LLM prompt templates for financial statement translation.

All prompts emphasize:
- IFRS terminology consistency
- Formal financial English
- Matching the existing DOCX document style
"""

from __future__ import annotations


# ──────────────────────────────────────────────
# System prompt (shared across all translation calls)
# ──────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a professional financial translator specializing in Korean-to-English \
translation of IFRS financial statements and audit reports. Your translations \
must use standard IFRS English terminology consistently.

Rules:
1. Use formal financial English appropriate for published annual reports.
2. Preserve all numbers, dates, company names, and proper nouns exactly as-is.
3. Use IFRS-standard terminology (e.g., "Property, plant and equipment" not \
"Fixed assets"; "Revenue" not "Sales income").
4. Keep the same level of formality and tone as existing English text in the document.
5. Do NOT add explanations, comments, or translator notes.
6. Preserve paragraph structure and line breaks.
7. Korean won amounts should keep their original formatting.
8. For parenthesized Korean annotations, translate the content inside parentheses.
"""


# ──────────────────────────────────────────────
# Paragraph translation
# ──────────────────────────────────────────────

def translate_paragraph_prompt(
    korean_text: str,
    glossary_context: str = "",
    surrounding_english: str = "",
) -> str:
    """
    Build a user prompt for translating a paragraph of Korean financial text.

    Args:
        korean_text: The Korean paragraph to translate.
        glossary_context: Formatted glossary entries for context.
        surrounding_english: Nearby English text for style matching.
    """
    parts = [
        "Translate the following Korean financial statement paragraph into English."
    ]

    if glossary_context:
        parts.append(
            f"\nUse these established glossary terms for consistency:\n{glossary_context}"
        )

    if surrounding_english:
        parts.append(
            f"\nMatch the style and tone of this existing English text from the same document:\n"
            f'"""\n{surrounding_english}\n"""'
        )

    parts.append(
        f"\nKorean text to translate:\n"
        f'"""\n{korean_text}\n"""'
    )

    parts.append(
        "\nProvide ONLY the English translation, with no additional commentary."
    )

    return "\n".join(parts)


# ──────────────────────────────────────────────
# Table label translation
# ──────────────────────────────────────────────

def translate_table_labels_prompt(
    labels: list[str],
    glossary_context: str = "",
    table_context: str = "",
) -> str:
    """
    Build a user prompt for translating table row/column labels.

    Args:
        labels: List of Korean labels to translate.
        glossary_context: Formatted glossary entries for context.
        table_context: Description of the table for context (e.g., title, note number).
    """
    labels_text = "\n".join(f"- {label}" for label in labels)

    parts = [
        "Translate the following Korean financial table labels into English.",
        "These are row or column labels from an IFRS financial statement table.",
    ]

    if table_context:
        parts.append(f"\nTable context: {table_context}")

    if glossary_context:
        parts.append(
            f"\nUse these established glossary terms for consistency:\n{glossary_context}"
        )

    parts.append(
        f"\nKorean labels to translate:\n{labels_text}"
    )

    parts.append(
        "\nProvide the translations as a numbered list, one per line, in the same order. "
        "Format: `N. English translation` (where N is the line number starting from 1). "
        "Provide ONLY the translations, no commentary."
    )

    return "\n".join(parts)


# ──────────────────────────────────────────────
# Note title translation
# ──────────────────────────────────────────────

def translate_note_title_prompt(
    korean_title: str,
    note_number: str = "",
    glossary_context: str = "",
) -> str:
    """
    Build a user prompt for translating a note section title.

    Args:
        korean_title: The Korean note title to translate.
        note_number: The note number (e.g., "5", "12.1").
        glossary_context: Formatted glossary entries for context.
    """
    parts = [
        "Translate the following Korean financial statement note title into English.",
        "Use standard IFRS note title formatting (title case, concise).",
    ]

    if note_number:
        parts.append(f"This is Note {note_number}.")

    if glossary_context:
        parts.append(
            f"\nEstablished glossary terms:\n{glossary_context}"
        )

    parts.append(
        f'\nKorean title: "{korean_title}"'
    )

    parts.append(
        "\nProvide ONLY the English title, with no additional commentary."
    )

    return "\n".join(parts)


# ──────────────────────────────────────────────
# Glossary formatting helper
# ──────────────────────────────────────────────

def format_glossary_context(
    glossary_entries: dict[str, str],
    max_entries: int = 50,
) -> str:
    """
    Format glossary entries into a string for prompt context.

    Args:
        glossary_entries: Korean→English glossary dict.
        max_entries: Maximum entries to include (to stay within context limits).
    """
    if not glossary_entries:
        return ""

    items = list(glossary_entries.items())[:max_entries]
    lines = [f"  {ko} → {en}" for ko, en in items]
    return "\n".join(lines)

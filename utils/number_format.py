"""
Number formatting utilities for financial statements.
Handles Korean won formatting, negative numbers in parentheses, etc.
"""

import re


def parse_korean_number(text: str) -> int | float | None:
    """
    Parse a Korean-formatted number string into a numeric value.
    Handles: commas, parentheses (negative), dashes (zero), won symbol.

    Examples:
        "1,234,567" -> 1234567
        "(1,234,567)" -> -1234567
        "-" -> 0
        "" -> None
        "\\  2,938,755" -> 2938755
    """
    if not text:
        return None

    cleaned = text.strip()
    # Remove won symbol and whitespace
    cleaned = cleaned.replace("\\", "").replace("\u20a9", "").strip()

    if not cleaned or cleaned == "-" or cleaned == "—" or cleaned == "–":
        return 0

    is_negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        is_negative = True
        cleaned = cleaned[1:-1].strip()
    elif cleaned.startswith("-"):
        is_negative = True
        cleaned = cleaned[1:].strip()

    # Remove commas
    cleaned = cleaned.replace(",", "")

    if not cleaned:
        return None

    try:
        if "." in cleaned:
            value = float(cleaned)
        else:
            value = int(cleaned)
        return -value if is_negative else value
    except ValueError:
        return None


def format_english_number(value: int | float | None, negative_style: str = "parentheses") -> str:
    """
    Format a number for English financial statements.

    Args:
        value: numeric value
        negative_style: "parentheses" for (1,234) or "minus" for -1,234

    Examples:
        1234567 -> "1,234,567"
        -1234567 -> "(1,234,567)"
        0 -> "-"
        None -> ""
    """
    if value is None:
        return ""

    if value == 0:
        return "-"

    is_negative = value < 0
    abs_value = abs(value)

    if isinstance(abs_value, float):
        # Format with decimal places
        formatted = f"{abs_value:,.2f}"
    else:
        formatted = f"{abs_value:,}"

    if is_negative:
        if negative_style == "parentheses":
            return f"({formatted})"
        else:
            return f"-{formatted}"
    return formatted


def detect_number_format(text: str) -> dict:
    """
    Detect the number formatting conventions used in a text sample.
    Returns dict with detected patterns.
    """
    patterns = {
        "thousands_separator": "," if "," in text else "",
        "negative_style": "parentheses" if re.search(r"\(\d", text) else "minus",
        "zero_style": "dash" if re.search(r"(?<!\w)-(?!\w)", text) else "zero",
        "has_won_symbol": "\\" in text or "\u20a9" in text,
        "has_decimals": bool(re.search(r"\d\.\d", text)),
    }
    return patterns

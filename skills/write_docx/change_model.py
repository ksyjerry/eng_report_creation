"""
Change data classes — describe what modifications to apply to a DOCX template.

Each Change targets a specific element (cell, row, table, section, header)
and carries the data needed to perform that modification.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ir_schema import ChangeType


@dataclass
class Change:
    """
    A single modification to apply to a DOCX template.

    Attributes:
        type:             What kind of change (from ir_schema.ChangeType).
        target:           Address string that locates the element, e.g.
                          "table:5:row:3:col:2"   — a specific cell
                          "table:5:row:3"          — a specific row
                          "table:5"                — an entire table
                          "paragraph:15"           — a body-level paragraph
                          "header"                 — all header/footer XMLs
        value:            New text value (for single-cell or text updates).
        values:           Column-index → text mapping for multi-cell row updates.
        rows:             List of row dicts for ADD_ROW.  Each dict maps
                          logical column index → text value.
        content:          For ADD_NOTE — list of (type, content) tuples where
                          type is "paragraph" or "table" etc.
        reference_index:  Body index of the element to clone from.
        position:         "before" or "after" the reference_index.
        spacer_indices:   Physical column indices that are spacers (skip them
                          when writing cell values).
        old_year:         For header year replacement — year to find.
        new_year:         For header year replacement — year to substitute.
    """
    type: ChangeType
    target: str
    value: str = ""
    values: dict[int, str] = field(default_factory=dict)
    rows: list[dict[int, str]] = field(default_factory=list)
    content: list[tuple[str, str]] = field(default_factory=list)
    reference_index: int = -1
    position: str = "after"
    spacer_indices: list[int] = field(default_factory=list)
    old_year: str = ""
    new_year: str = ""


# ---------------------------------------------------------------------------
# Target-address parsing helpers
# ---------------------------------------------------------------------------

def parse_target(target: str) -> dict:
    """
    Parse a target address string into a dict of components.

    Examples:
        "table:5:row:3:col:2" → {"table": 5, "row": 3, "col": 2}
        "table:5:row:3"       → {"table": 5, "row": 3}
        "table:5"             → {"table": 5}
        "paragraph:15"        → {"paragraph": 15}
        "header"              → {"header": True}
    """
    parts = target.split(":")
    result: dict = {}

    i = 0
    while i < len(parts):
        key = parts[i]
        if key == "header":
            result["header"] = True
            i += 1
        elif i + 1 < len(parts):
            try:
                result[key] = int(parts[i + 1])
            except ValueError:
                result[key] = parts[i + 1]
            i += 2
        else:
            result[key] = True
            i += 1

    return result

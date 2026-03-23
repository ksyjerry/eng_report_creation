"""
Intermediate Representation (IR) Schema for Financial Statements.

Defines the common data structures that all parsers output
and all writers consume. This is the contract between skills.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DocType(Enum):
    CONSOLIDATED = "consolidated"   # 연결
    SEPARATE = "separate"           # 별도


class StatementType(Enum):
    BALANCE_SHEET = "BS"                    # 재무상태표
    INCOME_STATEMENT = "IS"                 # 포괄손익계산서
    CHANGES_IN_EQUITY = "CE"               # 자본변동표
    CASH_FLOW = "CF"                        # 현금흐름표


class ElementType(Enum):
    PARAGRAPH = "paragraph"
    TABLE = "table"
    SUBTITLE = "subtitle"
    PAGE_BREAK = "page_break"


class ChangeType(Enum):
    UPDATE_VALUES = "update_values"
    UPDATE_TEXT = "update_text"
    ADD_ROW = "add_row"
    DELETE_ROW = "delete_row"
    ADD_COLUMN = "add_column"
    ADD_TABLE = "add_table"
    DELETE_TABLE = "delete_table"
    ADD_NOTE = "add_note"
    DELETE_NOTE = "delete_note"
    RESTRUCTURE = "restructure"


class SpacingStrategy(Enum):
    SPACER_COLUMN = "spacer_column"     # HYBE style
    EMPTY_ROW = "empty_row"             # SBL style
    MIXED = "mixed"
    NONE = "none"


class MergeStrategy(Enum):
    VMERGE_HEAVY = "vmerge_heavy"
    GRIDSPAN_HEAVY = "gridspan_heavy"
    BALANCED = "balanced"
    MINIMAL = "minimal"


class WidthStrategy(Enum):
    FIXED = "fixed"
    AUTO = "auto"
    MIXED = "mixed"


# ──────────────────────────────────────────────
# Core IR structures
# ──────────────────────────────────────────────

@dataclass
class CellValue:
    """A single cell in a table."""
    text: str = ""
    colspan: int = 1
    rowspan: int = 1
    is_header: bool = False
    align: str = ""             # LEFT, CENTER, RIGHT
    indent_level: int = 0       # for hierarchical labels


@dataclass
class TableRow:
    """A row in a table."""
    cells: list[CellValue] = field(default_factory=list)
    is_header_row: bool = False
    is_subtotal: bool = False
    is_total: bool = False
    is_empty: bool = False      # for SBL empty-row-2 pattern


@dataclass
class TableData:
    """A parsed table with logical structure (spacers removed)."""
    id: str = ""
    headers: list[TableRow] = field(default_factory=list)
    rows: list[TableRow] = field(default_factory=list)
    footnotes: list[str] = field(default_factory=list)
    title: str = ""
    unit: str = ""              # e.g., "(in thousands of Korean won)"
    source_index: int = -1      # index in original document
    # Column mapping: logical col → physical col (for DOCX tables with spacers removed)
    logical_to_physical: dict[int, int] = field(default_factory=dict)


@dataclass
class NoteElement:
    """A single element within a note (paragraph, table, subtitle, etc.)."""
    type: ElementType = ElementType.PARAGRAPH
    text: str = ""
    depth: int = 0              # nesting level (0=top, 1=subsection, etc.)
    numbering: str = ""         # e.g., "(1)", "①", "2.1.1"
    table: Optional[TableData] = None


@dataclass
class Note:
    """A single note/disclosure in the financial statements."""
    id: str = ""
    number: str = ""            # e.g., "1", "2", "2.1"
    title: str = ""
    elements: list[NoteElement] = field(default_factory=list)


@dataclass
class FinancialStatement:
    """One of the 4 main financial statements."""
    id: str = ""
    statement_type: StatementType = StatementType.BALANCE_SHEET
    title: str = ""
    periods: list[str] = field(default_factory=list)    # e.g., ["2025.12.31", "2024.12.31"]
    table: Optional[TableData] = None


@dataclass
class Section:
    """A section in the document (can be financial statements or notes)."""
    section_type: str = ""      # "cover", "financial_statement", "notes"
    section_index: int = 0
    title: str = ""
    financial_statements: list[FinancialStatement] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    elements: list[NoteElement] = field(default_factory=list)   # raw elements


@dataclass
class DocumentMeta:
    """Metadata about the source document."""
    company: str = ""
    period_current: str = ""    # e.g., "2025"
    period_prior: str = ""      # e.g., "2024"
    doc_type: DocType = DocType.CONSOLIDATED
    source_format: str = ""     # "dsd" or "docx"


@dataclass
class DocxProfile:
    """Auto-detected formatting profile of a DOCX file."""
    spacing_strategy: SpacingStrategy = SpacingStrategy.NONE
    primary_style: str = ""             # most common paragraph style
    width_strategy: WidthStrategy = WidthStrategy.AUTO
    merge_strategy: MergeStrategy = MergeStrategy.MINIMAL
    section_count: int = 1
    color_scheme: str = "monochrome"    # "monochrome" or "colored"
    title_style: str = ""               # style used for note titles
    subtitle_style: str = ""            # style used for subsection titles
    body_style: str = ""                # style used for body text
    empty_row_pattern: bool = False     # SBL-style empty row 2
    spacer_col_widths: list[int] = field(default_factory=list)  # typical spacer widths


@dataclass
class ParsedDocument:
    """The complete IR output from any parser."""
    meta: DocumentMeta = field(default_factory=DocumentMeta)
    sections: list[Section] = field(default_factory=list)
    docx_profile: Optional[DocxProfile] = None  # only for DOCX

    def get_financial_statements(self) -> list[FinancialStatement]:
        """Convenience: collect all financial statements across sections."""
        result = []
        for s in self.sections:
            result.extend(s.financial_statements)
        return result

    def get_all_notes(self) -> list[Note]:
        """Convenience: collect all notes across sections."""
        result = []
        for s in self.sections:
            result.extend(s.notes)
        return result

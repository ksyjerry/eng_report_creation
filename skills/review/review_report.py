"""
ReviewReport data classes for the review skill.

Defines severity levels and structured review output.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReviewItem:
    """A single finding from the review process."""
    severity: str          # "CRITICAL", "WARNING", "INFO"
    category: str          # "number", "completeness", "balance", "format"
    location: str          # human-readable location
    message: str
    expected: str = ""
    found: str = ""

    def __str__(self) -> str:
        parts = [f"[{self.severity}] [{self.category}] {self.location}: {self.message}"]
        if self.expected:
            parts.append(f"  expected: {self.expected}")
        if self.found:
            parts.append(f"  found:    {self.found}")
        return "\n".join(parts)


@dataclass
class ReviewReport:
    """Aggregated review results with pass/fail status."""
    status: str = "PASS"               # "PASS", "NEEDS_REVISION", "CRITICAL_ERRORS"
    items: list[ReviewItem] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def add(self, item: ReviewItem) -> None:
        self.items.append(item)

    def finalize(self) -> None:
        """Compute summary counts and determine overall status."""
        by_severity: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for item in self.items:
            by_severity[item.severity] = by_severity.get(item.severity, 0) + 1
            by_category[item.category] = by_category.get(item.category, 0) + 1

        self.summary = {
            "total": len(self.items),
            "by_severity": by_severity,
            "by_category": by_category,
        }

        critical = by_severity.get("CRITICAL", 0)
        warning = by_severity.get("WARNING", 0)

        if critical > 0:
            self.status = "CRITICAL_ERRORS"
        elif warning > 0:
            self.status = "NEEDS_REVISION"
        else:
            self.status = "PASS"

    def __str__(self) -> str:
        lines = [
            f"Review Report  —  Status: {self.status}",
            f"{'=' * 50}",
        ]
        if self.summary:
            lines.append(f"Total items: {self.summary['total']}")
            for sev, cnt in self.summary.get("by_severity", {}).items():
                lines.append(f"  {sev}: {cnt}")
            lines.append("")

        for item in self.items:
            lines.append(str(item))
            lines.append("")

        return "\n".join(lines)

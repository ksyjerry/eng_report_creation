"""
완료 도구 — DOCX 저장, 에스컬레이션, 최종 보고서.
"""

from __future__ import annotations

from agent.tools import tool


_ctx = None
_escalations: list[dict] = []


def set_context(ctx) -> None:
    global _ctx
    _ctx = ctx


def _get_ctx():
    if _ctx is None:
        raise RuntimeError("DocumentContext not initialized")
    return _ctx


@tool("save_docx", "현재 DOCX 상태를 파일로 저장합니다.", is_write=True)
def save_docx(output_path: str) -> str:
    """DOCX 저장."""
    ctx = _get_ctx()
    try:
        saved_path = ctx.save_docx(output_path)
        return f"OK: DOCX saved to {saved_path}"
    except Exception as e:
        return f"ERROR: Failed to save — {e}"


@tool("escalate", "해결하지 못한 문제를 보고합니다.")
def escalate(issue_type: str, description: str, suggestion: str = "") -> str:
    """에스컬레이션 기록."""
    _escalations.append({
        "type": issue_type,
        "description": description,
        "suggestion": suggestion,
    })
    return f"OK: Issue recorded — {issue_type}: {description}"


@tool("final_report", "최종 작업 보고서를 생성합니다.")
def final_report(summary: str, stats: dict = None) -> str:
    """최종 보고서 생성."""
    lines = ["== 최종 보고서 ==", "", summary, ""]

    if stats:
        lines.append("통계:")
        for k, v in stats.items():
            lines.append(f"  {k}: {v}")

    if _escalations:
        lines.append(f"\n에스컬레이션: {len(_escalations)}건")
        for esc in _escalations:
            lines.append(f"  [{esc['type']}] {esc['description']}")
            if esc.get("suggestion"):
                lines.append(f"    → 제안: {esc['suggestion']}")

    return "\n".join(lines)

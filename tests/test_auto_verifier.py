"""auto_verifier 모듈의 VerifyError / VerifyReport 데이터 클래스 단위 테스트."""

import pytest

from agent.auto_verifier import VerifyError, VerifyReport


# ---------------------------------------------------------------------------
# VerifyError
# ---------------------------------------------------------------------------

class TestVerifyError:
    def test_creation(self):
        err = VerifyError(
            table_index=5,
            note_number="10",
            row_idx=3,
            col_name="current",
            severity="CRITICAL",
            error_type="NUMBER_MISMATCH",
            expected="1,234",
            found="5,678",
        )
        assert err.table_index == 5
        assert err.note_number == "10"
        assert err.row_idx == 3
        assert err.col_name == "current"
        assert err.severity == "CRITICAL"
        assert err.error_type == "NUMBER_MISMATCH"
        assert err.expected == "1,234"
        assert err.found == "5,678"
        assert err.auto_fixed is False

    def test_auto_fixed(self):
        err = VerifyError(
            table_index=5,
            note_number="10",
            row_idx=3,
            col_name="current",
            severity="CRITICAL",
            error_type="TOTAL_MISMATCH",
            expected="1,234",
            found="5,678",
            auto_fixed=True,
        )
        assert err.auto_fixed is True


# ---------------------------------------------------------------------------
# VerifyReport
# ---------------------------------------------------------------------------

class TestVerifyReport:
    def test_empty_report(self):
        report = VerifyReport()
        assert report.critical_count == 0
        assert report.unresolved_errors() == []
        assert "검증 결과" in report.summary()

    def test_with_errors(self):
        report = VerifyReport(
            errors=[
                VerifyError(1, "10", 3, "current", "CRITICAL", "NUMBER_MISMATCH", "100", "200"),
                VerifyError(1, "10", 4, "prior", "WARNING", "EMPTY_CELL", "300", ""),
                VerifyError(2, "15", 5, "current", "CRITICAL", "TOTAL_MISMATCH", "500", "600", auto_fixed=True),
            ],
            tables_checked=2,
            cells_checked=10,
            cells_correct=7,
            cells_wrong=3,
            auto_fixed=1,
        )
        assert report.critical_count == 2
        assert len(report.unresolved_errors()) == 2
        summary = report.summary()
        assert "CRITICAL 오류: 2개" in summary
        assert "자동 수정: 1개" in summary

    def test_all_fixed(self):
        report = VerifyReport(
            errors=[
                VerifyError(1, "10", 3, "current", "CRITICAL", "NUMBER_MISMATCH", "100", "200", auto_fixed=True),
            ],
            auto_fixed=1,
        )
        assert len(report.unresolved_errors()) == 0

    def test_summary_contains_table_and_cell_counts(self):
        report = VerifyReport(tables_checked=5, cells_checked=50, cells_correct=48, cells_wrong=2)
        summary = report.summary()
        assert "테이블 검사: 5개" in summary
        assert "셀 검사: 50개" in summary
        assert "정확: 48개" in summary
        assert "오류: 2개" in summary

    def test_summary_includes_error_details(self):
        err = VerifyError(3, "20", 7, "prior", "WARNING", "NUMBER_MISMATCH", "999", "888")
        report = VerifyReport(errors=[err], cells_wrong=1)
        summary = report.summary()
        assert "오류 상세" in summary
        assert "테이블 3" in summary
        assert "주석 20" in summary
        assert "행 7" in summary

    def test_summary_shows_auto_fixed_tag(self):
        err = VerifyError(1, "5", 2, "current", "CRITICAL", "EMPTY_CELL", "100", "(빈셀)", auto_fixed=True)
        report = VerifyReport(errors=[err], auto_fixed=1)
        summary = report.summary()
        assert "[자동수정됨]" in summary

    def test_critical_count_excludes_non_critical(self):
        report = VerifyReport(
            errors=[
                VerifyError(1, "1", 1, "current", "WARNING", "NUMBER_MISMATCH", "1", "2"),
                VerifyError(1, "1", 2, "current", "INFO", "NUMBER_MISMATCH", "3", "4"),
                VerifyError(1, "1", 3, "current", "CRITICAL", "TOTAL_MISMATCH", "5", "6"),
            ]
        )
        assert report.critical_count == 1

    def test_unresolved_errors_mixed(self):
        report = VerifyReport(
            errors=[
                VerifyError(1, "1", 1, "current", "CRITICAL", "EMPTY_CELL", "1", "", auto_fixed=True),
                VerifyError(1, "1", 2, "prior", "WARNING", "NUMBER_MISMATCH", "2", "3"),
                VerifyError(1, "1", 3, "current", "CRITICAL", "TOTAL_MISMATCH", "4", "5", auto_fixed=True),
                VerifyError(2, "2", 1, "current", "CRITICAL", "COLUMN_SHIFT", "a", "b"),
            ]
        )
        unresolved = report.unresolved_errors()
        assert len(unresolved) == 2
        assert all(not e.auto_fixed for e in unresolved)

"""Unit tests for note_filler column mapping helper functions."""

from __future__ import annotations

import pytest

from agent.note_filler import _parse_number, _format_number, _convert_value, _is_numeric_cell


# ---------------------------------------------------------------------------
# _convert_value — 단위 변환 정밀도
# ---------------------------------------------------------------------------

class TestConvertValue:
    """단위 변환 시 정수 나눗셈 + 반올림 정확성 검증."""

    def test_won_to_cheonwon_rounds_up(self):
        # 1234567 / 1000 = 1234.567 → 반올림 1235
        assert _convert_value(1234567, "원", "천원") == 1235

    def test_won_to_cheonwon_exact(self):
        assert _convert_value(1000, "원", "천원") == 1

    def test_won_to_cheonwon_half_rounds_up(self):
        # 500 / 1000 = 0.5 → 반올림 1
        assert _convert_value(500, "원", "천원") == 1

    def test_won_to_cheonwon_below_half_truncates(self):
        # 499 / 1000 = 0.499 → 내림 0
        assert _convert_value(499, "원", "천원") == 0

    def test_none_passthrough(self):
        assert _convert_value(None, "원", "천원") is None

    def test_same_unit_no_change(self):
        assert _convert_value(100, "천원", "천원") == 100

    def test_cheonwon_to_won(self):
        # 역변환: 5 * 1000 = 5000
        assert _convert_value(5, "천원", "원") == 5000

    def test_won_to_million(self):
        assert _convert_value(1500000, "원", "백만원") == 2  # 반올림

    def test_cheonwon_to_million(self):
        assert _convert_value(1500, "천원", "백만원") == 2  # 반올림

    def test_negative_value(self):
        # 음수도 올바르게 변환
        assert _convert_value(-1234567, "원", "천원") == -1235

    def test_zero(self):
        assert _convert_value(0, "원", "천원") == 0


# ---------------------------------------------------------------------------
# _parse_number — 다양한 숫자 형식 파싱
# ---------------------------------------------------------------------------

class TestParseNumber:
    """한국어 재무제표 숫자 형식 파싱 검증."""

    def test_comma_separated(self):
        assert _parse_number("1,234") == 1234

    def test_parentheses_negative(self):
        assert _parse_number("(1,234)") == -1234

    def test_triangle_negative(self):
        assert _parse_number("△1,234") == -1234

    def test_dash_is_zero(self):
        assert _parse_number("-") == 0

    def test_empty_string_is_zero(self):
        assert _parse_number("") == 0

    def test_non_numeric_returns_none(self):
        assert _parse_number("some text") is None

    def test_zero_string(self):
        assert _parse_number("0") == 0

    def test_large_number(self):
        assert _parse_number("1,234,567,890") == 1234567890

    def test_filled_triangle_negative(self):
        assert _parse_number("▲1,234") == -1234

    def test_whitespace_stripped(self):
        assert _parse_number("  1,234  ") == 1234

    def test_em_dash_is_zero(self):
        assert _parse_number("—") == 0

    def test_en_dash_is_zero(self):
        assert _parse_number("–") == 0

    def test_plain_negative(self):
        assert _parse_number("-1234") == -1234


# ---------------------------------------------------------------------------
# _format_number — DOCX 표시 형식 출력
# ---------------------------------------------------------------------------

class TestFormatNumber:
    """int → DOCX 표시 형식 변환 검증."""

    def test_positive_with_commas(self):
        assert _format_number(1234567) == "1,234,567"

    def test_negative_in_parentheses(self):
        assert _format_number(-1234) == "(1,234)"

    def test_zero_is_dash(self):
        assert _format_number(0) == "-"

    def test_none_is_dash(self):
        assert _format_number(None) == "-"

    def test_small_positive(self):
        assert _format_number(5) == "5"

    def test_small_negative(self):
        assert _format_number(-5) == "(5)"

    def test_large_negative(self):
        assert _format_number(-1234567890) == "(1,234,567,890)"


# ---------------------------------------------------------------------------
# _is_numeric_cell — 숫자/텍스트 셀 분류
# ---------------------------------------------------------------------------

class TestIsNumericCell:
    """셀 값이 숫자 영역인지 텍스트 영역인지 판별."""

    def test_comma_number_is_numeric(self):
        assert _is_numeric_cell("1,234") is True

    def test_parentheses_number_is_numeric(self):
        assert _is_numeric_cell("(1,234)") is True

    def test_dash_is_numeric(self):
        assert _is_numeric_cell("-") is True

    def test_empty_is_numeric(self):
        assert _is_numeric_cell("") is True

    def test_text_label_not_numeric(self):
        assert _is_numeric_cell("Total Assets") is False

    def test_text_label_korean_not_numeric(self):
        assert _is_numeric_cell("Net Income") is False

    def test_em_dash_is_numeric(self):
        assert _is_numeric_cell("—") is True

    def test_en_dash_is_numeric(self):
        assert _is_numeric_cell("–") is True

    def test_triangle_number_is_numeric(self):
        assert _is_numeric_cell("△1,234") is True

    def test_plain_integer_is_numeric(self):
        assert _is_numeric_cell("1234") is True

    def test_whitespace_only_is_numeric(self):
        assert _is_numeric_cell("   ") is True


# ---------------------------------------------------------------------------
# Round-trip: parse → format 일관성
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """parse → format round-trip 검증."""

    @pytest.mark.parametrize("text,expected", [
        ("1,234", "1,234"),
        ("(1,234)", "(1,234)"),
        ("-", "-"),
        ("0", "-"),
    ])
    def test_parse_then_format(self, text: str, expected: str):
        parsed = _parse_number(text)
        assert _format_number(parsed) == expected

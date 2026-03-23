"""translate_tool 단위 테스트."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from agent.tools.translate_tool import (
    _similarity,
    _translate_date,
    _extract_json_array,
    _find_ifrs_match,
    _find_best_fuzzy,
    _load_ifrs_terms,
    translate,
    find_prior_translation,
)


# ==================================================================
# _similarity
# ==================================================================

class TestSimilarity:

    def test_identical(self):
        assert _similarity("유동자산", "유동자산") == 1.0

    def test_different(self):
        assert _similarity("유동자산", "비유동자산") < 1.0
        assert _similarity("유동자산", "비유동자산") > 0.3

    def test_empty(self):
        assert _similarity("", "") == 1.0
        assert _similarity("abc", "") == 0.0


# ==================================================================
# _translate_date
# ==================================================================

class TestTranslateDate:

    def test_basic_date(self):
        result = _translate_date("2025년 12월 31일")
        assert result == "December 31, 2025"

    def test_date_with_as_at(self):
        result = _translate_date("2025년 12월 31일 현재")
        assert result == "As at December 31, 2025"

    def test_various_months(self):
        assert _translate_date("2024년 1월 1일") == "January 1, 2024"
        assert _translate_date("2024년 6월 30일") == "June 30, 2024"

    def test_non_date(self):
        assert _translate_date("유동자산") is None
        assert _translate_date("2024년도") is None


# ==================================================================
# _extract_json_array
# ==================================================================

class TestExtractJsonArray:

    def test_clean_json(self):
        result = _extract_json_array('["hello", "world"]')
        assert result == ["hello", "world"]

    def test_code_block(self):
        result = _extract_json_array('```json\n["hello", "world"]\n```')
        assert result == ["hello", "world"]

    def test_numbered_lines(self):
        result = _extract_json_array("1. Hello\n2. World\n3. Test")
        assert result == ["Hello", "World", "Test"]

    def test_plain_lines(self):
        result = _extract_json_array('"Hello"\n"World"')
        assert result == ["Hello", "World"]

    def test_empty(self):
        result = _extract_json_array("")
        assert result is None


# ==================================================================
# _find_ifrs_match
# ==================================================================

class TestFindIfrsMatch:

    def test_exact(self):
        ifrs = {"유동자산": "Current assets", "비유동자산": "Non-current assets"}
        assert _find_ifrs_match("유동자산", ifrs) == "Current assets"

    def test_partial_contains(self):
        ifrs = {"매출채권": "Trade receivables"}
        assert _find_ifrs_match("매출채권 및 기타", ifrs) == "Trade receivables"

    def test_partial_contained(self):
        ifrs = {"매출채권 및 기타채권": "Trade and other receivables"}
        assert _find_ifrs_match("매출채권", ifrs) == "Trade and other receivables"

    def test_fuzzy(self):
        ifrs = {"기타포괄손익-공정가치측정금융자산": "Financial assets at FVOCI"}
        result = _find_ifrs_match("기타포괄손익-공정가치금융자산", ifrs)
        assert result == "Financial assets at FVOCI"

    def test_no_match(self):
        ifrs = {"유동자산": "Current assets"}
        assert _find_ifrs_match("완전히다른텍스트", ifrs) is None


# ==================================================================
# _find_best_fuzzy
# ==================================================================

class TestFindBestFuzzy:

    def test_good_match(self):
        candidates = {"기타포괄손익-공정가치측정금융자산": "FVOCI assets"}
        result = _find_best_fuzzy("기타포괄손익-공정가치금융자산", candidates, threshold=0.6)
        assert result is not None
        assert result[1] == "FVOCI assets"

    def test_below_threshold(self):
        candidates = {"유동자산": "Current assets"}
        result = _find_best_fuzzy("완전히 다른 텍스트", candidates, threshold=0.6)
        assert result is None


# ==================================================================
# translate (async)
# ==================================================================

class TestTranslate:

    async def test_exact_match(self):
        result = await translate(
            texts=["유동자산", "비유동자산"],
            prior_translations={"유동자산": "Current assets", "비유동자산": "Non-current assets"},
        )
        assert "Current assets" in result
        assert "Non-current assets" in result
        assert "[REUSE]" in result

    async def test_date_translation(self):
        result = await translate(texts=["2025년 12월 31일"])
        assert "December 31, 2025" in result
        assert "[DATE]" in result

    async def test_empty_text_skip(self):
        result = await translate(texts=["", "  "])
        assert "[SKIP]" in result

    async def test_ifrs_fallback(self):
        # No prior_translations, no LLM — should use IFRS terms
        result = await translate(texts=["유동자산"])
        assert "[IFRS]" in result or "[REUSE]" in result or "Current assets" in result

    async def test_fuzzy_adjust_no_llm(self):
        result = await translate(
            texts=["기타포괄손익-공정가치금융자산"],
            prior_translations={"기타포괄손익-공정가치측정금융자산": "Financial assets at FVOCI"},
        )
        # Without LLM, should use prior English as fallback
        assert "FVOCI" in result

    async def test_untranslated_no_llm(self):
        result = await translate(texts=["이것은_매우_독특한_텍스트입니다"])
        assert "[UNTRANSLATED]" in result or "[IFRS]" in result

    async def test_with_mock_llm_adjust(self):
        from agent.tools.translate_tool import set_llm_client

        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value='["Financial assets measured at FVOCI"]')
        set_llm_client(mock_llm)

        try:
            result = await translate(
                texts=["기타포괄손익-공정가치금융자산"],
                prior_translations={"기타포괄손익-공정가치측정금융자산": "Financial assets at FVOCI"},
            )
            assert "[ADJUST]" in result
            assert "FVOCI" in result
        finally:
            set_llm_client(None)

    async def test_with_mock_llm_new(self):
        from agent.tools.translate_tool import set_llm_client

        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value='["Test translated text"]')
        set_llm_client(mock_llm)

        try:
            result = await translate(
                texts=["이것은_고유한_텍스트_번역필요"],
                context="주석 14 유형자산",
            )
            assert "[NEW]" in result or "[IFRS]" in result
        finally:
            set_llm_client(None)


# ==================================================================
# find_prior_translation
# ==================================================================

class TestFindPriorTranslation:

    def test_date(self):
        result = find_prior_translation("2025년 12월 31일")
        assert "December 31, 2025" in result
        assert "date conversion" in result

    def test_empty(self):
        result = find_prior_translation("")
        assert "ERROR" in result

    def test_not_found(self):
        result = find_prior_translation("이것은_절대_없는_텍스트입니다")
        assert "Not Found" in result

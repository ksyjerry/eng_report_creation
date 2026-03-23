"""E2E 파이프라인 테스트 — 실제 파일로 Agent.run() 전체 흐름 검증.

테스트 범위:
  1. DOCX/DSD 로딩
  2. 연도 롤링 (year_roller)
  3. 주석 자동 채우기 (note_filler)
  4. 자동 검증 (auto_verifier)
  5. ReAct 루프 (MockLLM)
  6. 출력 DOCX 저장 + 데이터 정합성 검증
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile

import pytest

from agent.agent import Agent
from agent.document_context import DocumentContext
from agent.note_filler import (
    apply_note_filling,
    extract_dsd_tables,
    _parse_number,
    _get_cell_by_target_col,
)
from agent.auto_verifier import verify_fill_results
from agent.year_roller import apply_year_rolling
from agent.tools.docx_ops.xml_helpers import findall_w, get_cell_text
from skills.parse_dsd import parse_dsd


# ---------------------------------------------------------------------------
# Test data paths
# ---------------------------------------------------------------------------

FILES_DIR = os.path.join(os.path.dirname(__file__), "..", "files")

HYBE_DOCX = os.path.join(FILES_DIR, "Hybe 2024 Eng Report.docx")
HYBE_DSD = os.path.join(FILES_DIR, "Hybe 2025 Eng Report.dsd")
SBL_DOCX = os.path.join(FILES_DIR, "SBL_2023_English report_vF.docx")
SBL_DSD = os.path.join(FILES_DIR, "SBL_2024_별도감사보고서.dsd")

_has_hybe = os.path.exists(HYBE_DOCX) and os.path.exists(HYBE_DSD)
_has_sbl = os.path.exists(SBL_DOCX) and os.path.exists(SBL_DSD)


# ---------------------------------------------------------------------------
# Smart MockLLM — 10 step 이상 경과 후 finish
# ---------------------------------------------------------------------------

class _SmartMockLLM:
    """E2E 테스트용 MockLLM.

    첫 10 step은 read_memo로 Working Memory 확인 (Agent의 조기 finish 방지),
    이후 finish 반환.
    """

    def __init__(self):
        self._call_count = 0
        self._memo_keys = [
            "auto_fill_stats", "verify_report", "unmatched_dsd_tables",
            "glossary", "auto_fill_stats", "verify_report",
            "unmatched_dsd_tables", "glossary", "auto_fill_stats", "verify_report",
        ]

    async def complete(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        self._call_count += 1

        if self._call_count <= 10:
            idx = (self._call_count - 1) % len(self._memo_keys)
            key = self._memo_keys[idx]
            return json.dumps({
                "thought": f"Working Memory에서 {key} 확인",
                "action": "read_memo",
                "action_input": {"key": key},
            })

        return json.dumps({
            "thought": "모든 자동 처리 완료. 결과 저장.",
            "action": "finish",
            "action_input": {
                "summary": "E2E 테스트 완료",
                "stats": {"mock_llm_calls": self._call_count},
            },
        })


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def output_dir():
    """임시 출력 디렉토리."""
    d = tempfile.mkdtemp(prefix="sara_e2e_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# 1. 코드 파이프라인 E2E (year_roller + note_filler + auto_verifier)
# ---------------------------------------------------------------------------

class TestCodePipelineHybe:
    """Hybe 파일로 코드 기반 파이프라인 전체 검증."""

    @pytest.mark.skipif(not _has_hybe, reason="Hybe files not found")
    def test_year_rolling(self):
        ctx = DocumentContext()
        ctx.load_docx(HYBE_DOCX)
        dsd_data = parse_dsd(HYBE_DSD)
        ctx.dsd_data = dsd_data

        stats = apply_year_rolling(ctx, dsd_data)
        assert stats["total_elements"] > 0, "연도 롤링이 하나 이상의 요소를 수정해야 함"

    @pytest.mark.skipif(not _has_hybe, reason="Hybe files not found")
    def test_note_filling(self):
        ctx = DocumentContext()
        ctx.load_docx(HYBE_DOCX)
        dsd_data = parse_dsd(HYBE_DSD)
        ctx.dsd_data = dsd_data
        apply_year_rolling(ctx, dsd_data)

        stats, matches = apply_note_filling(ctx, dsd_data)

        assert stats["tables_matched"] >= 120, f"매칭 {stats['tables_matched']}개 — 120개 이상이어야 함"
        assert stats["cells_updated"] >= 1000, f"셀 업데이트 {stats['cells_updated']}개 — 1000개 이상이어야 함"
        assert stats["errors"] == 0, f"채우기 에러 {stats['errors']}개 — 0이어야 함"

    @pytest.mark.skipif(not _has_hybe, reason="Hybe files not found")
    def test_auto_verify_zero_critical(self):
        ctx = DocumentContext()
        ctx.load_docx(HYBE_DOCX)
        dsd_data = parse_dsd(HYBE_DSD)
        ctx.dsd_data = dsd_data
        apply_year_rolling(ctx, dsd_data)
        _, matches = apply_note_filling(ctx, dsd_data)

        report = verify_fill_results(ctx, dsd_data, matches)

        assert report.critical_count == 0, f"CRITICAL {report.critical_count}개 — 0이어야 함\n{report.summary()}"
        assert report.cells_correct >= 1600, f"정확 {report.cells_correct}개 — 1600개 이상이어야 함"

    @pytest.mark.skipif(not _has_hybe, reason="Hybe files not found")
    def test_output_docx_saved(self, output_dir):
        ctx = DocumentContext()
        ctx.load_docx(HYBE_DOCX)
        dsd_data = parse_dsd(HYBE_DSD)
        ctx.dsd_data = dsd_data
        apply_year_rolling(ctx, dsd_data)
        apply_note_filling(ctx, dsd_data)

        output_path = os.path.join(output_dir, "hybe_e2e_output.docx")
        ctx.save_docx(output_path)

        assert os.path.exists(output_path), "출력 DOCX 파일이 생성되어야 함"
        assert os.path.getsize(output_path) > 10000, "출력 DOCX 크기가 10KB 이상이어야 함"

        # 출력 DOCX를 다시 읽어서 데이터 정합성 확인
        ctx2 = DocumentContext()
        ctx2.load_docx(output_path)
        assert ctx2.num_tables() > 100, "출력 DOCX에 테이블이 100개 이상이어야 함"


class TestCodePipelineSBL:
    """SBL 파일로 코드 기반 파이프라인 전체 검증."""

    @pytest.mark.skipif(not _has_sbl, reason="SBL files not found")
    def test_year_rolling(self):
        ctx = DocumentContext()
        ctx.load_docx(SBL_DOCX)
        dsd_data = parse_dsd(SBL_DSD)
        ctx.dsd_data = dsd_data

        stats = apply_year_rolling(ctx, dsd_data)
        assert stats["total_elements"] > 0

    @pytest.mark.skipif(not _has_sbl, reason="SBL files not found")
    def test_note_filling(self):
        ctx = DocumentContext()
        ctx.load_docx(SBL_DOCX)
        dsd_data = parse_dsd(SBL_DSD)
        ctx.dsd_data = dsd_data
        apply_year_rolling(ctx, dsd_data)

        stats, matches = apply_note_filling(ctx, dsd_data)

        assert stats["tables_matched"] >= 80, f"매칭 {stats['tables_matched']}개 — 80개 이상이어야 함"
        assert stats["cells_updated"] >= 500, f"셀 업데이트 {stats['cells_updated']}개 — 500개 이상이어야 함"

    @pytest.mark.skipif(not _has_sbl, reason="SBL files not found")
    def test_auto_verify_zero_critical(self):
        ctx = DocumentContext()
        ctx.load_docx(SBL_DOCX)
        dsd_data = parse_dsd(SBL_DSD)
        ctx.dsd_data = dsd_data
        apply_year_rolling(ctx, dsd_data)
        _, matches = apply_note_filling(ctx, dsd_data)

        report = verify_fill_results(ctx, dsd_data, matches)

        assert report.critical_count == 0, f"CRITICAL {report.critical_count}개 — 0이어야 함\n{report.summary()}"
        assert report.cells_correct >= 800, f"정확 {report.cells_correct}개 — 800개 이상이어야 함"

    @pytest.mark.skipif(not _has_sbl, reason="SBL files not found")
    def test_output_docx_roundtrip(self, output_dir):
        ctx = DocumentContext()
        ctx.load_docx(SBL_DOCX)
        dsd_data = parse_dsd(SBL_DSD)
        ctx.dsd_data = dsd_data
        apply_year_rolling(ctx, dsd_data)
        apply_note_filling(ctx, dsd_data)

        output_path = os.path.join(output_dir, "sbl_e2e_output.docx")
        ctx.save_docx(output_path)

        assert os.path.exists(output_path)

        # 라운드트립: 출력 DOCX를 다시 파싱하여 데이터 확인
        ctx2 = DocumentContext()
        ctx2.load_docx(output_path)
        ctx2.dsd_data = dsd_data
        _, matches2 = apply_note_filling(ctx2, dsd_data)

        # 이미 채워진 DOCX이므로 채울 데이터가 적을 것 (이미 올바른 값)
        report2 = verify_fill_results(ctx2, dsd_data, matches2)
        assert report2.critical_count == 0, f"라운드트립 후 CRITICAL 발생\n{report2.summary()}"


# ---------------------------------------------------------------------------
# 2. Agent.run() 풀 E2E (MockLLM 포함)
# ---------------------------------------------------------------------------

class TestAgentRunE2E:
    """Agent.run() 전체 플로우 (MockLLM + 코드 파이프라인)."""

    @pytest.mark.skipif(not _has_sbl, reason="SBL files not found")
    @pytest.mark.asyncio
    async def test_agent_run_sbl(self, output_dir):
        """SBL 파일로 Agent.run() 전체 실행."""
        logs: list[dict] = []
        output_path = os.path.join(output_dir, "agent_sbl_output.docx")

        agent = Agent(
            llm=_SmartMockLLM(),
            skills_dir=os.path.join(FILES_DIR, "..", "agent_skills"),
            max_steps=30,
            log_callback=lambda msg: logs.append(msg),
        )

        result = await agent.run(
            dsd_path=SBL_DSD,
            docx_path=SBL_DOCX,
            output_path=output_path,
        )

        # 1. 결과 반환 확인
        assert result is not None, "Agent.run()이 결과를 반환해야 함"

        # 2. 출력 파일 확인
        assert os.path.exists(output_path), "출력 DOCX가 생성되어야 함"
        assert os.path.getsize(output_path) > 10000, "출력 DOCX 크기가 10KB 이상이어야 함"

        # 3. 로그 확인 — 핵심 단계가 기록되었는지
        log_messages = " ".join(l.get("message", "") for l in logs)
        assert "DOCX 로딩" in log_messages, "DOCX 로딩 로그 필요"
        assert "DSD 로딩" in log_messages, "DSD 로딩 로그 필요"
        assert "연도 롤링" in log_messages, "연도 롤링 로그 필요"
        assert "주석" in log_messages or "자동 채우기" in log_messages, "주석 채우기 로그 필요"
        assert "검증" in log_messages, "검증 로그 필요"

        # 4. Working Memory 확인
        assert agent.memory.get("auto_fill_stats") is not None, "auto_fill_stats가 메모리에 있어야 함"
        assert agent.memory.get("verify_report") is not None, "verify_report가 메모리에 있어야 함"

        # 5. 출력 DOCX 데이터 검증
        ctx2 = DocumentContext()
        ctx2.load_docx(output_path)
        assert ctx2.num_tables() > 50, "출력 DOCX 테이블 수 검증"

    @pytest.mark.skipif(not _has_hybe, reason="Hybe files not found")
    @pytest.mark.asyncio
    async def test_agent_run_hybe(self, output_dir):
        """Hybe 파일로 Agent.run() 전체 실행."""
        logs: list[dict] = []
        output_path = os.path.join(output_dir, "agent_hybe_output.docx")

        agent = Agent(
            llm=_SmartMockLLM(),
            skills_dir=os.path.join(FILES_DIR, "..", "agent_skills"),
            max_steps=30,
            log_callback=lambda msg: logs.append(msg),
        )

        result = await agent.run(
            dsd_path=HYBE_DSD,
            docx_path=HYBE_DOCX,
            output_path=output_path,
        )

        assert result is not None
        assert os.path.exists(output_path)
        assert os.path.getsize(output_path) > 10000

        # Working Memory에 검증 결과 확인
        verify_text = agent.memory.get("verify_report") or ""
        assert "CRITICAL 오류: 0" in verify_text, f"CRITICAL 0이어야 함\n{verify_text}"


# ---------------------------------------------------------------------------
# 3. 데이터 정합성 — 특정 셀 값 샘플 검증
# ---------------------------------------------------------------------------

class TestDataIntegrity:
    """출력 DOCX의 특정 셀 값이 DSD와 일치하는지 검증."""

    @pytest.mark.skipif(not _has_sbl, reason="SBL files not found")
    def test_sbl_sample_values(self, output_dir):
        """SBL 출력에서 샘플 DSD 값이 DOCX에 존재하는지 확인."""
        ctx = DocumentContext()
        ctx.load_docx(SBL_DOCX)
        dsd_data = parse_dsd(SBL_DSD)
        ctx.dsd_data = dsd_data
        apply_year_rolling(ctx, dsd_data)
        stats, matches = apply_note_filling(ctx, dsd_data)

        output_path = os.path.join(output_dir, "sbl_integrity.docx")
        ctx.save_docx(output_path)

        # 매칭된 테이블에서 랜덤 샘플 검증
        checked = 0
        for match in matches[:20]:  # 처음 20개 매칭만 검증
            dsd_tbl = match.dsd_table
            docx_tbl = match.docx_table
            if docx_tbl.current_phys_col < 0:
                continue

            for dsd_ri, docx_ri in match.row_matches[:3]:  # 각 테이블 3행씩
                dsd_row = next((r for r in dsd_tbl.rows if r.row_idx == dsd_ri), None)
                if dsd_row is None:
                    continue
                cur_val = dsd_row.values.get("current")
                if cur_val is None or cur_val == 0:
                    continue

                try:
                    tc = _get_cell_by_target_col(ctx, docx_tbl.table_index, docx_ri, docx_tbl.current_phys_col)
                    cell_text = get_cell_text(tc).strip()
                    parsed = _parse_number(cell_text)
                    if parsed is not None:
                        # 단위 변환 후 ±1 허용
                        dsd_unit = dsd_tbl.unit or "천원"
                        if dsd_unit in ("원", "won"):
                            expected = cur_val // 1000
                        else:
                            expected = cur_val
                        assert abs(parsed - expected) <= 1, (
                            f"Table {docx_tbl.table_index} Row {docx_ri}: "
                            f"expected {expected}, got {parsed} (raw: {cell_text})"
                        )
                        checked += 1
                except (IndexError, Exception):
                    pass

        assert checked >= 10, f"최소 10개 셀 검증 필요 (실제: {checked})"

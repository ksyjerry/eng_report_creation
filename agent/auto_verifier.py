"""
Auto Verifier — note_filler 출력물(DSD→DOCX 데이터 채우기) 검증 엔진.

검증 항목:
  1. 숫자 일치 검증 (단위 변환 후 ±1 허용)
  2. 합계/소계 검증
  3. 열 뒤바뀜(column shift) 감지
  4. 빈 셀 감지 (DSD 값 있는데 DOCX가 비어 있는 경우)

자동 수정:
  - 열 뒤바뀜 → 당기/전기 스왑
  - 합계 불일치 → DSD 값으로 덮어쓰기
  - 빈 셀 → DSD 값으로 채우기
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from agent.document_context import DocumentContext
from agent.note_filler import (
    TableMatch, DsdTableInfo, DocxTableInfo,
    _parse_number, _format_number, _convert_value, _is_numeric_cell,
    _get_grid_span, _get_cell_by_target_col, extract_dsd_tables,
)
from agent.tools.docx_ops.xml_helpers import findall_w, get_cell_text
from agent.tools.docx_ops.cell_writer import set_cell_text as _set_cell_text

LogCallback = Optional[Callable[[str], None]]


# ---------------------------------------------------------------------------
# 데이터 클래스
# ---------------------------------------------------------------------------

@dataclass
class VerifyError:
    """개별 검증 오류."""
    table_index: int
    note_number: str
    row_idx: int
    col_name: str        # "current" | "prior"
    severity: str        # "CRITICAL" | "WARNING" | "INFO"
    error_type: str      # "NUMBER_MISMATCH" | "TOTAL_MISMATCH" | "COLUMN_SHIFT" | "EMPTY_CELL"
    expected: str
    found: str
    auto_fixed: bool = False


@dataclass
class VerifyReport:
    """검증 결과 보고서."""
    errors: list[VerifyError] = field(default_factory=list)
    tables_checked: int = 0
    cells_checked: int = 0
    cells_correct: int = 0
    cells_wrong: int = 0
    auto_fixed: int = 0

    def summary(self) -> str:
        """사람이 읽기 쉬운 요약 문자열 반환."""
        lines = [
            f"=== 검증 결과 ===",
            f"테이블 검사: {self.tables_checked}개",
            f"셀 검사: {self.cells_checked}개",
            f"정확: {self.cells_correct}개",
            f"오류: {self.cells_wrong}개",
            f"자동 수정: {self.auto_fixed}개",
            f"CRITICAL 오류: {self.critical_count}개",
            f"미해결 오류: {len(self.unresolved_errors())}개",
        ]
        if self.errors:
            lines.append("")
            lines.append("--- 오류 상세 ---")
            for err in self.errors:
                fixed_tag = " [자동수정됨]" if err.auto_fixed else ""
                lines.append(
                    f"[{err.severity}] 테이블 {err.table_index}, "
                    f"주석 {err.note_number}, 행 {err.row_idx}, "
                    f"열 {err.col_name}: {err.error_type} "
                    f"(기대: {err.expected}, 실제: {err.found}){fixed_tag}"
                )
        return "\n".join(lines)

    @property
    def critical_count(self) -> int:
        """CRITICAL 심각도 오류 수."""
        return sum(1 for e in self.errors if e.severity == "CRITICAL")

    def unresolved_errors(self) -> list[VerifyError]:
        """자동 수정되지 않은 오류 목록."""
        return [e for e in self.errors if not e.auto_fixed]


# ---------------------------------------------------------------------------
# 내부 유틸
# ---------------------------------------------------------------------------

def _read_docx_cell_value(
    ctx: DocumentContext,
    table_index: int,
    row_idx: int,
    phys_col: int,
) -> tuple[Optional[int], str]:
    """DOCX 셀에서 숫자 값과 원본 텍스트를 읽기.

    Returns:
        (parsed_value, raw_text) 튜플. 셀이 없거나 파싱 불가 시 (None, raw_text).
    """
    try:
        tc = _get_cell_by_target_col(ctx, table_index, row_idx, phys_col)
    except (IndexError, Exception):
        return None, ""
    raw = get_cell_text(tc)
    parsed = _parse_number(raw)
    return parsed, raw.strip()


def _log(callback: LogCallback, msg: str) -> None:
    """로그 콜백 호출 (있으면)."""
    if callback:
        callback(msg)


# ---------------------------------------------------------------------------
# 메인 검증 함수
# ---------------------------------------------------------------------------

def verify_fill_results(
    ctx: DocumentContext,
    dsd_data,
    matches: list[TableMatch],
    log_callback: LogCallback = None,
) -> VerifyReport:
    """note_filler 출력물 검증.

    각 TableMatch에 대해:
      1. 숫자 일치 검증 (단위 변환 ±1 허용)
      2. 합계/소계 검증
      3. 열 뒤바뀜 감지
      4. 빈 셀 감지

    Args:
        ctx: DocumentContext (DOCX 로드 상태)
        dsd_data: 파싱된 DSD 데이터
        matches: note_filler에서 생성한 TableMatch 리스트
        log_callback: 선택적 로그 콜백

    Returns:
        VerifyReport 검증 보고서
    """
    report = VerifyReport()
    dsd_tables = extract_dsd_tables(dsd_data)

    # DSD 테이블을 (note_number, table_idx_in_note)로 빠르게 조회
    dsd_map: dict[str, DsdTableInfo] = {}
    for dt in dsd_tables:
        key = f"{dt.note_number}_{dt.table_idx_in_note}"
        dsd_map[key] = dt

    for match in matches:
        dsd_tbl = match.dsd_table
        docx_tbl = match.docx_table

        # 컬럼 매핑이 없는 테이블 (Pass5 lightweight fallback)은 검증 건너뜀
        if docx_tbl.current_phys_col < 0:
            continue

        report.tables_checked += 1

        dsd_unit = dsd_tbl.unit or "천원"
        docx_unit = docx_tbl.unit or "천원"

        _log(log_callback,
             f"[검증] 테이블 {docx_tbl.table_index} ↔ 주석 {dsd_tbl.note_number} 검증 시작")

        # DSD 행을 row_idx로 빠르게 조회
        dsd_row_map = {row.row_idx: row for row in dsd_tbl.rows}

        # 열 뒤바뀜 감지용 카운터 및 행별 추적
        shift_count = 0
        shift_total = 0
        shifted_rows: list[int] = []  # 실제로 뒤바뀐 docx_row_idx 목록

        for dsd_ri, docx_ri in match.row_matches:
            dsd_row = dsd_row_map.get(dsd_ri)
            if dsd_row is None:
                continue

            # DSD 값 가져오기 (단위 변환)
            dsd_current_raw = dsd_row.values.get("current")
            dsd_prior_raw = dsd_row.values.get("prior")
            dsd_current = _convert_value(dsd_current_raw, dsd_unit, docx_unit)
            dsd_prior = _convert_value(dsd_prior_raw, dsd_unit, docx_unit)

            # DOCX 셀 값 읽기
            docx_cur_val, docx_cur_text = _read_docx_cell_value(
                ctx, docx_tbl.table_index, docx_ri, docx_tbl.current_phys_col)

            # prior 컬럼 매핑이 없으면 (-1) prior 검증 건너뜀
            if docx_tbl.prior_phys_col >= 0:
                docx_pri_val, docx_pri_text = _read_docx_cell_value(
                    ctx, docx_tbl.table_index, docx_ri, docx_tbl.prior_phys_col)
            else:
                docx_pri_val, docx_pri_text = None, ""

            # --- (a) 숫자 일치 검증 ---
            checks = [("current", dsd_current, docx_cur_val, docx_cur_text)]
            # prior 컬럼 매핑이 있는 경우에만 prior 검증
            if docx_tbl.prior_phys_col >= 0:
                checks.append(("prior", dsd_prior, docx_pri_val, docx_pri_text))
            for col_name, dsd_val, docx_val, docx_text in checks:
                report.cells_checked += 1

                if dsd_val is None:
                    # DSD 값 없으면 검증 불가 → 정확으로 처리
                    report.cells_correct += 1
                    continue

                # --- (d) 빈 셀 감지 ---
                if dsd_val != 0 and (docx_val is None or docx_text in ("", "-", "—", "–")):
                    # 같은 행의 다른 셀에 해당 값이 있는지 확인 (컬럼 매핑 오류 false positive 방지)
                    found_elsewhere = False
                    try:
                        tr_rows = ctx.get_table_rows(docx_tbl.table_index)
                        if 0 <= docx_ri < len(tr_rows):
                            row_cells = findall_w(tr_rows[docx_ri], "w:tc")
                            for other_tc in row_cells:
                                other_text = get_cell_text(other_tc).strip()
                                other_parsed = _parse_number(other_text)
                                if other_parsed is not None and abs(other_parsed - dsd_val) <= 1:
                                    found_elsewhere = True
                                    break
                    except Exception:
                        pass

                    if found_elsewhere:
                        # 값이 다른 컬럼에 존재 → 컬럼 매핑 불일치 (데이터는 정확)
                        report.cells_correct += 1
                        continue

                    report.cells_wrong += 1
                    report.errors.append(VerifyError(
                        table_index=docx_tbl.table_index,
                        note_number=dsd_tbl.note_number,
                        row_idx=docx_ri,
                        col_name=col_name,
                        severity="CRITICAL",
                        error_type="EMPTY_CELL",
                        expected=_format_number(dsd_val),
                        found=docx_text or "(빈셀)",
                    ))
                    continue

                # 숫자 비교 (±1 허용)
                if docx_val is not None and abs(dsd_val - docx_val) <= 1:
                    report.cells_correct += 1
                else:
                    # --- (b) 합계/소계 검증 ---
                    if dsd_row.is_total or dsd_row.is_subtotal:
                        severity = "CRITICAL"
                        error_type = "TOTAL_MISMATCH"
                    else:
                        severity = "WARNING"
                        error_type = "NUMBER_MISMATCH"
                    report.cells_wrong += 1
                    report.errors.append(VerifyError(
                        table_index=docx_tbl.table_index,
                        note_number=dsd_tbl.note_number,
                        row_idx=docx_ri,
                        col_name=col_name,
                        severity=severity,
                        error_type=error_type,
                        expected=_format_number(dsd_val),
                        found=docx_text,
                    ))

            # --- (c) 열 뒤바뀜 감지 (행 단위) ---
            if (dsd_current is not None and dsd_prior is not None
                    and docx_cur_val is not None and docx_pri_val is not None
                    and dsd_current != 0 and dsd_prior != 0
                    and dsd_current != dsd_prior):  # 같은 값이면 감지 불가
                shift_total += 1
                # 먼저 값이 이미 올바른지 확인 (false positive 방지)
                cur_correct = abs(dsd_current - docx_cur_val) <= 1
                pri_correct = abs(dsd_prior - docx_pri_val) <= 1
                if cur_correct and pri_correct:
                    pass  # 값이 올바름 — 스왑 아님
                else:
                    # DSD current == DOCX prior AND DSD prior == DOCX current
                    cur_swapped = abs(dsd_current - docx_pri_val) <= 1
                    pri_swapped = abs(dsd_prior - docx_cur_val) <= 1
                    if cur_swapped and pri_swapped:
                        shift_count += 1
                        shifted_rows.append(docx_ri)

        # 열 뒤바뀜이 과반수 이상이면 COLUMN_SHIFT 오류 추가 (행별 기록)
        if shift_total > 0 and shift_count >= max(1, shift_total // 2):
            _log(log_callback,
                 f"[검증] 테이블 {docx_tbl.table_index}: 열 뒤바뀜 감지 "
                 f"({shift_count}/{shift_total} 행)")
            # 행 목록을 쉼표 구분 문자열로 저장 (auto_fix에서 활용)
            report.errors.append(VerifyError(
                table_index=docx_tbl.table_index,
                note_number=dsd_tbl.note_number,
                row_idx=-1,  # 테이블 전체
                col_name="current/prior",
                severity="CRITICAL",
                error_type="COLUMN_SHIFT",
                expected="당기→current, 전기→prior",
                found=",".join(str(r) for r in shifted_rows),
            ))

    _log(log_callback,
         f"[검증] 완료: {report.tables_checked}개 테이블, "
         f"{report.cells_checked}셀 검사, {report.cells_wrong}개 오류")

    return report


# ---------------------------------------------------------------------------
# 자동 수정 함수
# ---------------------------------------------------------------------------

def auto_fix_errors(
    ctx: DocumentContext,
    report: VerifyReport,
    matches: list[TableMatch],
    log_callback: LogCallback = None,
) -> int:
    """검증 오류 자동 수정.

    수정 가능한 오류:
      - COLUMN_SHIFT: 당기/전기 값 스왑
      - TOTAL_MISMATCH: DSD 합계 값으로 덮어쓰기
      - EMPTY_CELL: DSD 값으로 채우기

    Args:
        ctx: DocumentContext (DOCX 로드 상태, 직접 수정됨)
        report: verify_fill_results에서 생성된 VerifyReport
        matches: note_filler에서 생성한 TableMatch 리스트
        log_callback: 선택적 로그 콜백

    Returns:
        수정된 셀 수
    """
    fixed_count = 0

    # 매치를 table_index로 빠르게 조회
    match_by_table: dict[int, TableMatch] = {
        m.docx_table.table_index: m for m in matches
    }

    # 열 뒤바뀜 수정: 행 단위로 처리
    shift_errors: list[VerifyError] = [
        err for err in report.errors
        if err.error_type == "COLUMN_SHIFT" and not err.auto_fixed
    ]
    shift_tables: set[int] = set()

    for err in shift_errors:
        tbl_idx = err.table_index
        match = match_by_table.get(tbl_idx)
        if match is None:
            continue

        docx_tbl = match.docx_table
        # err.found에 뒤바뀐 행 목록이 쉼표로 저장됨
        try:
            shifted_row_set = {int(r) for r in err.found.split(",") if r.strip().isdigit()}
        except (ValueError, AttributeError):
            shifted_row_set = set()

        # shifted_row_set이 비어있으면 전체 행 스왑 (레거시 호환)
        if not shifted_row_set:
            shifted_row_set = {docx_ri for _, docx_ri in match.row_matches}

        _log(log_callback,
             f"[자동수정] 테이블 {tbl_idx}: 열 뒤바뀜 수정 "
             f"({len(shifted_row_set)}행 스왑)")

        row_swapped = 0
        for _dsd_ri, docx_ri in match.row_matches:
            if docx_ri not in shifted_row_set:
                continue
            try:
                tc_cur = _get_cell_by_target_col(
                    ctx, tbl_idx, docx_ri, docx_tbl.current_phys_col)
                tc_pri = _get_cell_by_target_col(
                    ctx, tbl_idx, docx_ri, docx_tbl.prior_phys_col)
            except (IndexError, Exception):
                continue

            # 같은 셀이면 스왑 불가 (gridSpan 병합으로 인한 동일 셀)
            if tc_cur is tc_pri:
                continue

            cur_text = get_cell_text(tc_cur)
            pri_text = get_cell_text(tc_pri)
            # 같은 텍스트면 스왑 의미 없음
            if cur_text.strip() == pri_text.strip():
                continue

            _set_cell_text(tc_cur, pri_text)
            _set_cell_text(tc_pri, cur_text)
            fixed_count += 2
            row_swapped += 1

        if row_swapped > 0:
            err.auto_fixed = True
            shift_tables.add(tbl_idx)

    # (b) TOTAL_MISMATCH / (c) EMPTY_CELL 수정
    for err in report.errors:
        if err.auto_fixed:
            continue
        if err.error_type not in ("TOTAL_MISMATCH", "EMPTY_CELL"):
            continue

        match = match_by_table.get(err.table_index)
        if match is None:
            continue

        # 이미 열 스왑으로 수정된 테이블이면 개별 수정 건너뜀 (재검증에서 처리)
        if err.table_index in shift_tables:
            continue

        docx_tbl = match.docx_table
        dsd_tbl = match.dsd_table
        dsd_unit = dsd_tbl.unit or "천원"
        docx_unit = docx_tbl.unit or "천원"

        # 해당 행의 DSD 데이터 찾기
        dsd_row_map = {row.row_idx: row for row in dsd_tbl.rows}
        # row_matches에서 해당 docx_row_idx에 대응하는 dsd_row_idx 찾기
        dsd_ri = None
        for d_ri, dx_ri in match.row_matches:
            if dx_ri == err.row_idx:
                dsd_ri = d_ri
                break
        if dsd_ri is None:
            continue

        dsd_row = dsd_row_map.get(dsd_ri)
        if dsd_row is None:
            continue

        # 대상 열의 phys_col 결정
        if err.col_name == "current":
            phys_col = docx_tbl.current_phys_col
            dsd_raw = dsd_row.values.get("current")
        else:
            phys_col = docx_tbl.prior_phys_col
            dsd_raw = dsd_row.values.get("prior")

        # 유효하지 않은 컬럼 매핑이면 건너뜀
        if phys_col < 0:
            continue

        dsd_val = _convert_value(dsd_raw, dsd_unit, docx_unit)
        if dsd_val is None:
            continue

        formatted = _format_number(dsd_val)
        try:
            tc = _get_cell_by_target_col(ctx, err.table_index, err.row_idx, phys_col)
            _set_cell_text(tc, formatted)
            err.auto_fixed = True
            fixed_count += 1
            _log(log_callback,
                 f"[자동수정] 테이블 {err.table_index}, 행 {err.row_idx}, "
                 f"열 {err.col_name}: {err.found} → {formatted}")
        except (IndexError, Exception) as e:
            _log(log_callback,
                 f"[자동수정] 실패: 테이블 {err.table_index}, 행 {err.row_idx} — {e}")

    report.auto_fixed = fixed_count
    _log(log_callback, f"[자동수정] 완료: {fixed_count}개 셀 수정")

    # 1회 재검증
    if fixed_count > 0:
        _log(log_callback, "[자동수정] 수정 후 재검증 시작...")
        re_report = verify_fill_results(ctx, ctx.dsd_data, matches, log_callback)
        # 재검증에서 새로 발견된 오류가 있으면 원본 리포트에 추가
        existing_keys = {
            (e.table_index, e.row_idx, e.col_name, e.error_type)
            for e in report.errors
        }
        for new_err in re_report.errors:
            key = (new_err.table_index, new_err.row_idx, new_err.col_name, new_err.error_type)
            if key not in existing_keys:
                report.errors.append(new_err)

        # 통계 갱신
        report.cells_checked = re_report.cells_checked
        report.cells_correct = re_report.cells_correct
        report.cells_wrong = re_report.cells_wrong

    return fixed_count

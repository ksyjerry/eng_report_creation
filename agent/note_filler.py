"""
Note Filler — DSD 주석 테이블 ↔ DOCX 테이블 자동 매칭 및 데이터 채우기.

연도 롤링과 마찬가지로 LLM 없이 코드 기반으로 처리.

매칭 전략:
- DOCX는 전기(prior year) 보고서. 연도 롤링 후 헤더만 업데이트됨, 데이터는 그대로.
- DOCX "현재연도" 열의 실제 데이터 = 전기 데이터 = DSD 전기 값
- DSD 전기 값과 DOCX 현재열 값을 비교하여 테이블/행 매칭
- 매칭된 행에 DSD 당기/전기 데이터를 채움
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from lxml import etree

from agent.document_context import DocumentContext
from agent.tools.docx_ops.column_mapper import build_column_mapping
from agent.tools.docx_ops.xml_helpers import findall_w, get_cell_text, w, find_w, OOXML_NS
from agent.tools.docx_ops.cell_writer import set_cell_text as _set_cell_text


# ---------------------------------------------------------------------------
# 숫자 파싱/포맷
# ---------------------------------------------------------------------------

def _parse_number(text: str) -> Optional[int]:
    """다양한 숫자 형식을 int로 파싱. 숫자가 아니면 None."""
    text = text.strip()
    if not text or text in ("-", "—", "–", "\\", "/", ""):
        return 0

    negative = False
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
        negative = True
    if text.startswith("△") or text.startswith("▲"):
        text = text[1:]
        negative = True

    # 콤마, 공백, 백슬래시 제거
    text = text.replace(",", "").replace(" ", "").replace("\u00a0", "").lstrip("\\").strip()

    if text.startswith("-"):
        text = text[1:]
        negative = True

    if not text:
        return None

    try:
        val = int(float(text))
        return -val if negative else val
    except ValueError:
        return None


def _is_numeric_cell(text: str) -> bool:
    """셀이 숫자 값인지 판별."""
    text = text.strip()
    if not text:
        return True  # 빈 셀은 숫자 영역일 수 있음
    if text in ("-", "—", "–", "\\", "/"):
        return True
    clean = text.replace(",", "").replace("(", "").replace(")", "").replace("-", "").replace("\\", "").replace(" ", "").replace("△", "").replace("▲", "")
    return clean.replace(".", "").isdigit() if clean else True


def _format_number(value: Optional[int]) -> str:
    """int를 DOCX 표시 형식으로 변환."""
    if value is None or value == 0:
        return "-"
    if value < 0:
        return f"({abs(value):,})"
    return f"{value:,}"


# ---------------------------------------------------------------------------
# DSD 테이블 추출
# ---------------------------------------------------------------------------

@dataclass
class DsdTableRow:
    """DSD 테이블의 한 행."""
    label: str
    values: dict[str, Optional[int]]  # period_key → value (e.g., "당기": 123, "전기": 456)
    row_idx: int
    is_total: bool = False
    is_subtotal: bool = False


@dataclass
class DsdTableInfo:
    """DSD 주석 내 하나의 테이블."""
    note_number: str
    note_title: str
    table_idx_in_note: int
    period_keys: list[str]  # ["당기", "전기"] or ["당기말", "전기말"]
    rows: list[DsdTableRow] = field(default_factory=list)
    col_count: int = 0  # 원본 열 수 (복잡도 판단용)
    unit: str = ""  # "원", "천원", "백만원" 등


def _detect_dsd_unit(headers: list, rows: list = None) -> str:
    """DSD 테이블 헤더 및 초기 데이터 행에서 단위를 감지."""
    # 헤더 먼저
    for hrow in headers:
        for cell in hrow.cells:
            text = cell.text.strip()
            if "천원" in text:
                return "천원"
            if "백만원" in text:
                return "백만원"
            if "원" in text:
                return "원"
    # 데이터 행 처음 2행도 확인 ("(단위: 원)" 패턴)
    if rows:
        for row in rows[:2]:
            for cell in row.cells:
                text = cell.text.strip()
                if re.search(r"단위\s*[:：]\s*원", text) or "(단위: 원)" in text:
                    return "원"
                if "천원" in text:
                    return "천원"
                if "백만원" in text:
                    return "백만원"
    return "원"  # 기본값: 원 (DSD는 대부분 원 단위)


def _detect_docx_unit(tbl) -> str:
    """DOCX 테이블 헤더에서 단위를 감지."""
    rows = findall_w(tbl, "w:tr")
    for ri in range(min(3, len(rows))):
        cells = findall_w(rows[ri], "w:tc")
        for tc in cells:
            text = get_cell_text(tc).strip().lower()
            if "in thousands" in text:
                return "천원"
            if "in millions" in text:
                return "백만원"
            if "in korean won" in text or "korean won)" in text:
                return "원"
    return "천원"  # 기본값


def _convert_value(value: Optional[int], from_unit: str, to_unit: str) -> Optional[int]:
    """단위 변환. e.g., 원 → 천원은 1000으로 나눔. 정수 나눗셈으로 반올림 오차 방지."""
    if value is None or from_unit == to_unit:
        return value
    _UNIT_WON = {"원": 1, "천원": 1000, "백만원": 1000000}
    from_won = _UNIT_WON.get(from_unit, 1000)
    to_won = _UNIT_WON.get(to_unit, 1000)
    if from_won == to_won:
        return value
    # 정수 나눗셈 사용 (반올림: 나머지가 절반 이상이면 올림)
    numerator = value * from_won
    result = numerator // to_won
    remainder = abs(numerator % to_won)
    if remainder * 2 >= to_won:
        result += 1 if numerator >= 0 else -1
    return result


def _identify_period_columns(headers: list) -> dict[int, str]:
    """헤더에서 기간 열을 식별. {col_idx: period_key}

    "당기말"/"전기말"을 우선 인식하고, 없으면 "당기"/"전기"로 fallback.
    Rollforward 테이블에서 "당기초" 대신 "당기말"을 선택하기 위함.
    """
    period_map: dict[int, str] = {}
    # 1차: "당기말"/"전기말" 우선 탐색
    current_end = None
    prior_end = None
    current_any = None
    prior_any = None

    for hrow in headers:
        for ci, cell in enumerate(hrow.cells):
            text = cell.text.strip()
            if "당기말" in text:
                current_end = ci
            elif "전기말" in text:
                prior_end = ci
            elif "당기" in text and current_any is None:
                current_any = ci
            elif "전기" in text and prior_any is None:
                prior_any = ci

    # 우선순위: 말(end) > 일반
    cur = current_end if current_end is not None else current_any
    pri = prior_end if prior_end is not None else prior_any

    if cur is not None:
        period_map[cur] = "current"
    if pri is not None:
        period_map[pri] = "prior"

    return period_map


def extract_dsd_tables(dsd_data) -> list[DsdTableInfo]:
    """DSD 전체에서 주석 테이블 데이터를 추출."""
    results = []
    notes = dsd_data.get_all_notes()

    for note in notes:
        table_idx = 0
        for elem in note.elements:
            if elem.type.value != "table" or elem.table is None:
                continue

            tbl = elem.table
            period_map = _identify_period_columns(tbl.headers)

            # 헤더에서 못 찾으면 열 수 기반 추론
            if not period_map and tbl.rows:
                ncols = len(tbl.rows[0].cells)
                if ncols >= 3:
                    period_map = {1: "current", 2: "prior"}
                elif ncols == 2:
                    period_map = {1: "current"}

            # 단순 2열(당기/전기) 테이블만 자동 처리
            current_cols = [c for c, k in period_map.items() if k == "current"]
            prior_cols = [c for c, k in period_map.items() if k == "prior"]

            if not current_cols:
                table_idx += 1
                continue

            cur_col = current_cols[0]
            pri_col = prior_cols[0] if prior_cols else -1

            period_keys = ["current"]
            if pri_col >= 0:
                period_keys.append("prior")

            row_data = []
            for ri, row in enumerate(tbl.rows):
                if len(row.cells) < 2:
                    continue
                label = row.cells[0].text.strip()
                if not label:
                    continue

                values: dict[str, Optional[int]] = {}
                if 0 <= cur_col < len(row.cells):
                    values["current"] = _parse_number(row.cells[cur_col].text)
                if 0 <= pri_col < len(row.cells):
                    values["prior"] = _parse_number(row.cells[pri_col].text)

                row_data.append(DsdTableRow(
                    label=label,
                    values=values,
                    row_idx=ri,
                    is_total=row.is_total,
                    is_subtotal=row.is_subtotal,
                ))

            if row_data:
                unit = (tbl.unit.strip() if tbl.unit else "") or _detect_dsd_unit(tbl.headers, tbl.rows)
                results.append(DsdTableInfo(
                    note_number=note.number,
                    note_title=note.title,
                    table_idx_in_note=table_idx,
                    period_keys=period_keys,
                    rows=row_data,
                    col_count=len(tbl.rows[0].cells) if tbl.rows else 0,
                    unit=unit,
                ))
            table_idx += 1

    return results


# ---------------------------------------------------------------------------
# DOCX 테이블 추출
# ---------------------------------------------------------------------------

@dataclass
class DocxTableRow:
    """DOCX 테이블의 한 행."""
    label: str
    current_val: Optional[int]  # "현재연도" 열의 값 (실제로는 전기 데이터)
    prior_val: Optional[int]    # "전기연도" 열의 값
    row_idx: int
    current_phys_col: int  # 현재연도 값의 physical column
    prior_phys_col: int    # 전기연도 값의 physical column


@dataclass
class DocxTableInfo:
    """DOCX 테이블의 구조화된 정보."""
    table_index: int
    num_rows: int
    current_phys_col: int  # "현재연도" 데이터의 physical column
    prior_phys_col: int    # "전기연도" 데이터의 physical column
    rows: list[DocxTableRow] = field(default_factory=list)
    spacer_indices: list[int] = field(default_factory=list)
    unit: str = "천원"


def _get_grid_span(tc) -> int:
    """셀의 gridSpan 반환."""
    tc_pr = find_w(tc, "w:tcPr")
    if tc_pr is not None:
        gs = find_w(tc_pr, "w:gridSpan")
        if gs is not None:
            try:
                return int(gs.get(w("val"), "1"))
            except ValueError:
                pass
    return 1


def _find_data_start_row(tbl) -> int:
    """데이터 시작 행을 찾기. 빈 행(empty-row-2 패턴)을 건너뜀."""
    rows = findall_w(tbl, "w:tr")
    for ri in range(2, min(len(rows), 5)):
        cells = findall_w(rows[ri], "w:tc")
        texts = [get_cell_text(c).strip() for c in cells]
        non_empty = [t for t in texts if t]
        if len(non_empty) >= 2:
            return ri
    return 2


def _get_row_phys_cols(row_elem) -> list[tuple[int, int]]:
    """행의 (셀 인덱스, physical column 시작) 목록 반환."""
    cells = findall_w(row_elem, "w:tc")
    result = []
    phys_col = 0
    for ci, tc in enumerate(cells):
        result.append((ci, phys_col))
        phys_col += _get_grid_span(tc)
    return result


def _find_representative_phys_cols(tbl) -> dict[int, list[int]]:
    """
    모든 데이터 행의 gridSpan 패턴을 검사하여 대표 physical column 매핑 생성.

    Returns: {셀 인덱스: [해당 셀이 등장하는 physical column 목록]}
    """
    rows = findall_w(tbl, "w:tr")
    start_row = _find_data_start_row(tbl)

    cell_idx_to_phys_cols: dict[int, list[int]] = {}
    for ri in range(start_row, min(len(rows), 25)):
        row_cols = _get_row_phys_cols(rows[ri])
        for ci, phys in row_cols:
            cell_idx_to_phys_cols.setdefault(ci, []).append(phys)

    return cell_idx_to_phys_cols


def _find_data_columns(tbl, mapping) -> tuple[int, int]:
    """
    테이블에서 데이터 열의 physical column 인덱스를 찾기.

    전략: 데이터 행들을 스캔하여 숫자 값이 많은 열을 찾음.
    행별 gridSpan 차이를 고려하여 셀 인덱스 기반으로 탐색 후 대표 phys_col 결정.
    첫 번째 숫자 열 = current year, 두 번째 = prior year.
    """
    rows = findall_w(tbl, "w:tr")
    if len(rows) < 3:
        return -1, -1

    # 셀 인덱스별 숫자 셀 카운트 (행마다 gridSpan이 달라도 셀 인덱스 기준)
    cidx_numeric_counts: dict[int, int] = {}
    cidx_total_counts: dict[int, int] = {}
    cidx_phys_cols: dict[int, list[int]] = {}  # 셀 인덱스 → 등장한 phys_col 목록

    start_row = _find_data_start_row(tbl)
    for ri in range(start_row, min(len(rows), 25)):
        cells = findall_w(rows[ri], "w:tc")
        phys_col = 0
        for ci, tc in enumerate(cells):
            span = _get_grid_span(tc)
            text = get_cell_text(tc).strip()

            # ci=0은 레이블 열, spacer 인덱스도 제외
            if ci > 0 and phys_col not in mapping.spacer_indices:
                cidx_total_counts[ci] = cidx_total_counts.get(ci, 0) + 1
                cidx_phys_cols.setdefault(ci, []).append(phys_col)
                if _is_numeric_cell(text) and text:
                    cidx_numeric_counts[ci] = cidx_numeric_counts.get(ci, 0) + 1

            phys_col += span

    # 숫자 비율이 높은 셀 인덱스 찾기 (70% 이상)
    numeric_cidxs = []
    for ci, total in cidx_total_counts.items():
        if total > 0:
            ratio = cidx_numeric_counts.get(ci, 0) / total
            if ratio >= 0.7:
                # 대표 phys_col: 가장 빈번하게 등장하는 값
                phys_list = cidx_phys_cols.get(ci, [])
                if phys_list:
                    from collections import Counter
                    rep_phys = Counter(phys_list).most_common(1)[0][0]
                else:
                    rep_phys = ci
                numeric_cidxs.append((ci, rep_phys, cidx_numeric_counts.get(ci, 0)))

    # 셀 인덱스 순서로 정렬
    numeric_cidxs.sort(key=lambda x: x[0])

    if len(numeric_cidxs) >= 2:
        return numeric_cidxs[0][1], numeric_cidxs[1][1]
    elif len(numeric_cidxs) == 1:
        return numeric_cidxs[0][1], -1
    return -1, -1


def extract_docx_tables(ctx: DocumentContext) -> list[DocxTableInfo]:
    """DOCX 전체에서 데이터 테이블을 추출."""
    results = []
    tables = ctx.get_tables()

    for ti, tbl in enumerate(tables):
        rows = findall_w(tbl, "w:tr")
        if len(rows) < 3:
            continue

        mapping = build_column_mapping(tbl)
        current_col, prior_col = _find_data_columns(tbl, mapping)

        if current_col < 0:
            continue

        # 데이터 행 추출 (빈 행 건너뜀)
        data_start = _find_data_start_row(tbl)
        row_data = []
        for ri in range(data_start, len(rows)):
            cells = findall_w(rows[ri], "w:tc")

            # 라벨 (physical col 0)
            label = ""
            current_val = None
            prior_val = None

            phys_col = 0
            for tc in cells:
                span = _get_grid_span(tc)
                text = get_cell_text(tc).strip()

                if phys_col == 0:
                    label = text
                elif phys_col == current_col:
                    current_val = _parse_number(text)
                elif phys_col == prior_col:
                    prior_val = _parse_number(text)

                phys_col += span

            # 라벨이 있고 숫자가 있는 행만
            if label and (current_val is not None or prior_val is not None):
                row_data.append(DocxTableRow(
                    label=label,
                    current_val=current_val,
                    prior_val=prior_val,
                    row_idx=ri,
                    current_phys_col=current_col,
                    prior_phys_col=prior_col,
                ))

        if row_data:
            unit = _detect_docx_unit(tbl)
            results.append(DocxTableInfo(
                table_index=ti,
                num_rows=len(rows),
                current_phys_col=current_col,
                prior_phys_col=prior_col,
                rows=row_data,
                spacer_indices=mapping.spacer_indices,
                unit=unit,
            ))

    return results


# ---------------------------------------------------------------------------
# 매칭
# ---------------------------------------------------------------------------

@dataclass
class TableMatch:
    """테이블 매칭 결과."""
    dsd_table: DsdTableInfo
    docx_table: DocxTableInfo
    row_matches: list[tuple[int, int]]  # [(dsd_row_idx, docx_row_idx), ...]
    score: float  # 매칭 점수 (0~1)


def _match_tables(
    dsd_tables: list[DsdTableInfo],
    docx_tables: list[DocxTableInfo],
) -> list[TableMatch]:
    """
    DSD 테이블과 DOCX 테이블을 매칭.

    매칭 기준: DSD 전기 값 == DOCX current_val (= 전기 실제 데이터)
    """
    matches = []
    used_docx = set()

    for dsd_tbl in dsd_tables:
        dsd_unit = dsd_tbl.unit or "천원"

        # 단위별 변환된 전기 값 dict 캐시
        prior_by_unit: dict[str, dict[int, list[int]]] = {}

        best_match = None
        best_score = 0.0
        best_row_matches = []

        for docx_tbl in docx_tables:
            if docx_tbl.table_index in used_docx:
                continue

            docx_unit = docx_tbl.unit or "천원"

            # 해당 DOCX 단위에 맞게 변환된 dict 생성 (캐시)
            if docx_unit not in prior_by_unit:
                d: dict[int, list[int]] = {}
                for drow in dsd_tbl.rows:
                    val = drow.values.get("prior")
                    if val is not None and val != 0:
                        cval = _convert_value(val, dsd_unit, docx_unit)
                        if cval is not None and cval != 0:
                            d.setdefault(cval, []).append(drow.row_idx)
                prior_by_unit[docx_unit] = d

            dsd_prior_values = prior_by_unit[docx_unit]
            if not dsd_prior_values:
                continue

            # DOCX current_val(= 실제 전기 데이터)와 DSD 전기 값 비교
            row_matches = []
            for dxrow in docx_tbl.rows:
                val = dxrow.current_val
                if val is not None and val != 0 and val in dsd_prior_values:
                    for dsd_ri in dsd_prior_values[val]:
                        row_matches.append((dsd_ri, dxrow.row_idx))

            if not row_matches:
                continue

            # 매칭 점수: 매칭된 행 수 / DSD 행 수
            unique_dsd_rows = len(set(rm[0] for rm in row_matches))
            score = unique_dsd_rows / len(dsd_tbl.rows)

            # 최소 1행 매칭 + 50% 이상, 또는 2행 이상 매칭
            if unique_dsd_rows >= 1 and (score >= 0.5 or unique_dsd_rows >= 2):
                if score > best_score:
                    best_score = score
                    best_match = docx_tbl
                    best_row_matches = row_matches

        if best_match is not None and best_score > 0:
            # 중복 제거: 각 DSD row에 대해 가장 좋은 DOCX row만 유지
            cleaned = _deduplicate_row_matches(best_row_matches, dsd_tbl, best_match)
            matches.append(TableMatch(
                dsd_table=dsd_tbl,
                docx_table=best_match,
                row_matches=cleaned,
                score=best_score,
            ))
            used_docx.add(best_match.table_index)

    return matches


def _extract_all_values(rows: list, start_row: int = 0, min_abs: int = 10) -> dict[int, list[tuple[int, int]]]:
    """테이블에서 모든 숫자 값을 추출. {value: [(row_idx, col_idx), ...]}"""
    values: dict[int, list[tuple[int, int]]] = {}
    for ri in range(start_row, len(rows)):
        cells = findall_w(rows[ri], "w:tc")
        phys_col = 0
        for tc in cells:
            span = _get_grid_span(tc)
            text = get_cell_text(tc).strip()
            val = _parse_number(text)
            if val is not None and val != 0 and abs(val) >= min_abs:
                values.setdefault(val, []).append((ri, phys_col))
            phys_col += span
    return values


def _match_tables_pass2(
    dsd_tables: list[DsdTableInfo],
    docx_tables: list[DocxTableInfo],
    used_docx: set[int],
    used_dsd: set[tuple[str, int]],
    ctx: DocumentContext,
) -> list[TableMatch]:
    """
    2차 매칭: ALL values fingerprint 방식.
    DSD 테이블의 모든 숫자 값을 DOCX 테이블의 모든 숫자 값과 비교.
    """
    matches = []

    for dsd_tbl in dsd_tables:
        key = (dsd_tbl.note_number, dsd_tbl.table_idx_in_note)
        if key in used_dsd:
            continue

        dsd_unit = dsd_tbl.unit or "천원"

        best_match = None
        best_score = 0.0
        best_row_matches = []

        # 단위별 변환된 DSD 값 dict 캐시
        dsd_vals_by_unit: dict[str, dict[int, list[int]]] = {}

        for docx_tbl in docx_tables:
            if docx_tbl.table_index in used_docx:
                continue

            docx_unit = docx_tbl.unit or "천원"

            # 해당 DOCX 단위에 맞게 변환된 DSD 값 dict
            if docx_unit not in dsd_vals_by_unit:
                d: dict[int, list[int]] = {}
                for drow in dsd_tbl.rows:
                    for period_key, val in drow.values.items():
                        if val is not None and val != 0 and abs(val) >= 10:
                            cval = _convert_value(val, dsd_unit, docx_unit)
                            if cval is not None and cval != 0 and abs(cval) >= 10:
                                d.setdefault(cval, []).append(drow.row_idx)
                dsd_vals_by_unit[docx_unit] = d

            dsd_all_values = dsd_vals_by_unit[docx_unit]
            if len(dsd_all_values) < 2:
                continue

            # DOCX 테이블의 모든 값 추출
            tbl_elem = ctx.get_table(docx_tbl.table_index)
            docx_rows = findall_w(tbl_elem, "w:tr")
            docx_all_values = _extract_all_values(docx_rows, start_row=2)

            # 교집합
            overlap = set(dsd_all_values.keys()) & set(docx_all_values.keys())
            if len(overlap) < 2:
                continue

            # 행 매칭: 겹치는 값으로 DSD row ↔ DOCX row 매핑
            row_matches = []
            for val in overlap:
                for dsd_ri in dsd_all_values[val]:
                    for docx_ri, docx_ci in docx_all_values[val]:
                        row_matches.append((dsd_ri, docx_ri))

            unique_dsd = len(set(rm[0] for rm in row_matches))
            score = unique_dsd / len(dsd_tbl.rows) if dsd_tbl.rows else 0

            if unique_dsd >= 2 and score > best_score:
                best_score = score
                best_match = docx_tbl
                best_row_matches = row_matches

        if best_match is not None and best_score >= 0.15:
            cleaned = _deduplicate_row_matches(best_row_matches, dsd_tbl, best_match)
            matches.append(TableMatch(
                dsd_table=dsd_tbl,
                docx_table=best_match,
                row_matches=cleaned,
                score=best_score,
            ))
            used_docx.add(best_match.table_index)
            used_dsd.add(key)

    return matches


def _match_tables_pass3(
    dsd_tables: list[DsdTableInfo],
    docx_tables: list[DocxTableInfo],
    used_docx: set[int],
    used_dsd: set[tuple[str, int]],
    ctx: DocumentContext,
) -> list[TableMatch]:
    """
    3차 매칭: 단위 보정 재시도.
    DSD 단위가 잘못 감지되었을 수 있으므로, 다른 단위 가정으로 전기 값 매칭 재시도.
    """
    matches = []
    alt_units = ["원", "천원"]  # 기본 감지와 다른 단위로 재시도

    for dsd_tbl in dsd_tables:
        key = (dsd_tbl.note_number, dsd_tbl.table_idx_in_note)
        if key in used_dsd:
            continue
        # 전기 값이 있는 행이 있어야 함
        has_prior = any(r.values.get("prior") is not None and r.values.get("prior") != 0 for r in dsd_tbl.rows)
        if not has_prior:
            continue

        dsd_unit = dsd_tbl.unit or "원"

        best_match = None
        best_score = 0.0
        best_row_matches = []

        for try_unit in alt_units:
            if try_unit == dsd_unit:
                continue  # 이미 시도한 단위는 건너뜀

            for docx_tbl in docx_tables:
                if docx_tbl.table_index in used_docx:
                    continue

                docx_unit = docx_tbl.unit or "천원"

                # DSD 전기 값을 try_unit 기준으로 변환
                dsd_prior: dict[int, list[int]] = {}
                for drow in dsd_tbl.rows:
                    val = drow.values.get("prior")
                    if val is not None and val != 0:
                        cval = _convert_value(val, try_unit, docx_unit)
                        if cval is not None and cval != 0:
                            dsd_prior.setdefault(cval, []).append(drow.row_idx)

                if not dsd_prior:
                    continue

                row_matches = []
                for dxrow in docx_tbl.rows:
                    val = dxrow.current_val
                    if val is not None and val != 0 and val in dsd_prior:
                        for dsd_ri in dsd_prior[val]:
                            row_matches.append((dsd_ri, dxrow.row_idx))

                if not row_matches:
                    continue

                unique_dsd = len(set(rm[0] for rm in row_matches))
                score = unique_dsd / len(dsd_tbl.rows)

                if unique_dsd >= 1 and (score >= 0.5 or unique_dsd >= 2) and score > best_score:
                    best_score = score
                    best_match = docx_tbl
                    best_row_matches = row_matches
                    # 단위 보정: DSD 테이블의 단위를 업데이트
                    dsd_tbl.unit = try_unit

        if best_match is not None:
            cleaned = _deduplicate_row_matches(best_row_matches, dsd_tbl, best_match)
            matches.append(TableMatch(
                dsd_table=dsd_tbl,
                docx_table=best_match,
                row_matches=cleaned,
                score=best_score,
            ))
            used_docx.add(best_match.table_index)
            used_dsd.add(key)

    return matches


def _match_tables_pass4(
    dsd_tables: list[DsdTableInfo],
    docx_tables: list[DocxTableInfo],
    used_docx: set[int],
    used_dsd: set[tuple[str, int]],
    ctx: DocumentContext,
) -> list[TableMatch]:
    """
    4차 매칭: 단위 보정 + fingerprint 결합.
    Pass3의 단위 보정과 Pass2의 fingerprint를 조합하여
    다른 단위 가정으로 전체 값 fingerprint 매칭.
    """
    matches = []
    alt_units = ["원", "천원"]

    for dsd_tbl in dsd_tables:
        key = (dsd_tbl.note_number, dsd_tbl.table_idx_in_note)
        if key in used_dsd:
            continue

        # 값이 있는 행이 있어야 함
        has_vals = any(
            any(v is not None and v != 0 for v in r.values.values())
            for r in dsd_tbl.rows
        )
        if not has_vals:
            continue

        dsd_unit = dsd_tbl.unit or "원"
        best_match = None
        best_score = 0.0
        best_row_matches = []
        best_unit = dsd_unit

        for try_unit in alt_units:
            if try_unit == dsd_unit:
                continue

            for docx_tbl in docx_tables:
                if docx_tbl.table_index in used_docx:
                    continue

                docx_unit = docx_tbl.unit or "천원"

                # DSD 전체 값을 try_unit 기준으로 변환
                dsd_all: dict[int, list[int]] = {}
                for drow in dsd_tbl.rows:
                    for val in drow.values.values():
                        if val is not None and val != 0 and abs(val) >= 10:
                            cval = _convert_value(val, try_unit, docx_unit)
                            if cval is not None and cval != 0 and abs(cval) >= 10:
                                dsd_all.setdefault(cval, []).append(drow.row_idx)

                if len(dsd_all) < 2:
                    continue

                # DOCX 테이블 전체 값 추출
                tbl_elem = ctx.get_table(docx_tbl.table_index)
                docx_rows = findall_w(tbl_elem, "w:tr")
                docx_all = _extract_all_values(docx_rows, start_row=2, min_abs=10)

                overlap = set(dsd_all.keys()) & set(docx_all.keys())
                if len(overlap) < 2:
                    continue

                row_matches = []
                for val in overlap:
                    for dsd_ri in dsd_all[val]:
                        for docx_ri, _ in docx_all[val]:
                            row_matches.append((dsd_ri, docx_ri))

                unique_dsd = len(set(rm[0] for rm in row_matches))
                score = unique_dsd / len(dsd_tbl.rows) if dsd_tbl.rows else 0

                if unique_dsd >= 2 and score > best_score:
                    best_score = score
                    best_match = docx_tbl
                    best_row_matches = row_matches
                    best_unit = try_unit

        if best_match is not None and best_score >= 0.15:
            dsd_tbl.unit = best_unit
            cleaned = _deduplicate_row_matches(best_row_matches, dsd_tbl, best_match)
            matches.append(TableMatch(
                dsd_table=dsd_tbl,
                docx_table=best_match,
                row_matches=cleaned,
                score=best_score,
            ))
            used_docx.add(best_match.table_index)
            used_dsd.add(key)

    return matches


# ---------------------------------------------------------------------------
# DOCX 섹션 파싱 (ABCTitle heading → 테이블 그룹)
# ---------------------------------------------------------------------------

def _build_docx_sections(ctx: DocumentContext) -> list[tuple[str, list[int]]]:
    """DOCX body에서 ABCTitle heading 기준으로 섹션별 테이블 인덱스를 파싱."""
    body = ctx.docx_doc.element.body
    W_NS = OOXML_NS["w"]

    sections: list[tuple[str, list[int]]] = []
    current_heading = ""
    current_tables: list[int] = []
    table_idx = 0

    for elem in body:
        tag = etree.QName(elem).localname

        if tag == "p":
            pPr = elem.find(f"{{{W_NS}}}pPr")
            if pPr is not None:
                pStyle = pPr.find(f"{{{W_NS}}}pStyle")
                if pStyle is not None:
                    style = pStyle.get(f"{{{W_NS}}}val", "")
                    if style == "ABCTitle":
                        texts = []
                        for t in elem.iter(f"{{{W_NS}}}t"):
                            if t.text:
                                texts.append(t.text)
                        text = "".join(texts).strip()
                        if current_heading or current_tables:
                            sections.append((current_heading, current_tables))
                        current_heading = text
                        current_tables = []

        elif tag == "tbl":
            current_tables.append(table_idx)
            table_idx += 1

    if current_heading or current_tables:
        sections.append((current_heading, current_tables))

    return sections


def _match_tables_pass5(
    dsd_tables: list[DsdTableInfo],
    docx_tables: list[DocxTableInfo],
    all_matches: list[TableMatch],
    used_docx: set[int],
    used_dsd: set[tuple[str, int]],
    ctx: DocumentContext,
) -> list[TableMatch]:
    """
    5차 매칭: DOCX 섹션 기반 위치 매칭.

    기존 매칭 결과로 DSD note → DOCX section 매핑을 확립하고,
    같은 section 내 미매칭 테이블을 순서대로 매칭.
    """
    matches = []

    # 1. DOCX 섹션 파싱
    sections = _build_docx_sections(ctx)

    # 2. DOCX table index → section index 매핑
    docx_ti_to_section: dict[int, int] = {}
    for si, (heading, table_indices) in enumerate(sections):
        for ti in table_indices:
            docx_ti_to_section[ti] = si

    # 3. 기존 매칭으로 DSD note → section 매핑
    note_to_sections: dict[str, set[int]] = {}
    for m in all_matches:
        note_num = m.dsd_table.note_number
        docx_ti = m.docx_table.table_index
        if docx_ti in docx_ti_to_section:
            note_to_sections.setdefault(note_num, set()).add(docx_ti_to_section[docx_ti])

    # 3b. 기존 매칭이 없는 note → note_number 기반 section 추론
    all_note_nums = set(dt.note_number for dt in dsd_tables if (dt.note_number, dt.table_idx_in_note) not in used_dsd)
    for note_num in all_note_nums:
        if note_num in note_to_sections:
            continue
        try:
            inferred_si = int(note_num) - 1
        except ValueError:
            continue
        if 0 <= inferred_si < len(sections):
            note_to_sections[note_num] = {inferred_si}

    # 4. 각 note의 미매칭 DSD 테이블과 해당 section의 미매칭 DOCX 테이블을 위치 매칭
    # DOCX table index → DocxTableInfo 매핑 (추출된 테이블 + 미추출 테이블 보충)
    docx_tbl_by_idx = {dt.table_index: dt for dt in docx_tables}
    all_docx_tbls = ctx.get_tables()

    # 미추출 DOCX 테이블도 lightweight DocxTableInfo로 생성 (Pass5 fallback용)
    for ti, tbl_elem in enumerate(all_docx_tbls):
        if ti in docx_tbl_by_idx:
            continue
        rows = findall_w(tbl_elem, "w:tr")
        if len(rows) < 2:
            continue
        data_start = min(2, len(rows))
        row_data = []
        for ri in range(data_start, len(rows)):
            cells = findall_w(rows[ri], "w:tc")
            if cells:
                label = get_cell_text(cells[0]).strip()
                if label:
                    row_data.append(DocxTableRow(
                        label=label, current_val=None, prior_val=None,
                        row_idx=ri, current_phys_col=-1, prior_phys_col=-1,
                    ))
        if row_data:
            docx_tbl_by_idx[ti] = DocxTableInfo(
                table_index=ti, num_rows=len(rows),
                current_phys_col=-1, prior_phys_col=-1,
                rows=row_data,
            )

    for note_num, section_indices in note_to_sections.items():
        # 이 note의 미매칭 DSD 테이블 (순서대로) — 데이터 유무 관계없이 포함
        unmatched_dsd = [
            dt for dt in dsd_tables
            if dt.note_number == note_num
            and (dt.note_number, dt.table_idx_in_note) not in used_dsd
        ]
        if not unmatched_dsd:
            continue

        # 해당 section들의 미매칭 DOCX 테이블 (순서대로, 미추출 테이블 포함)
        unmatched_docx_indices = []
        for si in sorted(section_indices):
            _, table_indices = sections[si]
            for ti in table_indices:
                if ti not in used_docx and ti in docx_tbl_by_idx:
                    unmatched_docx_indices.append(ti)

        if not unmatched_docx_indices:
            continue

        # Best-fit 매칭: 각 DSD 테이블에 가장 적합한 DOCX 테이블 선택
        local_used_docx: set[int] = set()

        for dsd_tbl in unmatched_dsd:
            dsd_rows = len(dsd_tbl.rows)
            if dsd_rows == 0:
                continue

            best_docx_ti = None
            best_ratio = 0.0

            for docx_ti in unmatched_docx_indices:
                if docx_ti in local_used_docx:
                    continue
                docx_tbl = docx_tbl_by_idx[docx_ti]
                docx_rows = len(docx_tbl.rows)
                if docx_rows == 0:
                    continue
                ratio = min(dsd_rows, docx_rows) / max(dsd_rows, docx_rows)
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_docx_ti = docx_ti

            if best_docx_ti is None or best_ratio < 0.2:
                continue

            docx_tbl = docx_tbl_by_idx[best_docx_ti]
            docx_rows = len(docx_tbl.rows)

            # 행 매칭: 순서대로 1:1
            row_matches = []
            for j in range(min(dsd_rows, docx_rows)):
                dsd_ri = dsd_tbl.rows[j].row_idx
                docx_ri = docx_tbl.rows[j].row_idx
                row_matches.append((dsd_ri, docx_ri))

            key = (dsd_tbl.note_number, dsd_tbl.table_idx_in_note)
            matches.append(TableMatch(
                dsd_table=dsd_tbl,
                docx_table=docx_tbl,
                row_matches=row_matches,
                score=best_ratio,
            ))
            local_used_docx.add(best_docx_ti)
            used_docx.add(best_docx_ti)
            used_dsd.add(key)

    return matches


def _match_tables_pass6(
    dsd_tables: list[DsdTableInfo],
    docx_tables: list[DocxTableInfo],
    used_docx: set[int],
    used_dsd: set[tuple[str, int]],
    ctx: DocumentContext,
) -> list[TableMatch]:
    """
    6차 매칭: DSD 당기(current) 값 기반.

    전기 값이 없고 당기 값만 있는 DSD 테이블을 위한 매칭.
    DSD 당기 값을 DOCX 테이블의 모든 값과 비교하여 fingerprint 매칭.
    (이런 테이블은 전기에 해당 항목이 없거나, 단일 기간 테이블임)
    """
    matches = []

    for dsd_tbl in dsd_tables:
        key = (dsd_tbl.note_number, dsd_tbl.table_idx_in_note)
        if key in used_dsd:
            continue

        # 전기 값이 있으면 이미 이전 pass에서 시도됨 → skip
        has_prior = any(
            r.values.get("prior") is not None and r.values.get("prior") != 0
            for r in dsd_tbl.rows
        )
        if has_prior:
            continue

        # 당기 값만 추출
        dsd_unit = dsd_tbl.unit or "천원"
        cur_vals: dict[int, list[int]] = {}
        for drow in dsd_tbl.rows:
            val = drow.values.get("current")
            if val is not None and val != 0 and abs(val) >= 100:
                cur_vals.setdefault(val, []).append(drow.row_idx)

        if len(cur_vals) < 2:
            continue

        best_match = None
        best_score = 0.0
        best_row_matches = []

        for docx_tbl in docx_tables:
            if docx_tbl.table_index in used_docx:
                continue

            docx_unit = docx_tbl.unit or "천원"

            # DOCX 테이블의 모든 값 추출
            tbl_elem = ctx.get_table(docx_tbl.table_index)
            docx_rows = findall_w(tbl_elem, "w:tr")
            docx_all = _extract_all_values(docx_rows, start_row=2, min_abs=100)

            # DSD 당기 값을 DOCX 단위로 변환하여 비교
            overlap_count = 0
            row_matches = []
            for val, dsd_ris in cur_vals.items():
                cval = _convert_value(val, dsd_unit, docx_unit)
                if cval is not None and cval in docx_all:
                    overlap_count += 1
                    for dsd_ri in dsd_ris:
                        for docx_ri, _ in docx_all[cval]:
                            row_matches.append((dsd_ri, docx_ri))

            if overlap_count < 2:
                continue

            unique_dsd = len(set(rm[0] for rm in row_matches))
            score = unique_dsd / len(dsd_tbl.rows) if dsd_tbl.rows else 0

            if unique_dsd >= 2 and score > best_score:
                best_score = score
                best_match = docx_tbl
                best_row_matches = row_matches

        if best_match is not None and best_score >= 0.15:
            cleaned = _deduplicate_row_matches(best_row_matches, dsd_tbl, best_match)
            matches.append(TableMatch(
                dsd_table=dsd_tbl,
                docx_table=best_match,
                row_matches=cleaned,
                score=best_score,
            ))
            used_docx.add(best_match.table_index)
            used_dsd.add(key)

    return matches


def _deduplicate_row_matches(
    raw_matches: list[tuple[int, int]],
    dsd_tbl: DsdTableInfo,
    docx_tbl: DocxTableInfo,
) -> list[tuple[int, int]]:
    """중복 매칭 제거. 각 DSD row와 DOCX row는 한 번만 매칭."""
    # DSD row별로 그룹핑
    dsd_to_docx: dict[int, list[int]] = {}
    for dsd_ri, docx_ri in raw_matches:
        dsd_to_docx.setdefault(dsd_ri, []).append(docx_ri)

    used_docx_rows = set()
    result = []

    # DSD 행 순서대로 처리
    for dsd_ri in sorted(dsd_to_docx.keys()):
        candidates = [dr for dr in dsd_to_docx[dsd_ri] if dr not in used_docx_rows]
        if candidates:
            # 가장 가까운 위치의 DOCX row 선택
            best = min(candidates)
            result.append((dsd_ri, best))
            used_docx_rows.add(best)

    return result


# ---------------------------------------------------------------------------
# 데이터 채우기
# ---------------------------------------------------------------------------

@dataclass
class FillResult:
    """채우기 결과."""
    table_index: int
    note_number: str
    note_title: str
    cells_updated: int
    cells_skipped: int
    errors: list[str] = field(default_factory=list)


def _get_cell_by_target_col(ctx: DocumentContext, table_index: int, row_idx: int, target_phys_col: int):
    """
    행 단위로 physical column 위치를 동적 계산하여 셀을 찾기.

    행마다 gridSpan이 다를 수 있으므로 target_phys_col과 가장 가까운 셀을 반환.
    """
    rows = ctx.get_table_rows(table_index)
    if not (0 <= row_idx < len(rows)):
        raise IndexError(f"Row {row_idx} out of range")

    cells = findall_w(rows[row_idx], "w:tc")
    phys_col = 0
    best_tc = None
    best_dist = float("inf")

    for tc in cells:
        span = _get_grid_span(tc)
        # 범위 매칭
        if phys_col <= target_phys_col < phys_col + span:
            return tc
        dist = min(abs(phys_col - target_phys_col), abs(phys_col + span - 1 - target_phys_col))
        if dist < best_dist:
            best_dist = dist
            best_tc = tc
        phys_col += span

    if best_tc is not None and best_dist <= 2:
        return best_tc
    raise IndexError(f"Column {target_phys_col} not found in row {row_idx}")


def _fill_matched_table(
    ctx: DocumentContext,
    match: TableMatch,
) -> FillResult:
    """매칭된 테이블에 DSD 데이터를 채움. 행 단위 동적 phys_col 계산."""
    docx_tbl = match.docx_table
    dsd_tbl = match.dsd_table

    result = FillResult(
        table_index=docx_tbl.table_index,
        note_number=dsd_tbl.note_number,
        note_title=dsd_tbl.note_title,
        cells_updated=0,
        cells_skipped=0,
    )

    # 단위 변환
    dsd_unit = dsd_tbl.unit or "천원"
    docx_unit = docx_tbl.unit or "천원"

    # DSD row index → DsdTableRow 매핑
    dsd_row_map = {r.row_idx: r for r in dsd_tbl.rows}

    for dsd_ri, docx_ri in match.row_matches:
        dsd_row = dsd_row_map.get(dsd_ri)
        if dsd_row is None:
            continue

        # 현재연도 열에 DSD 당기 값 쓰기
        if "current" in dsd_row.values and docx_tbl.current_phys_col >= 0:
            raw = dsd_row.values["current"]
            converted = _convert_value(raw, dsd_unit, docx_unit)
            new_val = _format_number(converted)
            try:
                tc = _get_cell_by_target_col(ctx, docx_tbl.table_index, docx_ri, docx_tbl.current_phys_col)
                existing = get_cell_text(tc).strip()
                # 레이블 보호
                if _is_numeric_cell(existing):
                    _set_cell_text(tc, new_val)
                    result.cells_updated += 1
                else:
                    result.cells_skipped += 1
            except (IndexError, Exception) as e:
                result.errors.append(f"R{docx_ri}C{docx_tbl.current_phys_col}: {e}")

        # 전기연도 열에 DSD 전기 값 쓰기
        if "prior" in dsd_row.values and docx_tbl.prior_phys_col >= 0:
            raw = dsd_row.values["prior"]
            converted = _convert_value(raw, dsd_unit, docx_unit)
            new_val = _format_number(converted)
            try:
                tc = _get_cell_by_target_col(ctx, docx_tbl.table_index, docx_ri, docx_tbl.prior_phys_col)
                existing = get_cell_text(tc).strip()
                if _is_numeric_cell(existing):
                    _set_cell_text(tc, new_val)
                    result.cells_updated += 1
                else:
                    result.cells_skipped += 1
            except (IndexError, Exception) as e:
                result.errors.append(f"R{docx_ri}C{docx_tbl.prior_phys_col}: {e}")

    # 합계 검증 및 수정
    _verify_and_fix_totals(ctx, match, result, dsd_unit, docx_unit)

    return result


def _verify_and_fix_totals(
    ctx: DocumentContext,
    match: TableMatch,
    result: FillResult,
    dsd_unit: str,
    docx_unit: str,
) -> None:
    """채워진 테이블의 합계/소계 행이 DSD 값과 일치하는지 검증. 불일치 시 강제 덮어쓰기."""
    docx_tbl = match.docx_table
    dsd_tbl = match.dsd_table
    dsd_row_map = {r.row_idx: r for r in dsd_tbl.rows}

    for dsd_ri, docx_ri in match.row_matches:
        dsd_row = dsd_row_map.get(dsd_ri)
        if dsd_row is None or not (dsd_row.is_total or dsd_row.is_subtotal):
            continue

        # 당기 합계 검증
        if "current" in dsd_row.values and docx_tbl.current_phys_col >= 0:
            expected = _convert_value(dsd_row.values["current"], dsd_unit, docx_unit)
            try:
                tc = _get_cell_by_target_col(ctx, docx_tbl.table_index, docx_ri, docx_tbl.current_phys_col)
                actual_text = get_cell_text(tc).strip()
                actual = _parse_number(actual_text)
                if expected is not None and actual is not None and abs(expected - actual) > 1:
                    _set_cell_text(tc, _format_number(expected))
                    result.cells_updated += 1
            except Exception:
                pass

        # 전기 합계 검증
        if "prior" in dsd_row.values and docx_tbl.prior_phys_col >= 0:
            expected = _convert_value(dsd_row.values["prior"], dsd_unit, docx_unit)
            try:
                tc = _get_cell_by_target_col(ctx, docx_tbl.table_index, docx_ri, docx_tbl.prior_phys_col)
                actual_text = get_cell_text(tc).strip()
                actual = _parse_number(actual_text)
                if expected is not None and actual is not None and abs(expected - actual) > 1:
                    _set_cell_text(tc, _format_number(expected))
                    result.cells_updated += 1
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 매칭 안 된 행도 위치 기반으로 채우기 (보조)
# ---------------------------------------------------------------------------

def _fill_unmatched_by_position(
    ctx: DocumentContext,
    match: TableMatch,
    already_filled_docx_rows: set[int],
) -> FillResult:
    """
    값 매칭이 안 된 행을 위치 순서로 채우기.
    매칭된 행 사이의 빈 행을 순서대로 매핑.
    """
    docx_tbl = match.docx_table
    dsd_tbl = match.dsd_table

    result = FillResult(
        table_index=docx_tbl.table_index,
        note_number=dsd_tbl.note_number,
        note_title=dsd_tbl.note_title,
        cells_updated=0,
        cells_skipped=0,
    )

    # 매칭 안 된 DSD 행
    matched_dsd_rows = set(rm[0] for rm in match.row_matches)
    unmatched_dsd = [r for r in dsd_tbl.rows if r.row_idx not in matched_dsd_rows]

    # 매칭 안 된 DOCX 행 (데이터 행 중)
    unmatched_docx = [r for r in docx_tbl.rows if r.row_idx not in already_filled_docx_rows]

    # 순서대로 1:1 매핑 (행 수가 같거나 비슷할 때만)
    if not unmatched_dsd or not unmatched_docx:
        return result

    # 행 수 차이가 너무 크면 skip
    if abs(len(unmatched_dsd) - len(unmatched_docx)) > max(3, len(unmatched_dsd) * 0.5):
        return result

    # 단위 변환
    dsd_unit = dsd_tbl.unit or "천원"
    docx_unit = docx_tbl.unit or "천원"

    for i, docx_row in enumerate(unmatched_docx):
        if i >= len(unmatched_dsd):
            break

        dsd_row = unmatched_dsd[i]

        # 현재연도 열
        if "current" in dsd_row.values and docx_tbl.current_phys_col >= 0:
            raw = dsd_row.values["current"]
            converted = _convert_value(raw, dsd_unit, docx_unit)
            new_val = _format_number(converted)
            try:
                tc = _get_cell_by_target_col(ctx, docx_tbl.table_index, docx_row.row_idx, docx_tbl.current_phys_col)
                existing = get_cell_text(tc).strip()
                if _is_numeric_cell(existing):
                    _set_cell_text(tc, new_val)
                    result.cells_updated += 1
                else:
                    result.cells_skipped += 1
            except Exception as e:
                result.errors.append(f"pos R{docx_row.row_idx}C{docx_tbl.current_phys_col}: {e}")

        # 전기연도 열
        if "prior" in dsd_row.values and docx_tbl.prior_phys_col >= 0:
            raw = dsd_row.values["prior"]
            converted = _convert_value(raw, dsd_unit, docx_unit)
            new_val = _format_number(converted)
            try:
                tc = _get_cell_by_target_col(ctx, docx_tbl.table_index, docx_row.row_idx, docx_tbl.prior_phys_col)
                existing = get_cell_text(tc).strip()
                if _is_numeric_cell(existing):
                    _set_cell_text(tc, new_val)
                    result.cells_updated += 1
                else:
                    result.cells_skipped += 1
            except Exception as e:
                result.errors.append(f"pos R{docx_row.row_idx}C{docx_tbl.prior_phys_col}: {e}")

    return result


# ---------------------------------------------------------------------------
# Glossary 자동 추출
# ---------------------------------------------------------------------------

def extract_glossary(
    ctx: DocumentContext,
    matches: list[TableMatch],
) -> dict[str, str]:
    """
    매칭된 테이블에서 한→영 라벨 대응(glossary)을 자동 추출.

    DSD 행의 한국어 라벨 ↔ DOCX 같은 행의 영어 라벨.
    """
    glossary: dict[str, str] = {}
    tables = ctx.get_tables()

    for match in matches:
        docx_idx = match.docx_table.table_index
        if docx_idx >= len(tables):
            continue
        tbl = tables[docx_idx]
        docx_rows = findall_w(tbl, "w:tr")

        # DSD row_idx → label 매핑
        dsd_label_map = {r.row_idx: r.label for r in match.dsd_table.rows}

        for dsd_ri, docx_ri in match.row_matches:
            ko_label = dsd_label_map.get(dsd_ri, "").strip()
            if not ko_label or docx_ri >= len(docx_rows):
                continue

            # DOCX 행의 첫 번째 셀 = 영문 라벨
            cells = findall_w(docx_rows[docx_ri], "w:tc")
            if not cells:
                continue
            en_label = get_cell_text(cells[0]).strip()

            # 숫자나 빈 값은 건너뜀
            if not en_label or en_label in ("-", "—", "–"):
                continue
            if _is_numeric_cell(en_label) and en_label.replace(",", "").replace("(", "").replace(")", "").replace("-", "").strip().isdigit():
                continue

            # 같은 텍스트면 건너뜀 (번역이 아님)
            if ko_label == en_label:
                continue

            glossary[ko_label] = en_label

    return glossary


# ---------------------------------------------------------------------------
# 메인 함수
# ---------------------------------------------------------------------------

def apply_note_filling(
    ctx: DocumentContext,
    dsd_data,
    log_callback=None,
) -> dict:
    """
    DSD 주석 데이터를 DOCX 테이블에 자동 채우기.

    Returns: 통계 dict
    """
    def _log(msg):
        if log_callback:
            log_callback({
                "type": "log",
                "level": "info",
                "message": msg,
                "step": 0,
                "timestamp": "",
            })

    stats = {
        "dsd_tables_found": 0,
        "docx_tables_found": 0,
        "tables_matched": 0,
        "cells_updated": 0,
        "cells_skipped": 0,
        "errors": 0,
        "match_details": [],
    }

    # 1. DSD 테이블 추출
    _log("주석 자동 채우기: DSD 테이블 추출 중...")
    dsd_tables = extract_dsd_tables(dsd_data)
    stats["dsd_tables_found"] = len(dsd_tables)
    _log(f"DSD 테이블 {len(dsd_tables)}개 추출")

    if not dsd_tables:
        _log("DSD에 처리 가능한 테이블이 없습니다.")
        return stats

    # 2. DOCX 테이블 추출
    _log("주석 자동 채우기: DOCX 테이블 추출 중...")
    docx_tables = extract_docx_tables(ctx)
    stats["docx_tables_found"] = len(docx_tables)
    _log(f"DOCX 데이터 테이블 {len(docx_tables)}개 추출")

    if not docx_tables:
        _log("DOCX에 데이터 테이블이 없습니다.")
        return stats

    # 3. 1차 매칭 (DSD 전기 값 == DOCX 현재열 값)
    _log("주석 자동 채우기: 1차 매칭 중 (전기 값 기반)...")
    matches = _match_tables(dsd_tables, docx_tables)
    _log(f"1차 매칭 {len(matches)}개 완료")

    # 3b. 2차 매칭 (전체 값 fingerprint)
    used_docx = set(m.docx_table.table_index for m in matches)
    used_dsd = set((m.dsd_table.note_number, m.dsd_table.table_idx_in_note) for m in matches)
    _log("주석 자동 채우기: 2차 매칭 중 (전체 값 fingerprint)...")
    pass2_matches = _match_tables_pass2(dsd_tables, docx_tables, used_docx, used_dsd, ctx)
    matches.extend(pass2_matches)
    used_docx.update(m.docx_table.table_index for m in pass2_matches)
    used_dsd.update((m.dsd_table.note_number, m.dsd_table.table_idx_in_note) for m in pass2_matches)
    _log(f"2차 매칭 {len(pass2_matches)}개 추가 (총 {len(matches)}개)")

    # 3c. 3차 매칭 (단위 보정 재시도)
    _log("주석 자동 채우기: 3차 매칭 중 (단위 보정)...")
    pass3_matches = _match_tables_pass3(dsd_tables, docx_tables, used_docx, used_dsd, ctx)
    matches.extend(pass3_matches)
    used_docx.update(m.docx_table.table_index for m in pass3_matches)
    used_dsd.update((m.dsd_table.note_number, m.dsd_table.table_idx_in_note) for m in pass3_matches)
    _log(f"3차 매칭 {len(pass3_matches)}개 추가 (총 {len(matches)}개)")

    # 3d. 4차 매칭 (단위 보정 + fingerprint 결합)
    _log("주석 자동 채우기: 4차 매칭 중 (단위+fingerprint 결합)...")
    pass4_matches = _match_tables_pass4(dsd_tables, docx_tables, used_docx, used_dsd, ctx)
    matches.extend(pass4_matches)
    used_docx.update(m.docx_table.table_index for m in pass4_matches)
    used_dsd.update((m.dsd_table.note_number, m.dsd_table.table_idx_in_note) for m in pass4_matches)
    _log(f"4차 매칭 {len(pass4_matches)}개 추가 (총 {len(matches)}개)")

    # 3e. 5차 매칭 (DOCX 섹션 기반 위치 매칭)
    _log("주석 자동 채우기: 5차 매칭 중 (섹션 위치 기반)...")
    pass5_matches = _match_tables_pass5(dsd_tables, docx_tables, matches, used_docx, used_dsd, ctx)
    matches.extend(pass5_matches)
    used_docx.update(m.docx_table.table_index for m in pass5_matches)
    used_dsd.update((m.dsd_table.note_number, m.dsd_table.table_idx_in_note) for m in pass5_matches)
    _log(f"5차 매칭 {len(pass5_matches)}개 추가 (총 {len(matches)}개)")

    # 3f. 6차 매칭 (DSD 당기 값 기반 — 전기 없는 테이블)
    _log("주석 자동 채우기: 6차 매칭 중 (당기 값 기반)...")
    pass6_matches = _match_tables_pass6(dsd_tables, docx_tables, used_docx, used_dsd, ctx)
    matches.extend(pass6_matches)
    _log(f"6차 매칭 {len(pass6_matches)}개 추가 (총 {len(matches)}개)")

    stats["tables_matched"] = len(matches)

    # 4. 데이터 채우기
    for match in matches:
        _log(f"채우기: 주석 {match.dsd_table.note_number} ({match.dsd_table.note_title}) → DOCX Table {match.docx_table.table_index} (score={match.score:.2f}, rows={len(match.row_matches)})")

        # 값 매칭된 행 먼저 채우기
        fill_result = _fill_matched_table(ctx, match)

        # 매칭 안 된 행 위치 기반 채우기
        filled_docx_rows = set(rm[1] for rm in match.row_matches)
        pos_result = _fill_unmatched_by_position(ctx, match, filled_docx_rows)

        total_updated = fill_result.cells_updated + pos_result.cells_updated
        total_skipped = fill_result.cells_skipped + pos_result.cells_skipped
        total_errors = fill_result.errors + pos_result.errors

        stats["cells_updated"] += total_updated
        stats["cells_skipped"] += total_skipped
        stats["errors"] += len(total_errors)

        detail = {
            "note": f"{match.dsd_table.note_number}: {match.dsd_table.note_title}",
            "docx_table": match.docx_table.table_index,
            "score": round(match.score, 2),
            "value_matched_rows": len(match.row_matches),
            "cells_updated": total_updated,
            "cells_skipped": total_skipped,
        }
        if total_errors:
            detail["errors"] = total_errors[:5]
        stats["match_details"].append(detail)

        level = "success" if not total_errors else "warning"
        if log_callback:
            log_callback({
                "type": "log",
                "level": level,
                "message": f"주석 {match.dsd_table.note_number}: {total_updated}셀 업데이트, {total_skipped}셀 스킵" +
                           (f", {len(total_errors)}건 에러" if total_errors else ""),
                "step": 0,
                "timestamp": "",
            })

    # 5. Glossary 자동 추출
    glossary = extract_glossary(ctx, matches)
    stats["glossary"] = glossary
    _log(f"주석 자동 채우기 완료 — {stats['tables_matched']}개 테이블, {stats['cells_updated']}셀 업데이트, glossary {len(glossary)}쌍")

    return stats, matches

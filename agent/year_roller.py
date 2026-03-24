"""
연도 롤링 — 코드 기반 자동 처리.

DSD 기간 정보를 바탕으로 DOCX의 재무제표 기간 표현을 일괄 업데이트.
분기/반기/연간 모두 지원.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent.document_context import DocumentContext
from agent.tools.docx_ops.text_replacer import replace_text_in_element
from agent.tools.docx_ops.xml_helpers import findall_w, w


# 월 이름 매핑
MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}

# 한국어 기 표현 패턴 (제21기, 제21(당)기 등)
KO_PERIOD_RE = re.compile(r"제(\d+)")


@dataclass
class PeriodInfo:
    """기간 정보."""
    year: int
    month: int
    day: int

    @classmethod
    def from_dsd_period(cls, period_str: str) -> PeriodInfo:
        """DSD 기간 문자열 파싱. '2025.12.31' 또는 '2025' 형식."""
        parts = period_str.split(".")
        if len(parts) == 3:
            return cls(year=int(parts[0]), month=int(parts[1]), day=int(parts[2]))
        elif len(parts) == 1:
            return cls(year=int(parts[0]), month=12, day=31)
        raise ValueError(f"Unknown period format: {period_str}")

    @property
    def en_date(self) -> str:
        """English date: 'December 31, 2025'"""
        return f"{MONTH_NAMES[self.month]} {self.day}, {self.year}"

    @property
    def en_date_no_comma(self) -> str:
        """English date without comma: 'December 31 2025'"""
        return f"{MONTH_NAMES[self.month]} {self.day} {self.year}"

    @property
    def year_ended(self) -> str:
        """'Year ended December 31, 2025'"""
        return f"Year ended {self.en_date}"

    @property
    def year_ended_lower(self) -> str:
        """'year ended December 31, 2025'"""
        return f"year ended {self.en_date}"


def build_replacements(dsd_data) -> list[tuple[str, str]]:
    """
    DSD 데이터에서 연도 롤링 교체 쌍을 생성.

    DOCX = 전기 보고서 (prior year report)
    DSD = 당기 데이터 (current year data)

    DOCX 내의 전기(prior) 날짜 → 당기(current) 날짜로 교체
    DOCX 내의 전전기(prior-prior) 날짜 → 전기(prior) 날짜로 교체

    교체 순서: 긴 문자열부터 (cascade 방지)
    """
    if dsd_data is None:
        return []

    meta = dsd_data.meta
    # DSD에서 결산일 추출
    fs_list = dsd_data.get_financial_statements()
    if fs_list and fs_list[0].periods:
        current = PeriodInfo.from_dsd_period(fs_list[0].periods[0])
    else:
        current = PeriodInfo(year=int(meta.period_current), month=12, day=31)

    prior = PeriodInfo(year=current.year - 1, month=current.month, day=current.day)
    prior_prior = PeriodInfo(year=current.year - 2, month=current.month, day=current.day)

    # 기초 날짜 (1월 1일)
    current_begin = PeriodInfo(year=current.year, month=1, day=1)
    prior_begin = PeriodInfo(year=prior.year, month=1, day=1)
    prior_prior_begin = PeriodInfo(year=prior_prior.year, month=1, day=1)

    replacements: list[tuple[str, str]] = []

    # -- 긴 패턴부터 (cascade 방지) --

    # "Year ended December 31, 2023" → "Year ended December 31, 2024"
    replacements.append((prior_prior.year_ended, prior.year_ended))
    replacements.append((prior_prior.year_ended_lower, prior.year_ended_lower))
    # "Year ended December 31, 2024" → "Year ended December 31, 2025"
    replacements.append((prior.year_ended, current.year_ended))
    replacements.append((prior.year_ended_lower, current.year_ended_lower))

    # "January 1, 2023" → "January 1, 2024" (기초)
    replacements.append((prior_prior_begin.en_date, prior_begin.en_date))
    # "January 1, 2024" → "January 1, 2025"
    replacements.append((prior_begin.en_date, current_begin.en_date))

    # "December 31, 2022" → "December 31, 2023" (전전기말)
    replacements.append((prior_prior.en_date, prior.en_date))
    # "December 31, 2023" → "December 31, 2024" (전기말 → 당기말로는 아님, 전전기→전기)
    # 주의: DOCX 전기 보고서에서 "December 31, 2023"은 전전기말, "December 31, 2024"는 전기말
    # 롤링: 2023→2024, 2024→2025
    replacements.append((prior.en_date, current.en_date))

    # 콤마 없는 버전도 처리
    replacements.append((prior_prior.en_date_no_comma, prior.en_date_no_comma))
    replacements.append((prior.en_date_no_comma, current.en_date_no_comma))

    # 분기 재무제표 대응: 결산월이 12월이 아닌 경우 중간기간 날짜도 처리
    if current.month != 12:
        # 예: 3월 31일 결산 → "March 31, 2024" → "March 31, 2025"
        # 이미 위에서 처리됨 (en_date)
        pass

    # 순수 연도 (테이블 헤더용): "2023" → "2024", "2024" → "2025"
    # 주의: 이것은 테이블 헤더에서만 적용 (본문에는 2023이 회사 설립년도 등에 쓰일 수 있음)
    replacements.append((str(prior_prior.year), str(prior.year)))
    replacements.append((str(prior.year), str(current.year)))

    return replacements


def apply_year_rolling(ctx: DocumentContext, dsd_data, log_callback=None) -> dict:
    """
    DOCX 전체에 연도 롤링을 적용.

    Returns: 통계 dict
    """
    replacements = build_replacements(dsd_data)
    if not replacements:
        return {"status": "skipped", "reason": "No DSD data"}

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
        "headers_footers": 0,
        "table_headers": 0,
        "paragraphs": 0,
        "total_elements": 0,
    }

    # 교체 쌍에서 순수 연도만 분리 (테이블/헤더에만 적용)
    year_only = [(o, n) for o, n in replacements if re.fullmatch(r"\d{4}", o)]
    date_repls = [(o, n) for o, n in replacements if not re.fullmatch(r"\d{4}", o)]

    # 본문 문단용: 날짜 패턴 + 문맥 있는 연도 패턴 (설립년도 등 보호)
    # "and 2023" → "and 2024", "(2023:" → "(2024:" 등
    para_repls = list(date_repls)
    for old_year, new_year in year_only:
        para_repls.append((f"and {old_year}", f"and {new_year}"))
        para_repls.append((f"({old_year}:", f"({new_year}:"))
        para_repls.append((f"({old_year} ", f"({new_year} "))
        para_repls.append((f"{old_year},", f"{new_year},"))
        para_repls.append((f"{old_year}.", f"{new_year}."))

    _log(f"연도 롤링 시작 — {len(replacements)}개 교체 패턴")

    # 1. 헤더/푸터: 모든 교체 적용
    for header in ctx.headers:
        if replace_text_in_element(header, replacements):
            stats["headers_footers"] += 1
    for footer in ctx.footers:
        if replace_text_in_element(footer, replacements):
            stats["headers_footers"] += 1
    _log(f"헤더/푸터: {stats['headers_footers']}개 수정")

    # 2. 테이블 헤더 (처음 3행): 모든 교체 적용 (연도 포함)
    tables = ctx.get_tables()
    for tbl in tables:
        rows = findall_w(tbl, "w:tr")
        header_rows = rows[:min(3, len(rows))]
        for row in header_rows:
            if replace_text_in_element(row, replacements):
                stats["table_headers"] += 1
    _log(f"테이블 헤더: {stats['table_headers']}행 수정")

    # 3. 본문 문단: 날짜 패턴 + 문맥 연도 패턴 적용 (순수 연도는 제외 — 설립년도 등 보호)
    # 주의: p.getparent()가 아닌 p 자체를 전달 — body를 전달하면 테이블 내부 문단까지
    # 재처리되어 step 2와 cross-step cascade 발생
    paragraphs = ctx.get_paragraphs()
    for p in paragraphs:
        if replace_text_in_element(p, para_repls):
            stats["paragraphs"] += 1
    _log(f"본문 문단: {stats['paragraphs']}개 수정")

    stats["total_elements"] = (
        stats["headers_footers"] + stats["table_headers"] + stats["paragraphs"]
    )
    _log(f"연도 롤링 완료 — 총 {stats['total_elements']}개 요소 수정")

    return stats

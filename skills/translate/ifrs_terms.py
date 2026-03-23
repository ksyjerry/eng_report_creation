"""
ifrs_terms.py — Comprehensive Korean→English IFRS accounting terminology dictionary.

Contains 200+ terms covering balance sheet, income statement, cash flow,
equity, notes, and accounting policy terminology.
"""

from __future__ import annotations


# ──────────────────────────────────────────────
# IFRS Korean → English term dictionary
# ──────────────────────────────────────────────

IFRS_TERMS: dict[str, str] = {
    # ═══════════════════════════════════════════
    # Balance Sheet — Assets (자산)
    # ═══════════════════════════════════════════
    "자산총계": "Total assets",
    "자산 총계": "Total assets",
    "자산합계": "Total assets",
    "유동자산": "Current assets",
    "비유동자산": "Non-current assets",
    "현금및현금성자산": "Cash and cash equivalents",
    "현금 및 현금성자산": "Cash and cash equivalents",
    "단기금융상품": "Short-term financial instruments",
    "장기금융상품": "Long-term financial instruments",
    "매출채권": "Trade receivables",
    "매출채권 및 기타채권": "Trade and other receivables",
    "매출채권및기타채권": "Trade and other receivables",
    "기타채권": "Other receivables",
    "기타유동자산": "Other current assets",
    "기타비유동자산": "Other non-current assets",
    "기타금융자산": "Other financial assets",
    "유동 기타금융자산": "Current other financial assets",
    "비유동 기타금융자산": "Non-current other financial assets",
    "기타자산": "Other assets",
    "재고자산": "Inventories",
    "선급금": "Advance payments",
    "선급비용": "Prepaid expenses",
    "미수금": "Accounts receivable - other",
    "미수수익": "Accrued income",
    "보증금": "Deposits",
    "당기법인세자산": "Current income tax assets",

    # Investments
    "당기손익-공정가치 측정 금융자산": "Financial assets at fair value through profit or loss",
    "당기손익-공정가치측정금융자산": "Financial assets at fair value through profit or loss",
    "당기손익-공정가치 금융자산": "Financial assets at FVTPL",
    "기타포괄손익-공정가치 측정 금융자산": "Financial assets at fair value through other comprehensive income",
    "기타포괄손익-공정가치측정금융자산": "Financial assets at fair value through other comprehensive income",
    "기타포괄손익-공정가치 금융자산": "Financial assets at FVOCI",
    "상각후원가 측정 금융자산": "Financial assets at amortized cost",
    "상각후원가측정금융자산": "Financial assets at amortized cost",
    "관계기업투자": "Investments in associates",
    "관계기업 투자": "Investments in associates",
    "관계기업및공동기업투자": "Investments in associates and joint ventures",
    "관계기업 및 공동기업 투자": "Investments in associates and joint ventures",
    "종속기업투자": "Investments in subsidiaries",
    "종속기업 투자": "Investments in subsidiaries",
    "공동기업투자": "Investments in joint ventures",
    "공동기업 투자": "Investments in joint ventures",
    "장기투자증권": "Long-term investment securities",

    # Property, Plant & Equipment
    "유형자산": "Property, plant and equipment",
    "유형 자산": "Property, plant and equipment",
    "토지": "Land",
    "건물": "Buildings",
    "구축물": "Structures",
    "기계장치": "Machinery",
    "기계 장치": "Machinery",
    "차량운반구": "Vehicles",
    "공구와기구": "Tools and equipment",
    "비품": "Furniture and fixtures",
    "건설중인자산": "Construction in progress",
    "건설중인 자산": "Construction in progress",

    # Intangible Assets
    "무형자산": "Intangible assets",
    "무형 자산": "Intangible assets",
    "영업권": "Goodwill",
    "산업재산권": "Industrial property rights",
    "개발비": "Development costs",
    "소프트웨어": "Software",
    "회원권": "Memberships",
    "기타의무형자산": "Other intangible assets",
    "기타 무형자산": "Other intangible assets",

    # Right-of-use / Investment Property
    "사용권자산": "Right-of-use assets",
    "투자부동산": "Investment property",
    "이연법인세자산": "Deferred tax assets",

    # ═══════════════════════════════════════════
    # Balance Sheet — Liabilities (부채)
    # ═══════════════════════════════════════════
    "부채총계": "Total liabilities",
    "부채 총계": "Total liabilities",
    "부채합계": "Total liabilities",
    "유동부채": "Current liabilities",
    "비유동부채": "Non-current liabilities",
    "매입채무": "Trade payables",
    "매입채무 및 기타채무": "Trade and other payables",
    "매입채무및기타채무": "Trade and other payables",
    "기타채무": "Other payables",
    "미지급금": "Accounts payable - other",
    "미지급비용": "Accrued expenses",
    "선수금": "Advances received",
    "예수금": "Withholdings",
    "선수수익": "Deferred revenue",
    "이연수익": "Deferred revenue",
    "유동성장기부채": "Current portion of long-term borrowings",
    "단기차입금": "Short-term borrowings",
    "장기차입금": "Long-term borrowings",
    "차입금": "Borrowings",
    "사채": "Bonds payable",
    "전환사채": "Convertible bonds",
    "교환사채": "Exchangeable bonds",
    "신주인수권부사채": "Bonds with warrants",
    "기타금융부채": "Other financial liabilities",
    "유동 기타금융부채": "Current other financial liabilities",
    "비유동 기타금융부채": "Non-current other financial liabilities",
    "기타부채": "Other liabilities",
    "기타유동부채": "Other current liabilities",
    "기타비유동부채": "Other non-current liabilities",
    "충당부채": "Provisions",
    "충당 부채": "Provisions",
    "당기법인세부채": "Current income tax liabilities",
    "이연법인세부채": "Deferred tax liabilities",
    "리스부채": "Lease liabilities",
    "유동 리스부채": "Current lease liabilities",
    "비유동 리스부채": "Non-current lease liabilities",

    # Employee Benefits
    "퇴직급여부채": "Employee benefit liabilities",
    "퇴직급여채무": "Employee benefit obligations",
    "확정급여부채": "Defined benefit liability",
    "확정급여채무": "Defined benefit obligation",
    "순확정급여부채": "Net defined benefit liability",
    "순확정급여자산": "Net defined benefit asset",
    "사외적립자산": "Plan assets",
    "확정기여형퇴직급여": "Defined contribution expense",

    # ═══════════════════════════════════════════
    # Balance Sheet — Equity (자본)
    # ═══════════════════════════════════════════
    "자본총계": "Total equity",
    "자본 총계": "Total equity",
    "자본합계": "Total equity",
    "부채와자본총계": "Total liabilities and equity",
    "부채 및 자본총계": "Total liabilities and equity",
    "부채와 자본 총계": "Total liabilities and equity",
    "자본금": "Share capital",
    "자본 금": "Share capital",
    "보통주자본금": "Common stock",
    "우선주자본금": "Preferred stock",
    "주식발행초과금": "Share premium",
    "자본잉여금": "Capital surplus",
    "이익잉여금": "Retained earnings",
    "기타자본": "Other components of equity",
    "기타자본구성요소": "Other components of equity",
    "기타자본항목": "Other components of equity",
    "기타포괄손익누계액": "Accumulated other comprehensive income",
    "기타포괄손익": "Other comprehensive income",
    "자기주식": "Treasury shares",
    "자기주식처분이익": "Gain on disposal of treasury shares",
    "비지배지분": "Non-controlling interests",
    "지배기업소유주지분": "Equity attributable to owners of the parent",
    "지배기업 소유주지분": "Equity attributable to owners of the parent",

    # ═══════════════════════════════════════════
    # Income Statement (손익계산서)
    # ═══════════════════════════════════════════
    "매출액": "Revenue",
    "매출": "Revenue",
    "수익": "Revenue",
    "영업수익": "Operating revenue",
    "매출원가": "Cost of sales",
    "매출총이익": "Gross profit",
    "매출 총이익": "Gross profit",
    "판매비와관리비": "Selling and administrative expenses",
    "판매비와 관리비": "Selling and administrative expenses",
    "판관비": "Selling and administrative expenses",
    "영업이익": "Operating income",
    "영업이익(손실)": "Operating income (loss)",
    "영업손실": "Operating loss",
    "기타수익": "Other income",
    "기타비용": "Other expenses",
    "금융수익": "Finance income",
    "금융비용": "Finance costs",
    "금융원가": "Finance costs",
    "이자수익": "Interest income",
    "이자비용": "Interest expense",
    "배당금수익": "Dividend income",
    "외환차익": "Foreign exchange gain",
    "외환차손": "Foreign exchange loss",
    "외화환산이익": "Foreign currency translation gain",
    "외화환산손실": "Foreign currency translation loss",
    "지분법이익": "Share of profit of associates",
    "지분법손실": "Share of loss of associates",
    "관계기업투자이익": "Share of profit of associates",
    "법인세비용차감전순이익": "Profit before income tax",
    "법인세비용차감전계속사업이익": "Profit before income tax from continuing operations",
    "법인세비용": "Income tax expense",
    "법인세": "Tax expense",
    "계속사업이익": "Profit from continuing operations",
    "중단사업이익": "Profit from discontinued operations",
    "중단사업손실": "Loss from discontinued operations",
    "당기순이익": "Profit for the period",
    "당기순이익(손실)": "Profit (loss) for the period",
    "당기순손실": "Loss for the period",
    "총포괄이익": "Total comprehensive income",
    "총포괄손익": "Total comprehensive income (loss)",

    # EPS
    "주당이익": "Earnings per share",
    "주당순이익": "Earnings per share",
    "기본주당이익": "Basic earnings per share",
    "기본주당순이익": "Basic earnings per share",
    "희석주당이익": "Diluted earnings per share",
    "희석주당순이익": "Diluted earnings per share",

    # SG&A detail
    "급여": "Salaries",
    "퇴직급여": "Retirement benefits",
    "복리후생비": "Employee welfare expenses",
    "감가상각비": "Depreciation",
    "무형자산상각비": "Amortization of intangible assets",
    "상각비": "Amortization",
    "대손상각비": "Bad debt expense",
    "광고선전비": "Advertising expenses",
    "판매수수료": "Sales commissions",
    "경상연구개발비": "Research and development expenses",
    "연구개발비": "Research and development expenses",
    "지급수수료": "Service fees",
    "임차료": "Rent expense",
    "수선비": "Repair and maintenance",
    "여비교통비": "Travel and transportation",
    "통신비": "Communication expenses",
    "세금과공과": "Taxes and dues",
    "보험료": "Insurance expenses",
    "접대비": "Entertainment expenses",
    "교육훈련비": "Training expenses",
    "주식보상비용": "Share-based payment expense",

    # ═══════════════════════════════════════════
    # Cash Flow Statement (현금흐름표)
    # ═══════════════════════════════════════════
    "영업활동으로인한현금흐름": "Cash flows from operating activities",
    "영업활동 현금흐름": "Cash flows from operating activities",
    "투자활동으로인한현금흐름": "Cash flows from investing activities",
    "투자활동 현금흐름": "Cash flows from investing activities",
    "재무활동으로인한현금흐름": "Cash flows from financing activities",
    "재무활동 현금흐름": "Cash flows from financing activities",
    "현금및현금성자산의증가(감소)": "Net increase (decrease) in cash and cash equivalents",
    "현금및현금성자산의 증가": "Increase in cash and cash equivalents",
    "기초현금및현금성자산": "Cash and cash equivalents at beginning of period",
    "기말현금및현금성자산": "Cash and cash equivalents at end of period",
    "유형자산의 취득": "Acquisition of property, plant and equipment",
    "유형자산의 처분": "Disposal of property, plant and equipment",
    "무형자산의 취득": "Acquisition of intangible assets",
    "무형자산의 처분": "Disposal of intangible assets",
    "단기차입금의 증가": "Increase in short-term borrowings",
    "단기차입금의 상환": "Repayment of short-term borrowings",
    "장기차입금의 차입": "Proceeds from long-term borrowings",
    "장기차입금의 상환": "Repayment of long-term borrowings",
    "배당금의 지급": "Dividends paid",
    "자기주식의 취득": "Acquisition of treasury shares",
    "자기주식의 처분": "Disposal of treasury shares",
    "사채의 발행": "Issuance of bonds",
    "사채의 상환": "Redemption of bonds",
    "리스부채의 상환": "Repayment of lease liabilities",

    # ═══════════════════════════════════════════
    # Equity Changes (자본변동표)
    # ═══════════════════════════════════════════
    "기초잔액": "Balance at beginning of period",
    "기초": "Beginning balance",
    "기말잔액": "Balance at end of period",
    "기말": "Ending balance",
    "배당": "Dividends",
    "배당금": "Dividends",
    "연차배당": "Annual dividends",
    "중간배당": "Interim dividends",
    "유상증자": "Issuance of shares",
    "자기주식 취득": "Acquisition of treasury shares",
    "자기주식 처분": "Disposal of treasury shares",

    # ═══════════════════════════════════════════
    # Note disclosure terms
    # ═══════════════════════════════════════════
    "리스": "Leases",
    "운용리스": "Operating leases",
    "금융리스": "Finance leases",
    "파생상품": "Derivatives",
    "파생금융상품": "Derivative financial instruments",
    "특수관계자": "Related parties",
    "특수관계자 거래": "Related party transactions",
    "특수관계자와의 거래": "Related party transactions",
    "우발부채": "Contingent liabilities",
    "우발자산": "Contingent assets",
    "약정사항": "Commitments",
    "담보제공자산": "Assets pledged as collateral",
    "금융위험관리": "Financial risk management",
    "금융위험 관리": "Financial risk management",
    "시장위험": "Market risk",
    "신용위험": "Credit risk",
    "유동성위험": "Liquidity risk",
    "이자율위험": "Interest rate risk",
    "환위험": "Foreign currency risk",
    "공정가치": "Fair value",
    "공정가치 서열체계": "Fair value hierarchy",
    "영업부문": "Operating segments",
    "부문정보": "Segment information",
    "부문 정보": "Segment information",
    "사업결합": "Business combinations",
    "보고기간후사건": "Events after the reporting period",
    "보고기간 후 사건": "Events after the reporting period",
    "보고기간후 사건": "Events after the reporting period",

    # ═══════════════════════════════════════════
    # Accounting policy / measurement terms
    # ═══════════════════════════════════════════
    "상각후원가": "Amortized cost",
    "공정가치측정": "Fair value measurement",
    "손상": "Impairment",
    "손상차손": "Impairment loss",
    "손상차손환입": "Reversal of impairment loss",
    "제거": "Derecognition",
    "최초인식": "Initial recognition",
    "후속측정": "Subsequent measurement",
    "연결": "Consolidation",
    "연결재무제표": "Consolidated financial statements",
    "별도재무제표": "Separate financial statements",
    "원가모형": "Cost model",
    "재평가모형": "Revaluation model",
    "정액법": "Straight-line method",
    "정률법": "Declining balance method",
    "내용연수": "Useful life",
    "잔존가치": "Residual value",
    "상각": "Amortization",
    "감가상각": "Depreciation",
    "충당금": "Allowance",
    "대손충당금": "Allowance for doubtful accounts",
    "기대신용손실": "Expected credit losses",
    "신용손실충당금": "Allowance for credit losses",
    "취득원가": "Acquisition cost",
    "장부금액": "Carrying amount",
    "순실현가능가치": "Net realizable value",
    "현재가치": "Present value",
    "할인율": "Discount rate",
    "유효이자율": "Effective interest rate",
    "가중평균": "Weighted average",

    # ═══════════════════════════════════════════
    # Common table headers / labels
    # ═══════════════════════════════════════════
    "구분": "Description",
    "과목": "Account",
    "계정과목": "Account",
    "합계": "Total",
    "소계": "Subtotal",
    "계": "Total",
    "내용": "Description",
    "금액": "Amount",
    "당기": "Current period",
    "전기": "Prior period",
    "당기말": "End of current period",
    "전기말": "End of prior period",
    "당분기": "Current quarter",
    "전분기": "Prior quarter",
    "당분기말": "End of current quarter",
    "전분기말": "End of prior quarter",
    "증가": "Increase",
    "감소": "Decrease",
    "취득": "Acquisition",
    "처분": "Disposal",
    "대체": "Transfer",
    "기타": "Others",
    "단위": "Unit",
    "원": "Korean won",
    "천원": "In thousands of Korean won",
    "백만원": "In millions of Korean won",
    "(단위: 천원)": "(In thousands of Korean won)",
    "(단위: 원)": "(In Korean won)",
    "(단위: 백만원)": "(In millions of Korean won)",
    "주석": "Notes",
}


def lookup_ifrs_term(korean: str) -> str | None:
    """
    Look up a Korean term in the IFRS dictionary.
    Returns English translation or None if not found.

    Tries exact match first, then stripped match.
    """
    text = korean.strip()
    if text in IFRS_TERMS:
        return IFRS_TERMS[text]
    return None


def lookup_ifrs_partial(korean: str) -> str | None:
    """
    Try to find a partial match for a Korean term.
    Useful for labels that have extra whitespace or prefixes.
    Returns the best (longest-match) English translation or None.
    """
    text = korean.strip()
    if not text:
        return None

    # Exact match first
    if text in IFRS_TERMS:
        return IFRS_TERMS[text]

    # Find the longest Korean key that appears as a substring of the input
    best_match = None
    best_len = 0
    for ko, en in IFRS_TERMS.items():
        if ko in text and len(ko) > best_len:
            best_match = en
            best_len = len(ko)

    return best_match

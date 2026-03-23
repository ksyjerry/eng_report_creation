# 재무제표 구조

## 4대 재무제표

### 1. 재무상태표 (BS - Statement of Financial Position)

특정 시점의 자산, 부채, 자본 현황.

```
구조:
  유동자산 (Current assets)
    현금및현금성자산 (Cash and cash equivalents)
    매출채권 (Trade receivables)
    ...
  비유동자산 (Non-current assets)
    유형자산 (Property, plant and equipment)
    무형자산 (Intangible assets)
    ...
  자산총계 (Total assets)

  유동부채 (Current liabilities)
    매입채무 (Trade payables)
    ...
  비유동부채 (Non-current liabilities)
    ...
  부채총계 (Total liabilities)

  자본 (Equity)
    자본금 (Share capital)
    이익잉여금 (Retained earnings)
    ...
  자본총계 (Total equity)

  부채와자본총계 (Total liabilities and equity)
```

**핵심 검증**: 자산총계 == 부채총계 + 자본총계 (또는 부채와자본총계)

**열 구조** (보통 3열):
- 라벨 | 당기말 | 전기말

### 2. 포괄손익계산서 (IS - Statement of Comprehensive Income)

일정 기간의 수익과 비용.

```
구조:
  매출액 (Revenue)
  매출원가 (Cost of sales)
  매출총이익 (Gross profit)
  판매비와관리비 (Selling and administrative expenses)
  영업이익 (Operating profit)
  금융수익 (Finance income)
  금융비용 (Finance costs)
  법인세비용차감전순이익 (Profit before income tax)
  법인세비용 (Income tax expense)
  당기순이익 (Profit for the year)
  기타포괄손익 (Other comprehensive income)
  총포괄이익 (Total comprehensive income)
```

**열 구조** (보통 3열):
- 라벨 | 당기 | 전기

### 3. 자본변동표 (CE - Statement of Changes in Equity)

자본 항목의 변동 내역.

```
구조 (매트릭스형):
  가로축: 자본금 | 자본잉여금 | 이익잉여금 | 기타자본 | 합계
  세로축:
    기초잔액 (Beginning balance)
    당기순이익 (Profit for the year)
    배당금 (Dividends)
    ...
    기말잔액 (Ending balance)
```

**특이사항**:
- 당기/전기 블록이 세로로 나뉨 (같은 테이블에 2개 기간)
- 다른 재무제표와 열 구조가 다름 (열이 많고 라벨이 세로)

### 4. 현금흐름표 (CF - Statement of Cash Flows)

현금의 유입/유출.

```
구조:
  영업활동현금흐름 (Cash flows from operating activities)
    당기순이익 (Profit for the year)
    조정 (Adjustments)
    ...
  투자활동현금흐름 (Cash flows from investing activities)
    유형자산의 취득 (Acquisition of property, plant and equipment)
    ...
  재무활동현금흐름 (Cash flows from financing activities)
    차입금의 상환 (Repayment of borrowings)
    ...
  현금및현금성자산의 증감 (Net increase/decrease in cash)
  기초 현금및현금성자산 (Cash at beginning of year)
  기말 현금및현금성자산 (Cash at end of year)
```

**핵심 검증**: 기초 + 증감 == 기말

## 주석 (Notes to Financial Statements)

재무제표의 세부 내역과 회계정책 설명.

### 주석 구조
- 번호 체계: 1, 2, 3, ... (소단원: 2.1, 2.2, ...)
- 내용 유형:
  - **텍스트 주석**: 회계정책 설명 등 (주로 변경 없음)
  - **테이블 주석**: 숫자 명세 (주로 업데이트 필요)
  - **혼합**: 텍스트 + 테이블

### 주요 주석 유형

| 번호 (통상) | 제목 (한) | 제목 (영) | 내용 |
|------------|-----------|-----------|------|
| 1 | 일반사항 | General information | 회사 개요 |
| 2 | 재무제표 작성기준 | Basis of preparation | 회계 기준 |
| 3 | 중요한 회계정책 | Significant accounting policies | 정책 상세 |
| ~ | 현금및현금성자산 | Cash and cash equivalents | 명세 테이블 |
| ~ | 매출채권 | Trade receivables | 명세 테이블 |
| ~ | 유형자산 | Property, plant and equipment | 변동 명세 |
| ~ | 무형자산 | Intangible assets | 변동 명세 |
| ~ | 차입금 | Borrowings | 명세 테이블 |
| ~ | 매출 | Revenue | 분류별 매출 |
| ~ | 법인세 | Income taxes | 세금 계산 |
| 마지막 | 보고기간후사건 | Events after reporting period | 후속 사건 |

**주의**: 주석 번호는 회사마다 다르다! 같은 내용이라도 A회사는 주석 5, B회사는 주석 8.

## 기간 표현

### DSD (한국어)
- 당기: 당기, 당기말, 당분기, 당분기말 → 현재 보고기간
- 전기: 전기, 전기말, 전분기, 전분기말 → 이전 보고기간

### DOCX (영어)
- 당기: "2025", "December 31, 2025", "For the year ended December 31, 2025"
- 전기: "2024", "December 31, 2024", "For the year ended December 31, 2024"

## 숫자 형식

### 한국어 (DSD)
- 양수: 1,234,567
- 음수: (1,234,567) 또는 -1,234,567 또는 △1,234,567
- 0: 0 또는 -
- 단위: (단위: 원) 또는 (단위: 천원)

### 영어 (DOCX)
- 양수: 1,234,567
- 음수: (1,234,567) — 괄호가 표준
- 0: - (대시가 일반적)
- 단위: (In thousands of Korean won) 또는 (In Korean won)

**중요**: 숫자 값 자체는 절대 변환하지 않는다. DSD 원본 그대로 사용.
형식(콤마, 괄호 등)만 DOCX 기존 형식에 맞춘다.

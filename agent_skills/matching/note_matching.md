# 주석 매칭

## 개요
DSD의 한국어 주석과 DOCX의 영어 주석을 매칭하는 작업.
주석 번호와 제목을 기반으로 매칭한다.

## 매칭 전략

### Pass 1: 번호 + 제목 확인

1. DSD 주석 번호와 DOCX 주석 번호가 같은 것을 찾음
2. 번호가 같아도 제목 유사도를 확인 (유사도 >= 0.3)
3. 유사도가 낮으면 번호가 같아도 매칭 보류 (→ Pass 2로)

**번호 정규화**:
- 앞뒤 점/공백 제거: "1." → "1", " 2 " → "2"
- 선행 0 제거: "01" → "1"
- 소수점 하위번호 유지: "2.1" → "2.1"

### Pass 2: 제목만으로 매칭

Pass 1에서 매칭 안 된 주석들을 제목 유사도로 매칭.
- 유사도 >= 0.4 이면 매칭
- 가장 높은 유사도의 쌍을 선택

### 제목 유사도 계산

한국어 제목 → 영어로 변환 → DOCX 영어 제목과 비교

**번역 소스**: 100개 이상의 한→영 주석 제목 매핑 테이블

```
"현금및현금성자산" → "Cash and Cash Equivalents"
"매출채권" → "Trade Receivables"
"유형자산" → "Property, Plant and Equipment"
"무형자산" → "Intangible Assets"
"차입금" → "Borrowings"
"충당부채" → "Provisions"
...
```

**비교 방법**: Jaccard 유사도 (단어 토큰 기반)
- 양쪽을 소문자로 변환 후 단어 분리
- 교집합 / 합집합 = 유사도 점수

## 주의사항

- **주석 번호가 같아도 내용이 다를 수 있다**: 회사마다 주석 순서가 다름
- **신규 주석**: DSD에만 있고 DOCX에 없는 주석 → 추가 필요
- **삭제된 주석**: DOCX에만 있고 DSD에 없는 주석 → 삭제 또는 보류
- **번호 변경**: 같은 내용인데 번호가 바뀔 수 있음 (전기 주석5 → 당기 주석6)
  - → Pass 2의 제목 기반 매칭이 이를 잡아냄

## 한→영 주석 제목 대응표 (주요 항목)

| 한국어 | 영어 |
|--------|------|
| 일반사항 | General information |
| 재무제표 작성기준 | Basis of preparation |
| 중요한 회계정책 | Significant accounting policies |
| 현금및현금성자산 | Cash and cash equivalents |
| 단기금융상품 | Short-term financial instruments |
| 매출채권 및 기타채권 | Trade and other receivables |
| 재고자산 | Inventories |
| 기타유동자산 | Other current assets |
| 장기금융상품 | Long-term financial instruments |
| 관계기업투자 | Investments in associates |
| 유형자산 | Property, plant and equipment |
| 무형자산 | Intangible assets |
| 투자부동산 | Investment property |
| 사용권자산 | Right-of-use assets |
| 매입채무 및 기타채무 | Trade and other payables |
| 차입금 | Borrowings |
| 사채 | Bonds |
| 리스부채 | Lease liabilities |
| 충당부채 | Provisions |
| 퇴직급여부채 | Retirement benefit obligations |
| 자본금 | Share capital |
| 이익잉여금 | Retained earnings |
| 매출 | Revenue |
| 판매비와관리비 | Selling and administrative expenses |
| 금융수익 | Finance income |
| 금융비용 | Finance costs |
| 법인세 | Income taxes |
| 주당이익 | Earnings per share |
| 우발부채 | Contingent liabilities |
| 특수관계자거래 | Related party transactions |
| 보고기간후사건 | Events after the reporting period |

**전체 목록**: translation/ifrs_terms.md 참조

# DSD 파일 형식

## 개요
DSD(Disclosure Submission Data)는 DART(전자공시시스템)에서 사용하는 재무제표 파일 형식.
ZIP 아카이브 내부에 XML 문서가 들어있다.

## 파일 구조

```
*.dsd (ZIP archive)
├── contents.xml    ← 메인 문서 (재무제표 + 주석 전체)
└── meta.xml        ← 메타데이터 (회사명, 보고기간 등)
```

## XML 스키마 (DART 4.0)

```xml
<DOCUMENT>
  <HEADER>...</HEADER>
  <BODY>
    <SECTION-1>          ← 재무제표 (4개)
      <TITLE>재무상태표</TITLE>
      <TABLE>...</TABLE>
    </SECTION-1>
    <SECTION-2>          ← 주석
      <TITLE>주석</TITLE>
      <SECTION-2>        ← 개별 주석 (중첩)
        <TITLE>1. 일반사항</TITLE>
        <P>...</P>
        <TABLE>...</TABLE>
      </SECTION-2>
    </SECTION-2>
  </BODY>
</DOCUMENT>
```

## 재무제표 유형 감지

SECTION-1의 TITLE 텍스트로 재무제표 유형을 판별한다:

| 키워드 | 유형 | 영문 |
|--------|------|------|
| 재무상태표, 자산, 부채 | BS | Statement of Financial Position |
| 손익계산서, 포괄손익, 매출액 | IS | Statement of Comprehensive Income |
| 자본변동표, 자본변동 | CE | Statement of Changes in Equity |
| 현금흐름표, 현금흐름 | CF | Statement of Cash Flows |

## 기간(Period) 추출

- `<TU>` 태그의 `AUNITVALUE` 속성에서 연도 추출 (앞 4자리)
- 연도를 내림차순 정렬: 가장 큰 값 = 당기, 두 번째 = 전기
- 예: AUNITVALUE="20251231" → 당기 2025, 전기 2024

## 회사명 추출

우선순위:
1. `<COMPANY-NAME>` 태그 텍스트
2. `<TD>` 태그 중 USERMARK='F-14' 또는 'BT14' (큰 볼드 텍스트)
3. "주식회사" 또는 "㈜" 포함 텍스트
4. 길이 3자 초과 텍스트

## 문서 유형

- "연결" 포함 → CONSOLIDATED (연결재무제표)
- "별도" 포함 → SEPARATE (별도재무제표)

## 테이블 구조

DSD 테이블은 비교적 단순하다:
- `<TABLE>` → `<COLGROUP>` (열 정의) + `<THEAD>` + `<TBODY>`
- `<TR>` → `<TD>` (셀)
- `COLSPAN`, `ROWSPAN` 속성으로 셀 병합
- **Spacer column이 없다** (DOCX와 다른 점)

## 주석 구조

- `<SECTION-2>` → 개별 주석 섹션
- `<TITLE>` → 주석 제목 (예: "1. 일반사항")
- `<P>` → 문단
- `<TABLE>` → 테이블
- 중첩: SECTION-2 안에 다시 SECTION-2 (소단원)
- 번호 체계: "1", "2", "2.1", "2.1.1" 등

## 특수 문자 처리

- `&cr;` 엔티티 → 개행문자로 변환
- 공백 정규화: `re.sub(r'\s+', ' ', text)` 로 연속 공백 제거

## 주의사항

- SECTION-2가 SECTION-1 안에 중첩될 수 있음 → 중복 처리 방지 필요
- 일부 DSD에서 BODY 태그가 없을 수 있음 → root를 fallback으로 사용
- 기간이 1개만 있을 수 있음 → 당기연도 - 1 = 전기연도로 유추

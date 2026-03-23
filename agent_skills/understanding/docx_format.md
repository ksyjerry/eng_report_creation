# DOCX 파일 형식

## 개요
영문 재무제표는 Microsoft Word 형식(DOCX)으로 되어 있다.
DOCX는 내부적으로 ZIP 아카이브이며, OOXML(Office Open XML) 표준을 따른다.

## 파일 내부 구조

```
*.docx (ZIP archive)
├── [Content_Types].xml
├── _rels/.rels
├── word/
│   ├── document.xml       ← 본문 (핵심)
│   ├── header1.xml        ← 머리글
│   ├── header2.xml
│   ├── footer1.xml        ← 바닥글
│   ├── footer2.xml
│   ├── styles.xml         ← 스타일 정의
│   ├── numbering.xml      ← 번호 매기기
│   ├── media/             ← 이미지
│   └── _rels/document.xml.rels
└── docProps/
    ├── app.xml
    └── core.xml
```

## 본문 XML 구조 (document.xml)

```xml
<w:body>
  <w:p>                    ← 문단 (paragraph)
    <w:pPr>                ← 문단 속성 (스타일, 정렬 등)
      <w:pStyle w:val="ABCTitle"/>
      <w:jc w:val="center"/>
    </w:pPr>
    <w:r>                  ← Run (텍스트 조각)
      <w:rPr>              ← Run 속성 (폰트, 크기, 볼드 등)
        <w:b/>
        <w:sz w:val="20"/>
      </w:rPr>
      <w:t>Note 1.</w:t>  ← 실제 텍스트
    </w:r>
  </w:p>
  <w:tbl>                  ← 테이블
    <w:tblPr>...</w:tblPr>
    <w:tblGrid>            ← 열 너비 정의
      <w:gridCol w:w="2500"/>
      <w:gridCol w:w="58"/>    ← Spacer column!
      <w:gridCol w:w="1200"/>
    </w:tblGrid>
    <w:tr>                 ← 행 (table row)
      <w:tc>               ← 셀 (table cell)
        <w:tcPr>
          <w:gridSpan w:val="2"/>  ← 수평 병합
          <w:vMerge w:val="restart"/> ← 수직 병합 시작
        </w:tcPr>
        <w:p>
          <w:r><w:t>Cell text</w:t></w:r>
        </w:p>
      </w:tc>
    </w:tr>
  </w:tbl>
</w:body>
```

## Spacer Column (매우 중요)

많은 회계 DOCX 파일에는 열 사이에 **spacer column**이 존재한다.
화면에서는 열 사이 간격으로 보이지만, XML에서는 독립적인 `<w:gridCol>`이다.

```
화면에서 보이는 것:    항목명   |   당기   |   전기
실제 XML 구조:         col0  | spacer | col2 | spacer | col4 | spacer | col6
                       2500     58      1200    58      1200    58      1200
```

**Spacer column 판별 기준**: `w:gridCol` 너비 < 200 dxa (약 0.14인치)
- 일반적으로 50~100 dxa 사이
- 데이터가 없는 빈 열

**결과**: Physical column index와 Logical column index가 다르다!
- Physical (XML 기준): [0, 1, 2, 3, 4, 5, 6] — 7개
- Logical (의미 기준): [0, 1, 2, 3] — 4개 (spacer 제거)
- 매핑: logical 0→physical 0, logical 1→physical 2, logical 2→physical 4, logical 3→physical 6

**→ 값을 쓸 때 반드시 physical column index를 사용해야 한다!**
자세한 내용: editing/column_mapping.md 참조

## 셀 병합

### 수평 병합 (gridSpan)
```xml
<w:tcPr>
  <w:gridSpan w:val="3"/>  ← 이 셀이 3개 physical column을 차지
</w:tcPr>
```
- 테이블 헤더에서 흔히 발생 (예: "December 31, 2024 and 2023"이 여러 열에 걸침)
- gridSpan이 spacer column을 포함할 수 있음 → column 매핑 시 주의

### 수직 병합 (vMerge)
```xml
<!-- 병합 시작 -->
<w:vMerge w:val="restart"/>

<!-- 병합 계속 (값 없음) -->
<w:vMerge/>
```
- vMerge continuation 셀은 빈 텍스트
- 값을 쓸 때는 restart 셀에만 쓰면 됨

## 주석 경계 감지

DOCX에서 주석의 시작은 **ABCTitle** 스타일의 문단으로 감지한다:

```xml
<w:p>
  <w:pPr><w:pStyle w:val="ABCTitle"/></w:pPr>
  <w:r><w:t>8. Property, plant and equipment</w:t></w:r>
</w:p>
```

- ABCTitle 문단 = 주석 시작점
- 주석 번호: 텍스트 앞의 숫자 (regex: `^\d+(?:\.\d+)*`)
- 주석 제목: 나머지 텍스트

## Run 분할 문제

Word는 편집 이력에 따라 하나의 텍스트를 **여러 Run으로 분할**할 수 있다:

```xml
<!-- "December 31, 2024" 가 3개 Run으로 분할 -->
<w:r><w:t>December 31, 202</w:t></w:r>
<w:r><w:t>4</w:t></w:r>
```

이 경우 "2024"를 단순 텍스트 검색으로 찾을 수 없다.
→ editing/year_rolling.md 의 cross-run 교체 방법 참조

## 회사명/기간 추출

- 회사명: 처음 나오는 Normal 스타일 문단 (80자 미만, "("로 시작하지 않는 것)
- 기간: "December 31, YYYY and YYYY" 패턴 검색
- 문서 유형: "consolidated"/"separate" 키워드 검색, 없으면 파일명에서 추출

## 스타일 체계

| 스타일명 | 용도 |
|---------|------|
| ABCTitle | 주석 제목 (주석 경계 감지에 사용) |
| Normal | 일반 본문 |
| (회사별 다름) | 소제목, 부제목 등 |

## DOCX Profile (자동 감지 항목)

DOCX를 파싱할 때 자동으로 감지하는 속성:
- **SpacingStrategy**: SPACER_COLUMN / EMPTY_ROW / MIXED / NONE
- **MergeStrategy**: VMERGE_HEAVY / GRIDSPAN_HEAVY / BALANCED / MINIMAL
- **WidthStrategy**: FIXED / AUTO / MIXED
- **스타일명**: title_style, subtitle_style, body_style
- **색상**: monochrome / colored

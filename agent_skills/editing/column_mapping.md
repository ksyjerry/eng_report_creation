# Column Mapping (Logical vs Physical)

## 문제

많은 회계 DOCX에는 열 사이에 **spacer column**이 있다.
값을 쓸 때 logical index로 쓰면 spacer column에 값이 들어가거나 한 칸 밀린다.

## Spacer Column이란?

화면에서는 열 사이 간격으로 보이지만, XML에서는 독립적인 열이다.

```
화면:     항목명       1,234,567       987,654
XML:     col0 | spc | col2 | spc | col4 | spc | col6
너비:    2500   58    1200   58    1200   58    1200
```

- Spacer column 판별: `<w:gridCol>` 너비 < 200 dxa
- 일반적 spacer 너비: 50~100 dxa
- 데이터가 없는 빈 열

## Logical vs Physical Index

```
Physical (XML 기준): [0,  1,    2,    3,    4,    5,    6]
역할:                [라벨, spc, 당기, spc, 전기, spc, 기타]
Logical (의미 기준): [0,         1,          2,         3]
```

매핑:
- logical 0 → physical 0 (라벨 열)
- logical 1 → physical 2 (당기 열)
- logical 2 → physical 4 (전기 열)
- logical 3 → physical 6 (기타 열)

## 값 쓰기 시 반드시 Physical Index 사용

```
잘못된 예:
  set_cell_text(table=3, row=5, col=1, text="1,234,567")
  → col 1 = spacer column → 값이 보이지 않는 빈 열에 들어감!

올바른 예:
  column_info = get_column_info(table=3)
  → "logical 1 → physical 2"
  set_cell_text(table=3, row=5, col=2, text="1,234,567")
  → col 2 = 실제 당기 데이터 열 ✓
```

## Column 정보 확인 방법

`get_column_info()` 도구 사용:

```
== Table 3 Column Info ==
Physical columns: 7
Widths: [2500, 58, 1200, 58, 1200, 58, 1200]
Spacers: [1, 3, 5] (width < 200)

Logical → Physical mapping:
  logical 0 → physical 0 (width=2500, label)
  logical 1 → physical 2 (width=1200, data)
  logical 2 → physical 4 (width=1200, data)
  logical 3 → physical 6 (width=1200, data)
```

## gridSpan과 Spacer의 관계

테이블 헤더에서 `gridSpan`이 spacer column을 포함할 수 있다:

```xml
<!-- "December 31, 2025 and 2024" 가 col 1~6을 차지 -->
<w:tc>
  <w:tcPr>
    <w:gridSpan w:val="6"/>  ← physical col 1~6 (spacer 포함!)
  </w:tcPr>
  <w:p><w:r><w:t>December 31, 2025 and 2024</w:t></w:r></w:p>
</w:tc>
```

이 경우 기간 열을 감지할 때:
- 헤더 텍스트 "2025"가 있는 셀의 gridSpan = 6
- 이 span이 spacer를 포함하므로, 실제 데이터 열은 확인이 필요
- → 데이터 행에서 실제 숫자가 있는 열을 확인하여 보정

## 기간 열 감지 시 주의

헤더에서 "2025"나 "당기"를 찾아 기간 열을 감지할 때:

1. 헤더 셀이 gridSpan으로 여러 열을 차지할 수 있음
2. 그 중 어떤 열이 실제 데이터 열인지는 데이터 행으로 확인
3. 데이터 행에서 실제 숫자값이 있는 열 = 데이터 열
4. 숫자가 없는 열 = spacer (건너뛰기)

```
확인 방법:
  데이터 행 10개를 스캔
  각 physical column에 실제 숫자가 몇 개 있는지 카운트
  숫자가 5개 이상 있는 column = 데이터 열
  숫자가 0개인 column = spacer
```

## Spacer가 없는 DOCX

모든 DOCX에 spacer가 있는 것은 아니다.
`get_column_info()`에서 spacer가 없으면 logical == physical.
이 경우 추가 변환 불필요.

## 체크리스트

- [ ] 테이블을 처음 만나면 `get_column_info()`로 spacer 확인
- [ ] 값을 쓸 때 항상 physical column index 사용
- [ ] 기간 열은 데이터 행에서 숫자 존재 여부로 검증
- [ ] 같은 문서의 다른 테이블도 spacer 구조가 같은지 확인

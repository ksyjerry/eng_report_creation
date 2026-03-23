# 행 추가/삭제

## 행 추가 (Clone & Insert)

### 원칙
새 행을 처음부터 만들지 않는다. 반드시 기존 행을 복제한다.

### 방법

```
1. 삽입할 위치 근처의 기존 행을 선택 (source_row)
   - 추가할 행과 유사한 구조의 행이 좋음
   - 소계/합계 행은 서식이 다르므로 피함
   - 일반 데이터 행을 선택

2. 해당 행을 deepcopy
   - XML 전체 (<w:tr> + 모든 자식)를 복제
   - 서식, 셀 속성, 테두리 등 모두 보존

3. 복제된 행의 텍스트만 교체
   - set_cell_text()로 각 셀의 내용을 새 데이터로
   - 서식(rPr)은 이미 복제되어 있으므로 보존됨

4. 지정 위치에 삽입
   - insert_after 지정한 행 다음에 삽입
```

### Spacer Column 처리

행을 복제하면 spacer column도 함께 복제된다.
값을 넣을 때 spacer column은 건너뛰어야 한다.

```
Physical columns: [label, spc, data1, spc, data2]
값 넣을 때: col 0(라벨), col 2(data1), col 4(data2)만 변경
col 1, col 3은 비워둠 (spacer)
```

### vMerge 주의

원본 행에 vMerge(수직 병합) 속성이 있으면:
- `vMerge="restart"` → 병합 시작점
- `vMerge` (속성값 없음) → 병합 계속

복제된 행에서 vMerge 속성을 **제거**해야 한다.
그렇지 않으면 이전 행과 의도치 않게 병합됨.

## 행 삭제

### 원칙
- 높은 인덱스부터 삭제 (인덱스 밀림 방지)
- 삭제 전에 해당 행이 맞는지 read_cell()로 확인
- 합계 행은 절대 삭제하지 않음

### 방법
```
1. 삭제할 행의 내용 확인 (read_table)
2. 해당 <w:tr> 요소를 부모(w:tbl)에서 remove
3. 후속 변경의 행 인덱스 조정
```

## 인덱스 관리

### 삭제 시
```
원본: [row0, row1, row2, row3, row4]
row3 삭제: [row0, row1, row2, row4]
→ 원래 row4는 이제 row3

따라서 높은 인덱스부터 삭제해야 안전.
```

### 추가 시
```
원본: [row0, row1, row2, row3]
row1 뒤에 삽입: [row0, row1, NEW, row2, row3]
→ 원래 row2는 이제 row3

따라서 추가는 삭제 후에 수행.
```

## 체크리스트

- [ ] 복제 원본으로 적합한 행 선택 (일반 데이터 행)
- [ ] deepcopy 후 텍스트만 교체
- [ ] spacer column은 건너뛰기
- [ ] vMerge 속성 제거 확인
- [ ] 삽입 위치가 올바른지 확인
- [ ] 삽입 후 read_table()로 전체 확인

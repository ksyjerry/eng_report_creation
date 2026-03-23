# 영문 재무제표 생성 AI Agent 설계서

## 1. 개요

### 1.1 목적
전기 영문 재무제표(DOCX)를 템플릿으로, 당기 한글 재무제표(DSD)의 데이터를 반영하여
당기 영문 재무제표를 자동 생성하는 **LLM 주도 자율형 AI Agent**.

### 1.2 설계 철학: "Claude Code처럼"

이번에 Claude Code가 영문 재무제표를 수정한 과정을 돌아보면:

```
1. 파일을 열어보고 구조를 파악했다
2. "이렇게 하면 되겠다" 하고 시도했다
3. 결과를 봤더니 숫자가 밀려있었다 → 원인 분석 → column mapping 문제 발견
4. column mapping을 고쳤다 → 다시 시도
5. 또 봤더니 연도가 전부 2025로 됐다 → cascade 문제 발견
6. atomic 교체로 바꿨다 → 다시 시도
7. 또 봤더니 매칭이 엉뚱한 행으로 갔다 → value validation 추가
8. ... 이 과정을 반복하면서 99% 정확도 달성
```

이것은 **정해진 워크플로우를 따른 것이 아니다**.
상황을 보고, 판단하고, 시도하고, 실패하면 원인을 분석해서 다른 방법으로 재시도한 것이다.

우리가 만들 Agent도 이렇게 동작해야 한다:
- **정해진 파이프라인이 아니라, 목표를 향해 유연하게 전진**
- **실패를 두려워하지 않고 시도하되, 매번 결과를 검증**
- **같은 실수를 반복하지 않도록 경험에서 학습**

### 1.3 핵심 설계 원칙

| 원칙 | 설명 |
|------|------|
| **Try → Verify → Fix** | 한 번에 완벽하려 하지 않는다. 시도하고, 확인하고, 고치기를 반복 |
| **Skill Documents** | 축적된 노하우를 md 파일로 관리. Agent가 필요할 때 읽고 참조 |
| **Flexible Workflow** | 기본 흐름은 있되, Agent가 상황에 따라 순서를 바꾸거나 단계를 추가 |
| **Clone & Modify** | DOCX 서식 보존의 생명선. 절대 새로 만들지 않고 기존 것을 복제·수정 |
| **Escalate When Stuck** | 3번 시도해도 안 되면 사람에게 보고 |

---

## 2. 아키텍처: Skill-Augmented Autonomous Agent

### 2.1 전체 구조

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│                         LLM Agent (뇌)                           │
│                                                                  │
│    "이 테이블 구조가 좀 이상한데... spacer column이 있나?"         │
│    → skills/docx_editing.md 참조                                 │
│    "아, spacer column이 있으면 physical index가 다르구나"          │
│    → get_column_info 도구로 확인                                  │
│    → 올바른 column에 값 쓰기                                     │
│    → 확인... OK!                                                 │
│                                                                  │
├──────────────┬───────────────────┬───────────────────────────────┤
│              │                   │                               │
│  ┌───────────▼──────┐  ┌────────▼────────┐  ┌─────────────────┐ │
│  │  Skill Documents  │  │   Tool Layer    │  │  Working Memory │ │
│  │  (참조 지식)       │  │   (실행 도구)    │  │  (작업 기록)     │ │
│  ├───────────────────┤  ├─────────────────┤  ├─────────────────┤ │
│  │ docx_editing.md   │  │ read_table      │  │ 진행 상황       │ │
│  │ year_rolling.md   │  │ set_cell_text   │  │ 발견한 문제들    │ │
│  │ table_matching.md │  │ clone_row       │  │ 적용한 변경들    │ │
│  │ translation.md    │  │ replace_text    │  │ 검증 결과       │ │
│  │ number_format.md  │  │ translate       │  │ 학습한 패턴     │ │
│  │ common_errors.md  │  │ validate        │  │                 │ │
│  │ ...               │  │ ...             │  │                 │ │
│  └───────────────────┘  └─────────────────┘  └─────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 세 가지 핵심 요소

**1. LLM Agent (뇌)** — 모든 판단과 계획

- 문서를 읽고 구조를 파악
- 무엇을 어떤 순서로 할지 스스로 계획
- 실행 결과를 보고 다음 행동 결정
- 문제가 생기면 원인 분석 후 대안 시도

**2. Skill Documents (참조 지식)** — 축적된 노하우

- Agent가 **필요할 때 스스로 찾아서 읽는** md 파일들
- 과거 경험에서 배운 패턴, 주의사항, 해결법
- 새로운 경험이 생기면 Skill Document를 업데이트
- **사람이 직접 추가할 수도 있고, Agent가 학습하여 추가할 수도 있음**

**3. Tool Layer (손)** — 안전한 실행 인터페이스

- DOCX 조작을 위한 원자적 도구들
- 서식 보존 로직이 내장된 안전한 인터페이스
- LLM은 도구를 통해서만 문서를 수정

---

## 3. Skill Documents 상세

### 3.1 개념

Skill Document는 Agent의 **참조 매뉴얼**이다.
사람이 새 업무를 할 때 매뉴얼을 찾아보듯, Agent도 특정 작업을 할 때
관련 Skill Document를 읽고 참고한다.

```
Agent의 사고 과정:

"테이블 헤더에서 연도를 바꿔야 하는데,
 전에 cascade 문제가 있었다고 했지...
 → skills/year_rolling.md 를 읽어보자."

(읽은 후)

"아, '반드시 모든 교체를 한 번에 atomic하게' 해야 하는구나.
 그리고 Run이 분할되어 있을 수 있으니 cross-run 교체를 써야 하고.
 OK, 그렇게 하자."
```

### 3.2 Skill Document 목록

```
skills/
├── overview.md              # 전체 업무 흐름 가이드 (Agent가 처음 읽는 문서)
│
├── understanding/
│   ├── dsd_format.md        # DSD 파일 구조, XML 스키마, 읽는 법
│   ├── docx_format.md       # DOCX 내부 구조, OOXML, spacer column, vMerge 등
│   └── fs_structure.md      # 재무제표 구조 (BS, IS, CE, CF), 주석 체계
│
├── matching/
│   ├── table_matching.md    # 테이블 행 매칭 전략, 교차언어 매칭 노하우
│   ├── note_matching.md     # 주석 매칭 전략, 번호/제목 기반 매칭
│   └── value_validation.md  # 값 기반 검증법 (DSD 전기 == DOCX 당기)
│
├── editing/
│   ├── docx_editing.md      # DOCX 편집 핵심 원칙, 서식 보존, Clone & Modify
│   ├── cell_editing.md      # 셀 값 변경 시 주의사항, Run 보존
│   ├── row_operations.md    # 행 추가/삭제, deepcopy 방법
│   ├── year_rolling.md      # 연도 롤링 방법, cascade 방지, split run 처리
│   └── column_mapping.md    # logical/physical column 매핑, spacer 처리
│
├── translation/
│   ├── translation.md       # 번역 원칙, 용어 일관성, 맥락 활용
│   ├── ifrs_terms.md        # IFRS 표준 용어 대응표
│   └── number_format.md     # 숫자 형식 (천단위 콤마, 괄호 음수, 대시 0)
│
├── verification/
│   ├── verification.md      # 검증 체크리스트, 전수 검증 방법
│   └── cross_check.md       # 교차 검증 (BS 균형, IS 일관성 등)
│
└── troubleshooting/
    ├── common_errors.md     # 자주 발생하는 오류와 해결법
    └── error_log.md         # 실제 발생했던 오류 기록 (Agent가 업데이트)
```

### 3.3 예시: `skills/editing/year_rolling.md`

```markdown
# 연도 롤링 (Year Rolling)

## 개요
전기 DOCX의 연도 참조(예: 2024/2023)를 당기(2025/2024)로 변경하는 작업.

## 적용 대상
- [ ] Header / Footer (모든 섹션)
- [ ] 테이블 헤더 행 (상위 1~2행)
- [ ] 본문 문단 (테이블 내부 제외)
- [ ] 표지 (cover page)

## 주의사항

### Cascade 문제 (치명적)
**절대 순차적으로 교체하지 마세요.**

나쁜 예:
  1단계: "2023" → "2024"
  2단계: "2024" → "2025"
  → 1단계에서 바뀐 "2024"가 2단계에서 또 "2025"로 바뀜!
  → 결과: 모든 연도가 "2025"

올바른 방법:
  전체 텍스트를 한 번에 읽고, 한 번에 모든 교체를 적용.
  → replace_in_headers_footers([("2024", "2025"), ("2023", "2024")])
  → 큰 연도부터 먼저 교체 (2024→2025 먼저, 그다음 2023→2024)

### Run 분할 문제
Word는 편집 이력에 따라 "2024"를 "202" + "4"로 분할 저장할 수 있음.
단순 텍스트 교체로는 찾을 수 없음.

해결: cross-run 교체 사용
  → 문단의 모든 <w:t>를 연결하여 교체 후 재분배

### 검증 방법
교체 후 반드시:
1. read_header_footer()로 모든 header/footer 확인
2. 이전 연도(2024, 2023)가 남아있지 않은지 검색
3. 새 연도(2025, 2024)만 존재하는지 확인
```

### 3.4 예시: `skills/editing/docx_editing.md`

```markdown
# DOCX 편집 핵심 원칙

## 최우선 원칙: 서식 보존

DOCX 편집에서 가장 중요한 것은 **기존 서식을 깨뜨리지 않는 것**이다.
숫자 하나 잘못 넣는 것보다 서식이 깨지는 것이 더 큰 문제다.
서식이 깨지면 전체 문서를 다시 작업해야 할 수 있다.

## Clone & Modify 원칙

새 요소를 절대 직접 생성하지 마세요.
반드시 기존 요소를 deepcopy한 후 내용만 수정하세요.

- 새 행 추가: 인접 행을 clone_row()로 복제 후 텍스트만 교체
- 새 셀 내용: set_cell_text()로 기존 Run 서식을 보존하며 텍스트만 교체
- 새 문단: 절대 새로 만들지 마세요. 기존 문단의 텍스트를 교체

## Spacer Column 주의

많은 DOCX 파일에 "spacer column"이 있음 (폭 58~100 dxa의 매우 좁은 열).
화면에는 열 사이 간격으로 보이지만, XML에서는 독립적인 열.

Physical column index와 Logical column index가 다름:
  Physical: [label, spacer, data1, spacer, data2, spacer, data3]
  Logical:  [label, data1, data2, data3]

값을 쓸 때 반드시 get_column_info()로 physical index를 확인한 후 사용.

## 변경 전 확인사항

1. 대상 셀의 현재 값을 read_cell()로 확인
2. column mapping을 get_column_info()로 확인
3. 변경 후 read_cell()로 검증
4. 서식이 유지되었는지 확인
```

### 3.5 예시: `skills/troubleshooting/common_errors.md`

```markdown
# 자주 발생하는 오류와 해결법

## 1. 값이 엉뚱한 열에 들어감
증상: 숫자가 한 칸 옆에 기록됨
원인: spacer column으로 인한 logical/physical index 불일치
해결: get_column_info()로 physical column 확인 후 사용
참조: skills/editing/column_mapping.md

## 2. 연도가 전부 같은 값으로 변환됨
증상: "2024"와 "2023"이 전부 "2025"로 됨
원인: 순차 교체 시 cascade 발생
해결: 모든 교체를 한 번에 atomic하게 수행
참조: skills/editing/year_rolling.md

## 3. 연도가 일부 변환 안 됨
증상: header에 "2024"가 여전히 남아있음
원인: Word가 "2024"를 "202"+"4"로 분할 저장
해결: cross-run 교체 사용
참조: skills/editing/year_rolling.md

## 4. 행 매칭이 엉뚱하게 됨
증상: DSD의 "매출원가"가 DOCX의 "판매비"에 매칭됨
원인: 라벨 유사도만으로 매칭하면 오류 발생
해결: DSD 전기값 == DOCX 당기값으로 교차검증
참조: skills/matching/value_validation.md

## 5. 셀 서식이 깨짐
증상: 특정 셀의 폰트/크기/정렬이 변경됨
원인: Run을 새로 생성하거나 기존 Run 속성을 덮어씀
해결: set_cell_text()가 기존 Run을 보존하는지 확인
참조: skills/editing/cell_editing.md

## 6. 빈 셀이 숫자로 인식됨
증상: spacer 열이 데이터 열로 감지됨
원인: 빈 문자열("")이나 대시("-")가 numeric으로 판정됨
해결: 실제 숫자값이 있는 셀만 데이터 열로 판정
```

### 3.6 Skill Document 활용 메커니즘

```python
@tool("read_skill")
def read_skill(skill_path: str) -> str:
    """
    Skill Document를 읽어서 반환.

    Args:
        skill_path: 예) "editing/year_rolling.md",
                        "troubleshooting/common_errors.md"

    Agent가 특정 작업을 하기 전에 관련 스킬을 참조하거나,
    문제에 부딪혔을 때 해결법을 찾기 위해 사용.
    """
    pass


@tool("list_skills")
def list_skills() -> str:
    """
    사용 가능한 모든 Skill Document 목록 반환.
    Agent가 어떤 스킬이 있는지 탐색할 때 사용.
    """
    pass


@tool("update_skill")
def update_skill(skill_path: str, content: str) -> str:
    """
    Skill Document를 업데이트하거나 새로 생성.
    Agent가 새로운 패턴을 발견했을 때 기록.

    예) 새로운 오류 패턴을 common_errors.md에 추가
    """
    pass
```

---

## 4. Working Memory (작업 기록)

### 4.1 개념

Agent가 작업하면서 축적하는 **현재 세션의 기억**.
Skill Document가 "매뉴얼"이라면, Working Memory는 "작업 노트".

```python
@tool("write_memo")
def write_memo(key: str, content: str) -> str:
    """
    작업 메모 저장. Agent가 나중에 참조할 정보를 기록.

    예시 사용:
      write_memo("docx_structure", "테이블 52개, 주석 45개, spacer column 있음")
      write_memo("note_8_plan", "유형자산 - 테이블 2개, 행 매칭 후 값 업데이트")
      write_memo("error_found", "table 15의 column 2가 spacer임. physical col 4 사용해야")
      write_memo("glossary", "유동자산=Current assets, 매출액=Revenue, ...")
    """
    pass


@tool("read_memo")
def read_memo(key: str) -> str:
    """작업 메모 읽기."""
    pass


@tool("list_memos")
def list_memos() -> str:
    """저장된 모든 메모 키 목록."""
    pass
```

### 4.2 Working Memory vs Skill Document

| | Working Memory | Skill Document |
|---|---|---|
| 수명 | 현재 세션만 | 영구 (세션 간 유지) |
| 작성자 | Agent (자동) | Agent + 사람 |
| 내용 | 이번 문서의 구조, 매칭 결과 등 | 일반적인 노하우, 패턴, 주의사항 |
| 예시 | "HYBE 2025의 주석 8은 테이블 2개" | "연도 롤링 시 cascade 주의" |

---

## 5. Agent 동작 방식

### 5.1 Claude Code가 일하는 방식 그대로

```
Agent가 일하는 과정 (실제 사고 흐름):

── 시작 ──

"영문 재무제표를 만들어야 한다.
 먼저 overview.md를 읽어서 전체 흐름을 파악하자."

→ read_skill("overview.md")

"OK, 큰 흐름은: 분석 → 재무제표 업데이트 → 주석 업데이트 → 연도 롤링 → 검증.
 하지만 이건 가이드일 뿐, 상황에 따라 유연하게 하자.
 먼저 두 파일을 열어보자."

→ read_dsd_structure(dsd_path)
→ read_docx_structure(docx_path)

"DSD: 재무제표 4개, 주석 45개
 DOCX: 재무제표 4개, 주석 43개
 → 주석 2개가 새로 추가된 것 같다.
 메모해두자."

→ write_memo("structure_diff", "DSD 주석 45개 vs DOCX 43개. 신규 2개 예상")

"재무상태표부터 시작하자. DSD와 DOCX의 BS 테이블을 비교해보자."

→ compare_tables(dsd_table=0, docx_table=3)

"행 매칭이 좀 복잡한데... table_matching.md를 참조하자."

→ read_skill("matching/table_matching.md")

"아, DSD 전기값 == DOCX 당기값으로 검증하라고 했다.
 '유동자산': DSD 전기 1,123,456 == DOCX 당기 1,123,456. 매칭 확실!

 이제 값을 업데이트하자. 그전에 column 정보를 확인."

→ get_column_info(table_index=3)

"spacer column이 있다. physical col 2가 당기열이다.
 docx_editing.md에서 주의하라고 했지."

→ set_cell_text(table=3, row=2, physical_col=2, text="1,234,567")
→ read_cell(table=3, row=2, col=2)

"1,234,567 ✓ OK. 다음 행..."

── (이런 식으로 계속) ──

"어? table 15의 매칭이 이상하다.
 DSD '감가상각비'가 DOCX 'Amortization'에 매칭됐는데,
 값을 보니 전혀 다르다. DSD 전기 500,000인데 DOCX 당기 12,000.
 이건 잘못된 매칭이다."

"common_errors.md를 보자."

→ read_skill("troubleshooting/common_errors.md")

"'행 매칭이 엉뚱하게 됨' 항목이 있다.
 value_validation.md를 참조하라고 했다."

→ read_skill("matching/value_validation.md")

"OK, 라벨이 아닌 값으로 매칭을 재시도하자.
 DSD 전기값 500,000을 가진 DOCX 행을 찾아보면...
 'Depreciation' 행의 당기값이 500,000이다. 이게 맞는 매칭이다!"

→ set_cell_text(...)  (올바른 행에 업데이트)

── (모든 변경 후 전수 검증) ──

"이제 전수 검증을 하자. verification.md를 참조."

→ read_skill("verification/verification.md")
→ validate_numbers(...)

"45행 중 44행 일치, 1행 불일치.
 행 23에서 DSD 당기 789,012인데 DOCX에 789,011이 들어가 있다.
 오타다. 수정하자."

→ set_cell_text(...)
→ read_cell(...)  "789,012 ✓"

"다시 검증... 45행 전부 일치! ✓"

── 이런 식으로 새로운 오류를 발견하면 ──

"이건 처음 보는 패턴인데... error_log.md에 기록해두자."

→ update_skill("troubleshooting/error_log.md",
    "## 2025-03-21: vMerge 행의 값이 누락됨\n"
    "증상: 수직 병합된 셀의 첫 행 값만 업데이트되고 병합 범위 내 다른 행은 빈칸\n"
    "원인: vMerge continuation 셀은 rowspan=0으로 표시되어 건너뛰어짐\n"
    "해결: vMerge restart 셀만 업데이트하면 병합 영역 전체에 반영됨")
```

### 5.2 유연한 워크플로우의 의미

**정해진 파이프라인**:
```
parse → match → translate → write → review (항상 이 순서)
```

**유연한 Agent**:
```
read DSD structure
  → "재무제표가 먼저 눈에 들어온다. BS부터 하자"
  → BS 매칭 + 업데이트 + 검증
  → "IS도 바로 하자"
  → IS 매칭 + 업데이트 + 검증
  → "주석으로 넘어가자. 주석 1부터..."
  → 주석 1 읽기 → "텍스트만 있네. 변경 없을 수도. 비교해보자"
  → (전기와 동일) → "스킵"
  → 주석 2 읽기 → "테이블이 있다. 매칭해보자"
  → 매칭 시도 → 실패 → "column이 이상하다" → column 정보 확인 → 재시도 → 성공
  → ...
  → "전체 검증하자"
  → 오류 3건 발견 → 수정 → 재검증 → 오류 1건 → 수정 → 재검증 → OK!
  → "연도 롤링을 아직 안 했다"
  → 연도 롤링 수행 → 검증
  → DONE
```

Agent가 **상황에 따라 순서를 결정**한다.
주석 1이 변경 없으면 건너뛰고, 어려운 주석은 나중에 돌아오고,
문제가 생기면 다른 방법을 시도하고.

### 5.3 "실패로부터 배우는" 메커니즘

```
시도 → 실패 → 분석 → 재시도 사이클:

[시도 1]
  set_cell_text(table=3, row=5, col=1, text="123,456")
  read_cell(table=3, row=5, col=1) → "" (빈칸?!)

[분석]
  "값이 안 들어갔다. col 1이 spacer column인가?"
  get_column_info(table=3) → "col 1 = spacer (width=58)"
  "아, col 1은 spacer다. 실제 데이터 열은 col 2다."

[메모]
  write_memo("table_3_columns", "col 1은 spacer. 데이터는 col 2부터")

[시도 2]
  set_cell_text(table=3, row=5, col=2, text="123,456")
  read_cell(table=3, row=5, col=2) → "123,456" ✓

[학습]
  "이 문서에는 spacer column이 있다.
   다른 테이블도 같을 수 있으니 항상 column info를 먼저 확인하자."
  write_memo("lesson", "이 문서의 테이블은 spacer column 있음. 항상 확인 필요")
```

---

## 6. System Prompt 설계

### 6.1 핵심 System Prompt

```python
SYSTEM_PROMPT = """
당신은 한국 IFRS 재무제표를 영문으로 변환하는 전문 AI Agent입니다.

## 당신의 업무
전기(prior year) 영문 재무제표 DOCX를 템플릿으로 사용하여,
당기(current year) 한글 DSD 데이터를 반영한 당기 영문 재무제표를 생성합니다.

## 일하는 방식

당신은 사람처럼 유연하게 일합니다:

1. **먼저 파악한다**: 두 파일을 열어보고 구조를 이해합니다
2. **계획을 세운다**: 무엇을 어떤 순서로 할지 판단합니다
3. **하나씩 실행한다**: 한 번에 하나의 작업을 수행합니다
4. **매번 확인한다**: 변경 후 반드시 결과를 검증합니다
5. **문제가 생기면 대처한다**: 실패하면 원인을 분석하고 다른 방법을 시도합니다
6. **모르면 찾아본다**: Skill Documents에서 관련 노하우를 참조합니다
7. **배운 것을 기록한다**: 이번 세션에서 발견한 패턴을 메모합니다
8. **끝나면 전수 검증한다**: 모든 작업 완료 후 처음부터 끝까지 검증합니다

## Skill Documents

skills/ 폴더에 축적된 노하우 문서들이 있습니다.
작업 전에 관련 스킬을 읽어보세요. 특히:
- 처음 시작할 때: overview.md
- DOCX를 편집할 때: editing/docx_editing.md
- 테이블을 매칭할 때: matching/table_matching.md
- 문제가 생겼을 때: troubleshooting/common_errors.md

새로운 패턴이나 오류를 발견하면 update_skill()로 기록하세요.

## DOCX 편집 원칙 (가장 중요)

1. **서식은 생명**: 기존 서식을 절대 깨뜨리지 마세요
2. **Clone & Modify**: 새 요소를 만들지 말고 기존 것을 복제해서 수정
3. **한 번에 하나씩**: 대량 변경 대신 소단위로 변경하고 매번 확인
4. **확신 없으면 멈춤**: 서식이 깨질 위험이 있으면 변경하지 말고 보고

## 검증 원칙

- 셀 값 변경 후: read_cell()로 확인
- 행 추가/삭제 후: read_table()로 전체 확인
- 전체 작업 완료 후: validate_numbers()로 전수 비교
- 연도 롤링 후: 이전 연도가 남아있지 않은지 검색

## 사용 가능한 도구

(tool schema 자동 주입)
"""
```

### 6.2 overview.md (Agent가 처음 읽는 문서)

```markdown
# 영문 재무제표 생성 - 전체 가이드

## 업무 흐름 (참고용 - 반드시 이 순서를 따를 필요 없음)

### Phase 1: 분석
1. DSD 구조 파악 (read_dsd_structure)
2. DOCX 구조 파악 (read_docx_structure)
3. 매칭 관계 파악 (어떤 DSD 섹션이 어떤 DOCX 섹션에 대응하는지)
4. 신규/삭제 주석 식별

### Phase 2: 재무제표 업데이트 (가장 중요)
1. 재무상태표 (BS) - 자산, 부채, 자본
2. 포괄손익계산서 (IS) - 수익, 비용, 이익
3. 자본변동표 (CE) - 자본 변동 내역
4. 현금흐름표 (CF) - 현금 흐름
각 재무제표마다: 행 매칭 → 값 업데이트 → 검증

### Phase 3: 주석 업데이트
주석을 하나씩 순서대로:
1. DSD 주석 읽기
2. 대응하는 DOCX 주석 찾기
3. 비교하여 변경 필요 부분 식별
4. 숫자 업데이트, 텍스트 번역/교체
5. 검증

### Phase 4: 연도 롤링
- Header/Footer
- 테이블 헤더
- 본문 문단
- ⚠️ skills/editing/year_rolling.md 반드시 참조

### Phase 5: 최종 검증
- 전수 숫자 비교
- 연도 일관성 확인
- 누락 주석 확인
- 서식 보존 확인

## 중요한 팁
- 어려운 부분은 나중에 돌아와도 됩니다
- 확실한 것부터 먼저 처리하세요
- 문제가 생기면 troubleshooting/common_errors.md를 참조하세요
- 3번 시도해도 안 되면 escalate하세요
```

---

## 7. Tool Layer 상세

### 7.1 읽기 도구

```python
@tool("read_dsd_structure")
def read_dsd_structure(dsd_path: str) -> str:
    """DSD 파일의 전체 구조를 텍스트로 반환."""

@tool("read_docx_structure")
def read_docx_structure(docx_path: str) -> str:
    """DOCX 파일의 전체 구조를 텍스트로 반환."""

@tool("read_table")
def read_table(source: str, table_index: int, max_rows: int = 50) -> str:
    """특정 테이블 내용을 마크다운 형태로 반환."""

@tool("read_cell")
def read_cell(table_index: int, row: int, col: int) -> str:
    """특정 셀의 값 읽기."""

@tool("read_note")
def read_note(source: str, note_number: str) -> str:
    """특정 주석의 전체 내용 반환."""

@tool("read_header_footer")
def read_header_footer() -> str:
    """모든 header/footer 텍스트 반환."""

@tool("search_text")
def search_text(query: str) -> str:
    """DOCX 전체에서 텍스트 검색. 연도 잔존 확인 등에 사용."""
```

### 7.2 분석 도구

```python
@tool("compare_tables")
def compare_tables(dsd_table_index: int, docx_table_index: int) -> str:
    """DSD/DOCX 테이블을 나란히 비교. 값 기반 매칭 힌트 포함."""

@tool("get_column_info")
def get_column_info(table_index: int) -> str:
    """DOCX 테이블의 column 정보 (spacer, physical/logical mapping)."""

@tool("validate_numbers")
def validate_numbers(
    dsd_table_index: int,
    docx_table_index: int,
    row_mapping: list[tuple[int, int]],
) -> str:
    """숫자 정합성 전수 검증."""
```

### 7.3 편집 도구 (서식 보존 내장)

```python
@tool("set_cell_text")
def set_cell_text(table_index: int, row: int, physical_col: int, text: str) -> str:
    """셀 텍스트 변경. 기존 Run 서식을 보존."""

@tool("clone_row")
def clone_row(
    table_index: int, source_row: int,
    insert_after: int, cell_texts: dict[int, str],
) -> str:
    """기존 행을 deepcopy하여 삽입. 서식 100% 보존."""

@tool("delete_row")
def delete_row(table_index: int, row: int) -> str:
    """행 삭제."""

@tool("replace_text_in_paragraph")
def replace_text_in_paragraph(
    paragraph_index: int, old_text: str, new_text: str,
) -> str:
    """문단 텍스트 교체. Run 경계 넘는 텍스트도 처리."""

@tool("replace_in_headers_footers")
def replace_in_headers_footers(replacements: list[tuple[str, str]]) -> str:
    """Header/Footer 텍스트 일괄 교체. Cross-run 대응."""

@tool("replace_in_table_headers")
def replace_in_table_headers(replacements: list[tuple[str, str]]) -> str:
    """모든 테이블 헤더(상위 2행) 텍스트 교체."""

@tool("replace_in_body")
def replace_in_body(replacements: list[tuple[str, str]]) -> str:
    """본문 문단 텍스트 교체."""
```

### 7.4 번역 도구

```python
@tool("translate")
def translate(
    texts: list[str],
    context: str = "",
    glossary: dict[str, str] | None = None,
) -> list[str]:
    """한→영 번역. Glossary와 맥락 정보 활용."""
```

### 7.5 지식/메모 도구

```python
@tool("read_skill")
def read_skill(skill_path: str) -> str:
    """Skill Document 읽기."""

@tool("list_skills")
def list_skills() -> str:
    """사용 가능한 Skill Document 목록."""

@tool("update_skill")
def update_skill(skill_path: str, content: str) -> str:
    """Skill Document 업데이트 (새 패턴 기록)."""

@tool("write_memo")
def write_memo(key: str, content: str) -> str:
    """작업 메모 저장."""

@tool("read_memo")
def read_memo(key: str) -> str:
    """작업 메모 읽기."""

@tool("list_memos")
def list_memos() -> str:
    """저장된 메모 목록."""
```

### 7.6 완료/보고 도구

```python
@tool("save_docx")
def save_docx(output_path: str) -> str:
    """최종 DOCX 저장."""

@tool("escalate")
def escalate(issue_type: str, description: str, suggestion: str) -> str:
    """자동 해결 불가 시 사람에게 보고."""

@tool("final_report")
def final_report(summary: str, stats: dict) -> str:
    """최종 작업 보고서 생성."""
```

---

## 8. 컨텍스트 관리

### 8.1 문제: LLM 컨텍스트 윈도우 한계

재무제표 하나를 처리하는 데 수백 번의 Tool 호출이 필요.
모든 대화 이력을 유지하면 컨텍스트 윈도우를 초과.

### 8.2 해결: 단계별 요약 + Working Memory

```python
class ContextManager:
    """
    대화가 길어지면 완료된 작업을 요약하여 압축.
    핵심 정보는 Working Memory에 저장되어 있으므로 안전.
    """

    COMPRESS_THRESHOLD = 80  # 메시지 수

    def should_compress(self, messages: list) -> bool:
        return len(messages) > self.COMPRESS_THRESHOLD

    def compress(self, messages: list) -> list:
        system = messages[0]
        old = messages[1:-20]
        recent = messages[-20:]

        # 완료된 작업을 요약
        summary = self._summarize_completed_work(old)

        # 현재 Working Memory의 핵심 정보도 포함
        memos = self._get_key_memos()

        return [
            system,
            {
                "role": "user",
                "content": (
                    f"[이전 작업 요약]\n{summary}\n\n"
                    f"[현재 메모]\n{memos}\n\n"
                    "위 작업에 이어서 계속하세요."
                ),
            },
            {
                "role": "assistant",
                "content": "이전 작업을 확인했습니다. 이어서 진행하겠습니다.",
            },
            *recent,
        ]
```

### 8.3 Working Memory가 컨텍스트 압축을 보완

```
컨텍스트가 압축되어도 Working Memory에 핵심 정보가 남아있음:

memo["docx_structure"] → DOCX 전체 구조
memo["completed_notes"] → 완료된 주석 목록
memo["column_map_table_3"] → table 3의 column mapping
memo["glossary"] → 축적된 용어집
memo["lessons"] → 이번 세션에서 배운 것들
```

---

## 9. ReAct 루프 구현

### 9.1 핵심 코드

```python
class Agent:
    def __init__(self, llm: GenAIClient, tools: ToolRegistry, skills_dir: str):
        self.llm = llm
        self.tools = tools
        self.skills_dir = skills_dir
        self.memory = WorkingMemory()
        self.messages: list[dict] = []
        self.context_mgr = ContextManager()

    async def run(self, dsd_path: str, docx_path: str, output_path: str):
        # 1. System prompt + 초기 지시
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": self._initial_instruction(dsd_path, docx_path, output_path)},
        ]

        # 2. ReAct 루프
        max_steps = 500
        for step in range(max_steps):

            # 컨텍스트 압축 (필요 시)
            if self.context_mgr.should_compress(self.messages):
                self.messages = self.context_mgr.compress(self.messages)

            # LLM 호출
            response = await self.llm.call(
                messages=self.messages,
                tools=self.tools.schema(),
                temperature=0.1,
            )

            # Tool 호출 처리
            if response.has_tool_calls():
                self.messages.append({"role": "assistant", "content": response.raw})

                results = []
                for tc in response.tool_calls:
                    result = await self._execute_tool(tc)
                    results.append(result)

                self.messages.append({"role": "tool", "content": results})

            # 완료 (Tool 호출 없이 텍스트만 반환)
            elif response.is_final():
                return self._finalize(response)

        raise AgentTimeout("최대 step 초과")

    async def _execute_tool(self, tool_call) -> dict:
        """도구 실행 + 로깅."""
        try:
            result = await self.tools.execute(tool_call.name, tool_call.args)
            return {"id": tool_call.id, "result": str(result)}
        except Exception as e:
            # 오류도 LLM에게 전달 — LLM이 대응 판단
            return {"id": tool_call.id, "result": f"ERROR: {e}"}
```

### 9.2 오류 처리: LLM이 판단

```
Tool이 오류를 반환하면, LLM이 직접 대응:

LLM: set_cell_text(table=3, row=50, col=2, text="123")
Tool: "ERROR: row 50 does not exist (table has 45 rows)"

LLM: "행 50이 없다. 아마 행 인덱스를 잘못 계산한 것 같다.
      테이블을 다시 읽어보자."
      → read_table(source="docx", table_index=3)
      "45행이고, 내가 찾는 '기타자산'은 행 42에 있다."
      → set_cell_text(table=3, row=42, col=2, text="123")
      → read_cell(table=3, row=42, col=2) → "123" ✓
```

---

## 10. Skill Document 학습 메커니즘

### 10.1 Agent가 스스로 학습하는 흐름

```
[세션 중 새로운 패턴 발견]

Agent: "이 DOCX에서 테이블의 마지막 행(합계)은 bold로 되어있고,
        굵은 하단 테두리가 있다. 이 패턴을 기록해두자."

→ update_skill("editing/cell_editing.md",
    append="## 합계 행 식별\n합계 행은 보통 bold + 하단 테두리. "
           "합계 값을 업데이트할 때 이 서식이 유지되는지 확인.\n")

[다음 세션에서]

Agent: "셀 값을 바꿔야 하는데, cell_editing.md를 참조하자."
→ read_skill("editing/cell_editing.md")
→ "아, 합계 행은 bold + 하단 테두리가 있을 수 있구나.
    이 셀이 합계인지 확인하고 서식이 보존되는지 확인하자."
```

### 10.2 사람이 Skill을 추가하는 흐름

```
[사람이 새 회사의 특이사항을 발견]

사람: skills/companies/company_xyz.md 파일 생성

```markdown
# XYZ 회사 특이사항
- 주석 번호가 1부터가 아니라 3부터 시작 (1, 2는 목차)
- 자본변동표가 가로/세로 반전된 형태
- 영문 표현이 US GAAP 스타일 (IFRS와 다름)
```

[Agent가 XYZ 회사 파일을 처리할 때]

Agent: "새 회사다. 혹시 회사별 스킬이 있나?"
→ list_skills()
→ "companies/company_xyz.md가 있다!"
→ read_skill("companies/company_xyz.md")
→ "아, 주석 번호가 3부터 시작하는구나. 주의하자."
```

---

## 11. 파일 구조

```
eng_fs_creation/
├── agent/
│   ├── __init__.py
│   ├── agent.py             # ReAct 루프, 핵심 Agent 클래스
│   ├── context_manager.py   # 컨텍스트 압축
│   ├── working_memory.py    # 세션 내 메모
│   ├── system_prompt.py     # System prompt 텍스트
│   └── report.py            # 최종 보고서 생성
│
├── agent/tools/
│   ├── __init__.py           # ToolRegistry
│   ├── read_tools.py         # 읽기 도구
│   ├── write_tools.py        # 쓰기 도구 (서식 보존 내장)
│   ├── analysis_tools.py     # 분석/비교 도구
│   ├── translate_tool.py     # 번역 도구
│   ├── knowledge_tools.py    # Skill/Memo 도구
│   └── report_tools.py       # 저장/보고 도구
│
├── agent/tools/docx_ops/
│   ├── cell_writer.py        # 서식 보존 셀 쓰기
│   ├── row_cloner.py         # 행 deepcopy
│   ├── text_replacer.py      # Cross-run 텍스트 교체
│   ├── column_mapper.py      # Logical/Physical column 매핑
│   └── xml_helpers.py        # lxml 유틸
│
├── skills/                   # Skill Documents (Agent의 참조 지식)
│   ├── overview.md
│   ├── understanding/
│   │   ├── dsd_format.md
│   │   ├── docx_format.md
│   │   └── fs_structure.md
│   ├── matching/
│   │   ├── table_matching.md
│   │   ├── note_matching.md
│   │   └── value_validation.md
│   ├── editing/
│   │   ├── docx_editing.md
│   │   ├── cell_editing.md
│   │   ├── row_operations.md
│   │   ├── year_rolling.md
│   │   └── column_mapping.md
│   ├── translation/
│   │   ├── translation.md
│   │   ├── ifrs_terms.md
│   │   └── number_format.md
│   ├── verification/
│   │   ├── verification.md
│   │   └── cross_check.md
│   ├── troubleshooting/
│   │   ├── common_errors.md
│   │   └── error_log.md
│   └── companies/            # 회사별 특이사항 (축적)
│       └── .gitkeep
│
├── utils/
│   └── genai_client.py       # PwC GenAI Gateway 클라이언트
│
├── config.py
└── agent_main.py             # 진입점
```

---

## 12. 구현 로드맵

### Phase 1: Tool Layer (2주)
```
- [ ] docx_ops/ — 서식 보존 핵심 로직 (기존 코드 리팩토링)
- [ ] read_tools.py — 구조/테이블/셀 읽기
- [ ] write_tools.py — 셀 쓰기, 행 복제, 텍스트 교체
- [ ] analysis_tools.py — 테이블 비교, column 정보
- [ ] ToolRegistry — 등록, 실행, 로깅, 스키마 생성
```

### Phase 2: Agent Core (1주)
```
- [ ] agent.py — ReAct 루프
- [ ] context_manager.py — 컨텍스트 압축
- [ ] system_prompt.py — 프롬프트 설계
- [ ] working_memory.py — 메모 시스템
```

### Phase 3: Skill Documents (1주)
```
- [ ] 이번 세션에서 배운 모든 노하우를 md로 정리
- [ ] knowledge_tools.py — read/update/list skill
- [ ] overview.md + 모든 하위 스킬 문서
```

### Phase 4: 번역 + 검증 (1주)
```
- [ ] translate_tool.py
- [ ] validate_tools.py
- [ ] report_tools.py
```

### Phase 5: 실전 테스트 + 개선 (1주)
```
- [ ] 다양한 회사 파일로 테스트
- [ ] Agent가 실패하는 케이스 수집
- [ ] Skill Document 보강
- [ ] 프롬프트 튜닝
```

---

## 13. 이전 설계와 비교

| 항목 | v1 (규칙 기반) | v2 (LLM 주도 고정) | v3 (유연한 Agent) |
|------|--------------|-------------------|------------------|
| 워크플로우 | 고정 파이프라인 | 고정 순서 + LLM 판단 | **LLM이 상황에 따라 결정** |
| 실패 대응 | 사전 정의된 패턴만 | LLM이 진단하나 흐름은 고정 | **시도→실패→분석→재시도 루프** |
| 지식 관리 | 코드에 하드코딩 | System prompt에 주입 | **Skill Documents로 분리** |
| 학습 | 없음 | 없음 | **Agent가 새 패턴을 기록** |
| 새 회사 대응 | 코드 수정 필요 | LLM이 적응 (prompt 고정) | **회사별 Skill 추가** |
| 컨텍스트 | 정해진 데이터만 | 전체 상태 주입 | **필요할 때 필요한 것만 참조** |
| 사람 개입 | 많음 | 에스컬레이션 | **Skill 추가로 점진적 자동화** |

---

## 14. 성공 지표

| 지표 | 목표 | 의미 |
|------|------|------|
| 숫자 정확도 | >= 99% | DSD 원본 vs 출력 DOCX |
| 주석 완전성 | >= 95% | 모든 주석이 반영되었는지 |
| 서식 보존 | 육안 구별 불가 | 원본 DOCX와 비교 |
| 자동 처리율 | >= 80% | 에스컬레이션 없이 완료 |
| 재시도 수렴 | 3회 이내 | 오류 발견→수정→재검증이 3회 안에 수렴 |
| 처리 시간 | < 15분 | end-to-end |

# CLAUDE.md — SARA Agent Application 개발 마스터 가이드

## 프로젝트 개요

**SARA** (국영문 보고서 대사) — 한국어 재무제표(DSD/DART)를 영문 재무제표(DOCX)로 변환하는 AI Agent 웹 애플리케이션.
PwC GenAI Gateway의 Claude Sonnet을 사용하는 ReAct 패턴 기반 자율 Agent.

## 기술 스택

| 레이어 | 기술 | 비고 |
|--------|------|------|
| **Frontend** | Next.js 14+ (App Router, TypeScript, Tailwind CSS) | PwC 브랜딩 3-Step UI |
| **Backend** | FastAPI (Python, uvicorn) | REST API + SSE 스트리밍 |
| **Agent Core** | Python (async/await) | ReAct 루프, JSON Tool Use 시뮬레이션 |
| **LLM** | PwC GenAI Gateway → `bedrock.anthropic.claude-sonnet-4-6` | Responses API |
| **DOCX 조작** | python-docx + lxml | 서식 보존 XML 직접 조작 |
| **실시간 통신** | SSE (Server-Sent Events) | Agent 로그 → Frontend 실시간 스트리밍 |
| **로고** | `_PwC_logo_2025.png` → `frontend/public/pwc-logo.png` | |

## 프로젝트 구조

```
eng_fs_creation/
│
├── agent/                    # Agent 코어 (Python)
│   ├── agent.py              # ReAct 루프 + log_callback
│   ├── context_manager.py    # 컨텍스트 압축
│   ├── working_memory.py     # 세션 메모리
│   ├── system_prompt.py      # System Prompt 빌더
│   ├── report.py             # 최종 보고서
│   └── tools/                # LLM 호출 도구 (27개)
│       ├── __init__.py       # ToolRegistry
│       ├── read_tools.py     # 7 읽기 도구
│       ├── write_tools.py    # 6 쓰기 도구
│       ├── analysis_tools.py # 3 분석 도구
│       ├── translate_tool.py # 3 번역 도구 (전기 재사용 원칙)
│       ├── knowledge_tools.py# 5 지식 도구
│       ├── report_tools.py   # 3 완료 도구
│       └── docx_ops/         # DOCX 저수준 조작 (리팩토링)
│           ├── xml_helpers.py
│           ├── cell_writer.py
│           ├── row_cloner.py
│           ├── text_replacer.py
│           └── column_mapper.py
│
├── backend/                  # FastAPI 백엔드
│   ├── app/
│   │   ├── main.py           # FastAPI app
│   │   ├── config.py         # 환경 설정 (Pydantic Settings)
│   │   ├── models.py         # Pydantic 모델
│   │   ├── routers/
│   │   │   └── jobs.py       # POST/GET/STREAM/DOWNLOAD/DELETE
│   │   ├── services/
│   │   │   ├── job_manager.py # Job 생명주기 + Agent 실행
│   │   │   └── file_manager.py
│   │   └── middleware/
│   │       └── cors.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                 # Next.js 프론트엔드
│   ├── public/
│   │   └── pwc-logo.png      # PwC 로고
│   ├── src/
│   │   ├── app/              # App Router (layout, page)
│   │   ├── components/       # Header, StepIndicator, FileUpload,
│   │   │                     # AgentLog, ProgressBar, ResultSummary
│   │   ├── hooks/            # useConversionState, useSSE
│   │   ├── lib/              # api.ts, types.ts
│   │   └── styles/           # PwC 테마
│   ├── tailwind.config.ts
│   └── package.json
│
├── agent_skills/             # Agent 참조 지식 (19 md files)
├── skills/                   # 기존 규칙 기반 파이프라인 (원본 코드)
├── utils/                    # 공통 유틸 (genai_client, xml_helpers 등)
├── docker-compose.yml        # 전체 서비스 구성
└── CLAUDE.md                 # 이 파일
```

## 아키텍처

```
┌─────────────┐     HTTP/SSE     ┌──────────────┐     async     ┌─────────┐
│   Next.js   │ ←──────────────→ │   FastAPI    │ ←──────────→ │  Agent  │
│  Frontend   │   REST + SSE     │   Backend    │  log_callback │  Core   │
│  :3000      │                  │  :8000       │               │         │
└─────────────┘                  └──────┬───────┘               └────┬────┘
                                        │ file I/O                   │ API
                                        ▼                            ▼
                                   uploads/outputs              PwC GenAI
                                                                Gateway
```

## 개발 계획 (7 Phase)

**상세 계획**: `.claude/development_plan.md`

| Phase | 모듈 | 내용 | 상태 |
|-------|------|------|------|
| 1 | docx_ops | 기존 코드 리팩토링 → 독립 모듈 | ⬜ |
| 2 | tools | 27개 LLM 도구 구현 | ⬜ |
| 3 | agent core | ReAct 루프, 컨텍스트 관리 | ⬜ |
| 4 | testing | 단위/통합 테스트, 프롬프트 튜닝 | ⬜ |
| 5 | backend | FastAPI 서버 (REST + SSE) | ⬜ |
| 6 | frontend | Next.js UI (3-Step 워크플로우) | ⬜ |
| 7 | integration | Docker, E2E 테스트, 배포 | ⬜ |

## 최우선 과제

### 1순위: 테이블 서식 보존
DOCX 템플릿의 서식(폰트, 정렬, 병합, 열 너비 등)을 완벽히 보존하면서 데이터만 교체.
절대 XML 요소를 직접 생성하지 않고, 기존 요소를 deepcopy하여 수정.

### 2순위: 번역 — 전기 영문 재사용 원칙
DOCX 템플릿 = 전기 영문 보고서. 이미 감사인이 검토한 완성된 번역이 있다.

**번역 4-Tier 우선순위**:
| Tier | 조건 | 처리 | 비율 |
|------|------|------|------|
| 1 | 전기와 동일한 한국어 | 전기 DOCX 영문 그대로 사용 (번역 X) | ~80% |
| 2 | 전기와 유사하지만 약간 변경 | 전기 영문 기반 최소 조정 | ~10% |
| 3 | 완전히 새로운 문구 | 전기 문체/스타일에 맞춰 번역 | ~8% |
| 4 | 맥락 없는 경우 | IFRS 용어 + LLM 번역 | ~2% |

**핵심**: "새로 번역" 이 아니라 "전기 영문 계승 + 변경분만 최소 조정"

## 개발 스킬 (Skills)

구현 시 참조할 상세 명세서. `.claude/skills/` 아래:

| 스킬 파일 | 용도 | Phase |
|-----------|------|-------|
| `docx_ops_refactor.md` | 기존→신규 코드 매핑, 함수 시그니처 | 1 |
| `tool_registry.md` | ToolRegistry 클래스, @tool 데코레이터, 전체 도구 목록 | 2 |
| `read_tools.md` | 7개 읽기 도구 명세 | 2 |
| `write_tools.md` | 6개 쓰기 도구 명세 | 2 |
| `analysis_tools.md` | 3개 분석 도구 명세 | 2 |
| `translate_tool.md` | 3개 번역 도구 (전기 재사용 4-Tier) | 2 |
| `react_loop.md` | ReAct 루프, 응답 파싱, 오류 처리 | 3 |
| `context_management.md` | 컨텍스트 압축, Working Memory | 3 |
| `system_prompt_design.md` | System Prompt 구조와 내용 | 3 |
| `testing_strategy.md` | 4단계 테스트 전략 | 4 |
| `backend_api.md` | FastAPI 엔드포인트, Job Manager, SSE | 5 |
| `frontend_design.md` | Next.js UI 설계, PwC 브랜딩, 컴포넌트 | 6 |

## 서브에이전트 (Subagents)

독립적인 개발 단위별 작업 지침. `.claude/subagents/` 아래:

| 서브에이전트 | 역할 | Phase |
|------------|------|-------|
| `docx_ops_builder.md` | docx_ops/ 리팩토링 실행 | 1 |
| `tool_layer_builder.md` | 27개 도구 구현 | 2 |
| `agent_core_builder.md` | ReAct 루프 + 컨텍스트 관리 구현 | 3 |
| `integration_tester.md` | 테스트 작성 및 실행 | 4 |
| `backend_builder.md` | FastAPI 서버 구현 | 5 |
| `frontend_builder.md` | Next.js UI 구현 | 6 |

## UI 디자인 (SARA)

PwC 브랜딩 기반 3-Step 워크플로우:
- **Step 1 — 파일 업로드**: DSD + DOCX 드래그앤드롭 → "대사 시작" 버튼
- **Step 2 — 처리 중**: 실시간 Agent 로그 스트리밍 + 진행률 바
- **Step 3 — 완료**: 결과 요약 + DOCX 다운로드

**디자인 컬러**:
- PwC Orange: `#D04A02` (액센트, 활성 요소)
- Background: `#F5F5F5`
- Cards: `#FFFFFF`
- Text: `#2D2D2D`

**로고**: `_PwC_logo_2025.png` → `frontend/public/pwc-logo.png`

## 기존 코드 참조

| 기존 파일 | 재활용 방식 |
|-----------|------------|
| `skills/write_docx/docx_cell_writer.py` | → `docx_ops/cell_writer.py` 리팩토링 |
| `skills/write_docx/docx_row_writer.py` | → `docx_ops/row_cloner.py` 리팩토링 |
| `skills/write_docx/docx_header_writer.py` | → `docx_ops/text_replacer.py` 리팩토링 |
| `skills/parse_docx/docx_table_parser.py` | → `docx_ops/column_mapper.py` 리팩토링 |
| `utils/xml_helpers.py` | → `docx_ops/xml_helpers.py` 복사 |
| `utils/genai_client.py` | 그대로 사용 |
| `utils/number_format.py` | 그대로 사용 |
| `ir_schema.py` | 그대로 사용 |
| `agent_skills/*.md` | Agent가 런타임에 read_skill로 참조 |

## 작업 시작 방법

### Phase 1: docx_ops
```
→ .claude/subagents/docx_ops_builder.md 참조
→ .claude/skills/docx_ops_refactor.md 상세 명세
→ 원본 코드 읽기 → 핵심 로직 추출 → 독립 모듈 작성 → 테스트
```

### Phase 2: Tool Layer (Phase 1 완료 후)
```
→ .claude/subagents/tool_layer_builder.md 참조
→ .claude/skills/tool_registry.md, read_tools.md, write_tools.md 등
→ ToolRegistry 구현 → 각 도구 구현 → DocumentContext 구현
```

### Phase 3: Agent Core (Phase 2 완료 후)
```
→ .claude/subagents/agent_core_builder.md 참조
→ .claude/skills/react_loop.md, context_management.md, system_prompt_design.md
→ pwc_llm_api.md로 Gateway API 연동
```

### Phase 4: Testing (Phase 3 완료 후)
```
→ .claude/subagents/integration_tester.md 참조
→ .claude/skills/testing_strategy.md
→ 단위 테스트 → 통합 테스트 → 프롬프트 튜닝
```

### Phase 5: Backend (Phase 3 완료 후, Phase 4와 병행 가능)
```
→ .claude/subagents/backend_builder.md 참조
→ .claude/skills/backend_api.md
→ FastAPI 초기화 → Job Manager → SSE 스트리밍 → Agent 연결
```

### Phase 6: Frontend (Phase 5 완료 후)
```
→ .claude/subagents/frontend_builder.md 참조
→ .claude/skills/frontend_design.md
→ Next.js 초기화 → PwC 테마 → Step 1/2/3 구현 → API 연동
```

### Phase 7: Integration
```
→ docker-compose.yml 작성
→ E2E 테스트 (파일 업로드 → Agent 실행 → 결과 다운로드)
→ PwC 내부 배포
```

## 코딩 규칙

### Python (Agent + Backend)
- Python 3.10+
- async/await (LLM 호출, FastAPI 모두 비동기)
- 타입 힌트 필수
- docstring 한국어
- 에러는 예외 대신 문자열 반환 (Agent Tool에서)
- lxml 사용 시 OOXML 네임스페이스 상수 활용

### TypeScript (Frontend)
- TypeScript strict mode
- Tailwind CSS (인라인 스타일 지양)
- 컴포넌트는 함수형 + hooks
- API 타입은 lib/types.ts에 중앙 관리

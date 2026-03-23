# 영문 재무제표 생성 - 전체 가이드

## 업무 개요

전기(prior year) 영문 재무제표 DOCX를 템플릿으로 사용하여,
당기(current year) 한글 DSD 데이터를 반영한 당기 영문 재무제표를 생성한다.

- 입력 1: DSD 파일 (한글 재무제표, DART XML ZIP)
- 입력 2: DOCX 파일 (전기 영문 재무제표, Word 문서)
- 출력: DOCX 파일 (당기 영문 재무제표)

## 작업 흐름 (참고용 - 상황에 따라 유연하게)

### Phase 1: 파일 분석
1. DSD 파일을 열어서 구조 파악
   - 회사명, 보고기간 (당기/전기), 연결/별도 구분
   - 재무제표 4개 (BS, IS, CE, CF)의 행/열 구조
   - 주석 목록과 각 주석의 내용 (테이블, 문단, 소제목)
2. DOCX 파일을 열어서 구조 파악
   - 회사명, 보고기간, 연결/별도 구분
   - 재무제표 4개의 행/열 구조
   - 주석 목록과 각 주석의 내용
   - **Spacer column 유무 확인** (→ editing/column_mapping.md 참조)
3. 매칭 관계 파악
   - DSD 주석 번호 ↔ DOCX 주석 번호 대응
   - 신규 주석 (DSD에만 있음), 삭제된 주석 (DOCX에만 있음) 식별

### Phase 2: 재무제표 업데이트 (가장 중요)
재무제표는 감사보고서의 핵심이므로 가장 먼저, 가장 신중하게 처리한다.

1. **재무상태표 (BS)** - Statement of Financial Position
   - 자산, 부채, 자본 항목
   - 자산총계 = 부채총계 + 자본총계 반드시 확인
2. **포괄손익계산서 (IS)** - Statement of Comprehensive Income
   - 매출, 원가, 영업이익, 당기순이익
3. **자본변동표 (CE)** - Statement of Changes in Equity
   - 가로축: 자본금, 자본잉여금, 이익잉여금 등
   - 세로축: 기초잔액, 변동, 기말잔액
4. **현금흐름표 (CF)** - Statement of Cash Flows
   - 영업/투자/재무 활동
   - 기초현금 + 증감 = 기말현금 확인

각 재무제표 처리 순서:
- 행 매칭 (→ matching/table_matching.md 참조)
- 값 업데이트 (→ editing/cell_editing.md 참조)
- 검증

### Phase 3: 주석 업데이트
주석을 하나씩 순서대로 처리:
1. DSD 주석 읽기
2. 대응하는 DOCX 주석 찾기 (→ matching/note_matching.md 참조)
3. 비교하여 변경 필요 부분 식별
4. 숫자 업데이트 + 텍스트 번역/교체 (→ translation/translation.md 참조)
5. 검증

### Phase 4: 연도 롤링
- Header/Footer의 연도 교체
- 테이블 헤더의 연도 교체
- 본문 문단의 연도 교체
- **반드시 editing/year_rolling.md 참조**

### Phase 5: 최종 검증
- 전수 숫자 비교 (→ verification/verification.md 참조)
- 연도 일관성 확인
- 누락 주석 확인
- 서식 보존 확인

## 중요한 팁
- 어려운 부분은 나중에 돌아와도 된다
- 확실한 것부터 먼저 처리
- 문제가 생기면 troubleshooting/common_errors.md 참조
- 3번 시도해도 안 되면 escalate
- **DOCX 서식 보존이 가장 중요** (→ editing/docx_editing.md 참조)

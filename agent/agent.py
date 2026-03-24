"""
ReAct Agent — Reason-Act-Observe 패턴의 자율 Agent.

PwC GenAI Gateway를 사용하여 JSON 기반 Tool Use 시뮬레이션.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Callable

from agent.tools import ToolRegistry, collect_tools
from agent.document_context import DocumentContext
from agent.working_memory import WorkingMemory
from agent.context_manager import ContextManager
from agent.system_prompt import build_system_prompt, build_initial_instruction

from agent.tools import read_tools, write_tools, analysis_tools, knowledge_tools, translate_tool, report_tools
from agent.year_roller import apply_year_rolling
from agent.note_filler import apply_note_filling
from agent.auto_verifier import verify_fill_results, auto_fix_errors


class Agent:
    """ReAct 루프 기반 Agent."""

    def __init__(
        self,
        llm,
        skills_dir: str = "agent_skills",
        max_steps: int = 200,
        log_callback: Callable[[dict], None] | None = None,
    ):
        self.llm = llm
        self.skills_dir = skills_dir
        self.max_steps = max_steps
        self.log_callback = log_callback or (lambda x: None)

        self.ctx = DocumentContext()
        self.memory = WorkingMemory()
        self.context_mgr = ContextManager()
        self.tools = ToolRegistry()
        self.messages: list[dict] = []
        self._retry_count = 0
        self._step = 0
        self._last_action: str = ""
        self._repeat_count: int = 0

        self._log_path = f"/tmp/sara_agent_{time.strftime('%Y%m%d_%H%M%S')}.log"
        self._setup_tools()

    def _setup_tools(self) -> None:
        """모든 Tool 모듈을 등록."""
        # DocumentContext 주입
        read_tools.set_context(self.ctx)
        write_tools.set_context(self.ctx)
        analysis_tools.set_context(self.ctx)
        report_tools.set_context(self.ctx)

        # WorkingMemory / Skills 주입
        knowledge_tools.set_memory(self.memory)
        knowledge_tools.set_skills_dir(self.skills_dir)
        analysis_tools.set_memory(self.memory)

        # LLM 클라이언트 주입
        translate_tool.set_llm_client(self.llm)

        # 모든 모듈에서 @tool 함수 자동 수집
        collect_tools(
            [read_tools, write_tools, analysis_tools,
             knowledge_tools, translate_tool, report_tools],
            self.tools,
        )

    async def run(
        self,
        dsd_path: str,
        docx_path: str,
        output_path: str,
    ) -> dict:
        """Agent 실행. DSD + DOCX → 업데이트된 DOCX."""
        # 문서 로드
        self._log("info", f"DOCX 로딩: {docx_path}")
        await asyncio.to_thread(self.ctx.load_docx, docx_path)
        self._log("info", f"DOCX 로딩 완료 — 테이블 {self.ctx.num_tables()}개")

        try:
            self._log("info", f"DSD 로딩: {dsd_path}")
            await asyncio.to_thread(self.ctx.load_dsd, dsd_path)
            self._log("info", "DSD 로딩 완료")
        except Exception as e:
            self._log("warning", f"DSD 로딩 실패: {e} — DOCX만으로 진행")

        # 연도 롤링 (코드 기반 자동 처리)
        if self.ctx.dsd_data is not None:
            self._log("info", "연도 롤링 자동 처리 시작")
            try:
                yr_stats = await asyncio.to_thread(apply_year_rolling, self.ctx, self.ctx.dsd_data, self.log_callback)
                self._log("success", f"연도 롤링 완료 — {yr_stats.get('total_elements', 0)}개 요소 수정")
            except Exception as e:
                self._log("warning", f"연도 롤링 실패: {e} — Agent가 수동 처리합니다")

        # 주석 데이터 자동 채우기 (코드 기반)
        fill_matches = []
        if self.ctx.dsd_data is not None:
            self._log("info", "주석 데이터 자동 채우기 시작")
            try:
                fill_stats, fill_matches = await asyncio.to_thread(apply_note_filling, self.ctx, self.ctx.dsd_data, self.log_callback)
                self._log("success",
                    f"주석 자동 채우기 완료 — {fill_stats.get('tables_matched', 0)}개 테이블, "
                    f"{fill_stats.get('cells_updated', 0)}셀 업데이트")
                # Agent에게 자동 채우기 결과를 알림 (Working Memory에 저장)
                summary_lines = [
                    f"자동 채우기 완료: {fill_stats.get('tables_matched', 0)}개 테이블, {fill_stats.get('cells_updated', 0)}셀 업데이트",
                    f"DSD 테이블 {fill_stats.get('dsd_tables_found', 0)}개 중 {fill_stats.get('tables_matched', 0)}개 매칭됨",
                    "",
                    "매칭된 테이블:",
                ]
                for d in fill_stats.get("match_details", []):
                    summary_lines.append(f"  {d['note']} → DOCX Table {d['docx_table']} ({d['cells_updated']}셀)")
                self.memory.set("auto_fill_stats", "\n".join(summary_lines))
                # Glossary 저장
                glossary = fill_stats.get("glossary", {})
                if glossary:
                    glossary_lines = [f"{ko} → {en}" for ko, en in sorted(glossary.items())]
                    self.memory.set("glossary", "\n".join(glossary_lines))
                    self._log("info", f"한→영 glossary {len(glossary)}쌍 자동 구축")
            except Exception as e:
                self._log("warning", f"주석 자동 채우기 실패: {e} — Agent가 수동 처리합니다")

        # 자동 검증 (Auto-Verify)
        if self.ctx.dsd_data is not None and fill_matches:
            self._log("info", "자동 검증 시작")
            try:
                matches = fill_matches
                from agent.note_filler import extract_dsd_tables
                dsd_tables = extract_dsd_tables(self.ctx.dsd_data)

                # 검증 (auto_verifier의 _log는 문자열을 보내므로 래퍼 필요)
                def _verify_log(msg: str):
                    self._log("info", msg)

                verify_report = await asyncio.to_thread(verify_fill_results, self.ctx, self.ctx.dsd_data, matches, _verify_log)
                self._log("info", f"검증 완료: {verify_report.cells_checked}셀 검사, {verify_report.cells_wrong}개 오류, CRITICAL {verify_report.critical_count}개")

                # 자동 수정
                if verify_report.cells_wrong > 0:
                    self._log("info", "자동 수정 시작")
                    fixed = await asyncio.to_thread(auto_fix_errors, self.ctx, verify_report, matches, _verify_log)
                    self._log("success", f"자동 수정 완료: {fixed}셀 수정")

                # Working Memory에 검증 결과 저장
                self.memory.set("verify_report", verify_report.summary())
                unresolved = verify_report.unresolved_errors()
                if unresolved:
                    error_tables = sorted(set(
                        f"Table {e.table_index} (주석 {e.note_number}): {e.error_type}"
                        for e in unresolved
                    ))
                    self.memory.set("unresolved_errors", "\n".join(error_tables))
                    self._log("warning", f"미해결 오류 {len(unresolved)}개 — Agent가 수동 수정합니다")
                else:
                    self._log("success", "모든 검증 통과!")

                # 미매칭 DSD 테이블 정보 저장
                matched_notes = set((m.dsd_table.note_number, m.dsd_table.table_idx_in_note) for m in matches)
                unmatched_dsd = [t for t in dsd_tables if (t.note_number, t.table_idx_in_note) not in matched_notes]
                if unmatched_dsd:
                    unmatched_lines = [f"주석 {t.note_number}: {t.note_title} (테이블 {t.table_idx_in_note}, {len(t.rows)}행)" for t in unmatched_dsd]
                    self.memory.set("unmatched_dsd_tables", "\n".join(unmatched_lines))
                    self._log("info", f"미매칭 DSD 테이블 {len(unmatched_dsd)}개")
            except Exception as e:
                self._log("warning", f"자동 검증 실패: {e}")

        # System Prompt 구성
        system_prompt = build_system_prompt(self.tools, self.skills_dir)
        initial_instruction = build_initial_instruction(dsd_path, docx_path, output_path)

        self.messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": initial_instruction},
        ]

        # ReAct 루프
        for step in range(self.max_steps):
            self._step = step

            # 컨텍스트 압축
            if self.context_mgr.should_compress(self.messages):
                self._log("info", f"컨텍스트 압축 중 ({len(self.messages)} messages)")
                self.messages = await self.context_mgr.compress(
                    self.messages, self.llm, self.memory
                )
                self._log("info", f"압축 완료 ({len(self.messages)} messages)")

            # LLM 호출
            response_text = await self._call_llm()

            # 응답 파싱
            parsed = self._parse_response(response_text)

            # finish 액션
            if parsed["action"] == "finish":
                # 조기 종료 방지: 최소 10 step 이상 진행해야 finish 허용
                if step < 10:
                    self._log("warning", f"Step {step}에서 조기 finish 시도 — 거부. 더 많은 주석을 처리하세요.")
                    self.messages.append({"role": "assistant", "content": response_text})
                    self.messages.append({
                        "role": "user",
                        "content": "[System] 아직 작업이 충분하지 않습니다. DSD 주석의 테이블 데이터를 DOCX에 반영하세요. batch_set_cells로 숫자 데이터를 입력하세요. finish하지 마세요.",
                    })
                    continue

                # CRITICAL 오류가 남아있으면 finish 거부 (step 50 미만일 때)
                unresolved = self.memory.get("unresolved_errors")
                if unresolved and step < 50:
                    unresolved_count = len(unresolved.strip().split("\n"))
                    self._log("warning", f"CRITICAL 오류 {unresolved_count}개 미해결 — finish 거부")
                    self.messages.append({"role": "assistant", "content": response_text})
                    self.messages.append({
                        "role": "user",
                        "content": f"[System] 아직 {unresolved_count}개 CRITICAL 오류가 남아있습니다. "
                                   f"find_unmatched_tables()로 오류 목록을 확인하고, compare_dsd_docx()로 상세 비교 후, "
                                   f"batch_set_cells로 수정하세요. 모든 CRITICAL 오류를 해결한 후 finish하세요.\n"
                                   f"미해결 오류:\n{unresolved}",
                    })
                    continue

                self._log("success", "작업 완료!")
                await asyncio.to_thread(self.ctx.save_docx, output_path)
                self._log("info", f"결과 저장: {output_path}")
                return parsed.get("action_input", {})

            # _retry 액션 (파싱 실패)
            if parsed["action"] == "_retry":
                self._retry_count += 1
                if self._retry_count > 3:
                    self._log("error", "응답 파싱 3회 연속 실패 — 리셋")
                    self._retry_count = 0
                    self.messages.append({"role": "assistant", "content": response_text})
                    self.messages.append({
                        "role": "user",
                        "content": "[System] 응답 형식이 올바르지 않습니다. 반드시 JSON 형식으로 응답하세요.",
                    })
                    continue

                self.messages.append({"role": "assistant", "content": response_text})
                self.messages.append({
                    "role": "user",
                    "content": "[System] JSON 형식 오류. {\"thought\": \"...\", \"action\": \"...\", \"action_input\": {...}} 형식으로 응답하세요.",
                })
                continue

            self._retry_count = 0

            # Tool 실행
            action = parsed["action"]
            action_input = parsed.get("action_input", {})
            thought = parsed.get("thought", "")

            # 반복 감지: 같은 tool + 같은 인자 3회 이상 → 강제 스킵
            action_key = f"{action}:{json.dumps(action_input, sort_keys=True)}"
            if action_key == self._last_action:
                self._repeat_count += 1
            else:
                self._last_action = action_key
                self._repeat_count = 1

            if self._repeat_count >= 3:
                self._log("warning", f"동일 작업 {self._repeat_count}회 반복 감지 — 스킵하고 다음 작업으로 이동")
                self._repeat_count = 0
                self._last_action = ""
                self.messages.append({"role": "assistant", "content": response_text})
                self.messages.append({
                    "role": "user",
                    "content": f"[System] {action}({json.dumps(action_input, ensure_ascii=False)[:100]})을 이미 여러 번 반복했습니다. 같은 결과가 나올 것입니다. 이 테이블을 건너뛰고 다른 작업을 진행하세요.",
                })
                continue

            self._log("info", f"Step {step}: {thought[:100]}")
            self._log("info", f"도구 실행: {action}({json.dumps(action_input, ensure_ascii=False)[:200]})")

            tool_result = await self.tools.execute(action, action_input)

            # 결과 로그
            level = "warning" if "ERROR" in tool_result else "success"
            self._log(level, f"{action} 결과: {tool_result[:200]}")

            # 대화에 추가
            self.messages.append({"role": "assistant", "content": response_text})
            self.messages.append({
                "role": "user",
                "content": f"[Tool Result]\n{tool_result}",
            })

        # 최대 step 초과
        self._log("error", f"최대 step({self.max_steps}) 초과")
        await asyncio.to_thread(self.ctx.save_docx, output_path)
        return {"error": "Max steps exceeded", "output_path": output_path}

    async def _call_llm(self) -> str:
        """LLM 호출. 대화를 하나의 프롬프트로 포맷팅."""
        system_prompt = self.messages[0]["content"]
        conversation = self._format_conversation()

        response = await self.llm.complete(
            system_prompt=system_prompt,
            user_prompt=conversation,
            temperature=0.1,
            max_tokens=4096,
        )
        return response

    def _format_conversation(self) -> str:
        """메시지 리스트를 하나의 텍스트로 변환."""
        parts = []
        for msg in self.messages[1:]:  # system 제외
            role = msg["role"].upper()
            parts.append(f"[{role}]\n{msg['content']}")
        return "\n\n---\n\n".join(parts)

    def _parse_response(self, text: str) -> dict:
        """LLM 응답에서 action JSON 추출."""
        # 방법 1: 전체가 JSON
        try:
            parsed = json.loads(text.strip())
            if "action" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

        # 방법 2: ```json ... ``` 블록 추출
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                if "action" in parsed:
                    return parsed
            except json.JSONDecodeError:
                pass

        # 방법 3: { ... } 블록 추출 (가장 큰 것)
        brace_matches = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        for match in brace_matches:
            try:
                parsed = json.loads(match)
                if "action" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

        # 파싱 실패
        return {
            "thought": "응답 형식 오류, 재시도 필요",
            "action": "_retry",
            "action_input": {"raw": text[:500]},
        }

    def _log(self, level: str, message: str) -> None:
        """로그 콜백 호출 + 파일 기록."""
        entry = {
            "type": "log",
            "level": level,
            "message": message,
            "step": self._step,
            "timestamp": time.strftime("%H:%M:%S"),
        }
        self.log_callback(entry)
        # 파일 로그
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(f"[{entry['timestamp']}] Step {self._step} [{level}] {message}\n")
        except Exception:
            pass

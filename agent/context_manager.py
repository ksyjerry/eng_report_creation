"""ContextManager — 대화 컨텍스트 압축 관리."""

from __future__ import annotations

import json


class ContextManager:
    """대화 컨텍스트 압축. 메시지가 너무 많아지면 오래된 것을 요약."""

    def __init__(self, max_messages: int = 80, compress_to: int = 20):
        self.max_messages = max_messages
        self.compress_to = compress_to

    def should_compress(self, messages: list[dict]) -> bool:
        """메시지 수가 max_messages를 초과하면 True."""
        # system 메시지 제외
        return len(messages) - 1 > self.max_messages

    async def compress(self, messages: list[dict], llm, working_memory) -> list[dict]:
        """
        오래된 메시지를 LLM에게 요약시켜 압축.

        Returns:
            [system_message, summary_message, ...recent_messages]
        """
        system_msg = messages[0]
        # 최근 compress_to개 보존
        recent = messages[-self.compress_to:]
        # 중간 메시지 (요약 대상)
        to_summarize = messages[1:-self.compress_to]

        if not to_summarize:
            return messages

        # 요약 요청
        conversation_text = self._format_for_summary(to_summarize)
        memory_text = working_memory.to_summary()

        summary_prompt = f"""아래는 AI Agent와 Tool 간의 대화 기록입니다.
이 대화를 요약해주세요. 다음 정보를 반드시 포함하세요:

1. 지금까지 완료된 작업 (어떤 테이블/주석을 처리했는지)
2. 현재 진행 중인 작업
3. 발견된 문제점과 해결 상태
4. 중요한 매핑 정보 (DSD↔DOCX 테이블 매칭 등)
5. 아직 처리하지 않은 항목

현재 Working Memory:
{memory_text}

대화 기록:
{conversation_text}

위 내용을 간결하게 요약하세요 (한국어로):"""

        try:
            summary = await llm.complete(
                system_prompt="대화 기록을 정확하게 요약하는 도우미입니다.",
                user_prompt=summary_prompt,
                temperature=0.1,
                max_tokens=2000,
            )
        except Exception:
            # LLM 실패 시 간단한 통계로 대체
            summary = f"[이전 대화 {len(to_summarize)}개 메시지 — 요약 실패]"

        summary_message = {
            "role": "user",
            "content": f"[이전 대화 요약]\n{summary}",
        }

        return [system_msg, summary_message] + recent

    def _format_for_summary(self, messages: list[dict]) -> str:
        """메시지 리스트를 요약용 텍스트로 변환."""
        parts = []
        for msg in messages:
            role = msg["role"].upper()
            content = msg["content"]
            # 너무 긴 메시지는 앞뒤만
            if len(content) > 500:
                content = content[:250] + "\n...(중략)...\n" + content[-250:]
            parts.append(f"[{role}] {content}")
        return "\n\n".join(parts)

"""Job 생명주기 관리 — Agent 실행, 로그 큐, 상태 추적 + PostgreSQL 영속화."""

from __future__ import annotations

import asyncio
import json
import time
import sys
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.models import JobStatus
from app.services import database as db

# agent 모듈을 import하기 위해 프로젝트 루트를 path에 추가
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


@dataclass
class Job:
    """작업 상태 (인메모리 — SSE 스트리밍용 큐 포함)."""
    id: str
    dsd_path: str
    docx_path: str
    output_path: str
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    current_step: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    result: dict | None = None
    error: str | None = None
    log_queue: asyncio.Queue = field(default_factory=asyncio.Queue)


class JobManager:
    """작업 생명주기 관리 — 인메모리 + DB 이중 저장."""

    def __init__(self):
        self.jobs: dict[str, Job] = {}

    async def create_job(self, dsd_path: str, docx_path: str, output_path: str, *, job_id: str | None = None) -> Job:
        """새 Job 생성 (인메모리 + DB)."""
        job = Job(
            id=job_id or str(uuid4()),
            dsd_path=dsd_path,
            docx_path=docx_path,
            output_path=output_path,
        )
        self.jobs[job.id] = job

        # DB에 저장
        await db.create_job(job.id, dsd_path, docx_path, output_path)

        return job

    def get_job(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    async def get_job_from_db(self, job_id: str) -> dict | None:
        """DB에서 Job 조회 (인메모리에 없을 때 fallback)."""
        return await db.get_job(job_id)

    async def run_job(self, job: Job) -> None:
        """Agent를 실행하고 로그를 job.log_queue에 푸시."""
        job.status = JobStatus.PROCESSING
        await db.update_job_status(job.id, "processing")
        # 이벤트 루프에 양보 — HTTP 응답이 먼저 클라이언트에 전달되도록
        await asyncio.sleep(0)

        # 이벤트 루프 참조 (스레드 안전 콜백용)
        loop = asyncio.get_running_loop()

        # DB 진행률 업데이트 주기 제어
        _last_db_update = [0.0]

        def log_callback(msg: dict):
            """Agent 로그를 큐에 넣기 (스레드 안전)."""
            # 진행률 먼저 계산 & msg에 주입
            step_progress = _estimate_progress(msg)
            if step_progress is not None:
                job.progress = step_progress
                msg["progress"] = step_progress
            if "message" in msg:
                job.current_step = msg["message"][:100]

            # DB 업데이트 (5초 간격, 스레드 안전)
            now = time.time()
            if now - _last_db_update[0] > 5:
                _last_db_update[0] = now
                loop.call_soon_threadsafe(
                    asyncio.ensure_future,
                    db.update_job_progress(job.id, job.progress, job.current_step),
                )

            # 큐에 넣기 (스레드 안전)
            loop.call_soon_threadsafe(job.log_queue.put_nowait, msg)

        try:
            from agent.agent import Agent
            from app.config import settings

            # LLM 클라이언트 생성
            llm = await _create_llm_client(settings)

            agent = Agent(
                llm=llm,
                skills_dir=os.path.abspath(settings.agent_skills_dir),
                max_steps=settings.agent_max_steps,
                log_callback=log_callback,
            )

            result = await agent.run(
                dsd_path=job.dsd_path,
                docx_path=job.docx_path,
                output_path=job.output_path,
            )

            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now()
            job.result = result
            job.progress = 100

            # DB 완료 업데이트
            await db.update_job_status(
                job.id, "completed",
                progress=100,
                result=result,
                completed_at=job.completed_at,
            )

            # 완료 이벤트
            job.log_queue.put_nowait({
                "type": "complete",
                "summary": result,
            })

        except Exception as e:
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now()
            job.error = str(e)

            # DB 실패 업데이트
            await db.update_job_status(
                job.id, "failed",
                error=str(e),
                completed_at=job.completed_at,
            )

            # 실패해도 현재까지의 결과를 저장
            try:
                agent.ctx.save_docx(job.output_path)
                job.log_queue.put_nowait({
                    "type": "log",
                    "level": "warning",
                    "message": f"에러 발생, 중간 결과 저장: {job.output_path}",
                    "step": 0,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                })
            except Exception:
                pass

            job.log_queue.put_nowait({
                "type": "error",
                "message": str(e),
            })

    async def cancel_job(self, job_id: str) -> bool:
        """작업 취소."""
        job = self.jobs.get(job_id)
        if job and job.status == JobStatus.PROCESSING:
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.now()
            await db.update_job_status(
                job_id, "cancelled",
                completed_at=job.completed_at,
            )
            return True
        return False

    async def list_jobs(self, limit: int = 20) -> list[dict]:
        """최근 Job 목록 (DB에서)."""
        return await db.list_jobs(limit)


async def _create_llm_client(settings):
    """GenAI Gateway 클라이언트 생성."""
    try:
        from utils.genai_client import GenAIClient
        return GenAIClient(
            base_url=settings.genai_api_url,
            api_key=settings.genai_api_key,
            model=settings.genai_model,
        )
    except ImportError:
        # genai_client가 없으면 mock 반환
        return _MockLLM()


class _MockLLM:
    """개발/테스트용 Mock LLM."""

    async def complete(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        return json.dumps({
            "thought": "Mock LLM — 실제 GenAI Gateway 연결 필요",
            "action": "finish",
            "action_input": {"summary": "Mock 실행 완료", "stats": {}},
        })


def _estimate_progress(msg: dict) -> int | None:
    """로그 메시지에서 진행률 추정."""
    message = msg.get("message", "").lower()
    if "구조 분석" in message or "로딩" in message:
        return 5
    if "매칭" in message:
        return 15
    if "재무상태표" in message:
        return 25
    if "포괄손익" in message:
        return 35
    if "자본변동" in message:
        return 45
    if "현금흐름" in message:
        return 55
    if "주석" in message:
        return 65
    if "연도 롤링" in message or "year" in message:
        return 80
    if "검증" in message or "validation" in message:
        return 90
    if "완료" in message or "저장" in message:
        return 95
    return None

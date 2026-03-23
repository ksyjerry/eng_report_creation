"""Jobs 라우터 — 파일 업로드, 상태 조회, SSE 스트리밍, 결과 다운로드."""

from __future__ import annotations

import asyncio
import json
import os

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from app.models import JobDetail, JobResponse, JobStatus
from app.services.file_manager import (
    get_output_path,
    save_upload,
    validate_dsd_file,
    validate_docx_file,
)
from app.services.job_manager import JobManager

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# 싱글턴 JobManager
job_manager = JobManager()


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    dsd_file: UploadFile = File(...),
    docx_file: UploadFile = File(...),
):
    """파일 업로드 + 작업 생성 + Agent 비동기 실행."""
    # 파일 검증
    if not validate_dsd_file(dsd_file.filename or ""):
        raise HTTPException(400, "DSD 파일은 .dsd 또는 .zip 확장자만 허용됩니다.")
    if not validate_docx_file(docx_file.filename or ""):
        raise HTTPException(400, "영문 재무제표는 .docx 또는 .pdf 확장자만 허용됩니다.")

    # 파일 저장용 임시 ID
    from uuid import uuid4
    temp_id = str(uuid4())

    # 파일 저장
    try:
        dsd_path = await save_upload(dsd_file, temp_id, "dsd")
        docx_path = await save_upload(docx_file, temp_id, "docx")
    except ValueError as e:
        raise HTTPException(413, str(e))

    output_path = get_output_path(temp_id)

    # Job 생성 (DB + 인메모리) — temp_id를 그대로 사용
    job = await job_manager.create_job(dsd_path, docx_path, output_path, job_id=temp_id)

    # 백그라운드에서 Agent 실행 (이벤트 루프 독립 태스크)
    asyncio.create_task(job_manager.run_job(job))

    return JobResponse(
        job_id=job.id,
        status=job.status,
        created_at=job.created_at,
    )


@router.get("", response_model=list[JobResponse])
async def list_jobs():
    """최근 작업 목록 조회 (DB에서)."""
    rows = await job_manager.list_jobs(limit=20)
    return [
        JobResponse(
            job_id=str(r["id"]),
            status=JobStatus(r["status"]),
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get("/{job_id}", response_model=JobDetail)
async def get_job_status(job_id: str):
    """작업 상태 조회."""
    # 인메모리 우선 (SSE 스트리밍 활성 중)
    job = job_manager.get_job(job_id)
    if job is not None:
        return JobDetail(
            job_id=job.id,
            status=job.status,
            progress=job.progress,
            current_step=job.current_step,
            created_at=job.created_at,
            completed_at=job.completed_at,
            error=job.error,
        )

    # DB fallback (서버 재시작 후)
    row = await job_manager.get_job_from_db(job_id)
    if row is None:
        raise HTTPException(404, "Job not found")

    return JobDetail(
        job_id=row["id"],
        status=JobStatus(row["status"]),
        progress=row["progress"],
        current_step=row["current_step"] or "",
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        error=row["error"],
    )


@router.get("/{job_id}/stream")
async def stream_progress(job_id: str):
    """SSE로 Agent 실행 로그 실시간 스트리밍."""
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")

    async def event_generator():
        while job.status in (JobStatus.QUEUED, JobStatus.PROCESSING):
            try:
                msg = await asyncio.wait_for(job.log_queue.get(), timeout=30)
                yield {
                    "event": "message",
                    "data": json.dumps(msg, ensure_ascii=False, default=str),
                }

                # 완료/에러 이벤트면 종료
                if msg.get("type") in ("complete", "error"):
                    break

            except asyncio.TimeoutError:
                # Keepalive
                yield {"event": "ping", "data": ""}

        # 스트리밍 종료 후 최종 상태
        if job.status == JobStatus.COMPLETED:
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "complete",
                    "summary": job.result or {},
                }, ensure_ascii=False, default=str),
            }
        elif job.status == JobStatus.FAILED:
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "error",
                    "message": job.error or "Unknown error",
                }, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


@router.get("/{job_id}/download")
async def download_result(job_id: str):
    """완료된 작업의 결과 DOCX 다운로드."""
    # 인메모리 또는 DB에서 조회
    job = job_manager.get_job(job_id)
    if job is not None:
        status = job.status
        output_path = job.output_path
    else:
        row = await job_manager.get_job_from_db(job_id)
        if row is None:
            raise HTTPException(404, "Job not found")
        status = JobStatus(row["status"])
        output_path = row["output_path"]

    if status != JobStatus.COMPLETED:
        raise HTTPException(409, f"Job is not completed (status: {status.value})")

    if not os.path.exists(output_path):
        raise HTTPException(404, "Output file not found")

    filename = os.path.basename(output_path)
    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )


@router.delete("/{job_id}")
async def cancel_job(job_id: str):
    """작업 취소."""
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")

    if await job_manager.cancel_job(job_id):
        return {"status": "cancelled"}
    else:
        raise HTTPException(409, f"Cannot cancel job (status: {job.status.value})")

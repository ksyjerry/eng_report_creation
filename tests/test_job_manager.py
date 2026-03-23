"""job_manager 단위 테스트 — DB 의존성 mock."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.models import JobStatus
from app.services.job_manager import Job, JobManager, _estimate_progress


# ==================================================================
# _estimate_progress 테스트
# ==================================================================

class TestEstimateProgress:

    def test_structure_analysis(self):
        assert _estimate_progress({"message": "DSD 구조 분석 중"}) == 5
        assert _estimate_progress({"message": "파일 로딩 완료"}) == 5

    def test_matching(self):
        assert _estimate_progress({"message": "테이블 매칭 시작"}) == 15

    def test_bs(self):
        assert _estimate_progress({"message": "재무상태표 처리"}) == 25

    def test_is(self):
        assert _estimate_progress({"message": "포괄손익계산서 처리"}) == 35

    def test_ce(self):
        assert _estimate_progress({"message": "자본변동표 처리"}) == 45

    def test_cf(self):
        assert _estimate_progress({"message": "현금흐름표 처리"}) == 55

    def test_notes(self):
        assert _estimate_progress({"message": "주석 처리 중"}) == 65

    def test_year_rolling(self):
        assert _estimate_progress({"message": "연도 롤링 시작"}) == 80

    def test_validation(self):
        assert _estimate_progress({"message": "validation 검증"}) == 90

    def test_completion(self):
        assert _estimate_progress({"message": "결과 저장 완료"}) == 95

    def test_unknown_message(self):
        assert _estimate_progress({"message": "some random message"}) is None

    def test_empty_message(self):
        assert _estimate_progress({}) is None


# ==================================================================
# Job 데이터클래스 테스트
# ==================================================================

class TestJob:

    def test_default_values(self):
        job = Job(
            id="test-id",
            dsd_path="/tmp/dsd",
            docx_path="/tmp/docx",
            output_path="/tmp/out",
        )
        assert job.status == JobStatus.QUEUED
        assert job.progress == 0
        assert job.current_step == ""
        assert job.completed_at is None
        assert job.result is None
        assert job.error is None
        assert isinstance(job.log_queue, asyncio.Queue)

    def test_custom_status(self):
        job = Job(
            id="test-id",
            dsd_path="/tmp/dsd",
            docx_path="/tmp/docx",
            output_path="/tmp/out",
            status=JobStatus.PROCESSING,
            progress=50,
        )
        assert job.status == JobStatus.PROCESSING
        assert job.progress == 50


# ==================================================================
# JobManager 테스트 (DB mock)
# ==================================================================

class TestJobManager:

    @patch("app.services.job_manager.db")
    async def test_create_job(self, mock_db):
        mock_db.create_job = AsyncMock(return_value={"id": "test", "status": "queued"})

        mgr = JobManager()
        job = await mgr.create_job("/tmp/dsd", "/tmp/docx", "/tmp/out")

        assert job.dsd_path == "/tmp/dsd"
        assert job.docx_path == "/tmp/docx"
        assert job.output_path == "/tmp/out"
        assert job.status == JobStatus.QUEUED
        assert job.id in mgr.jobs
        mock_db.create_job.assert_called_once()

    @patch("app.services.job_manager.db")
    async def test_create_job_with_id(self, mock_db):
        mock_db.create_job = AsyncMock(return_value={})

        mgr = JobManager()
        job = await mgr.create_job("/tmp/dsd", "/tmp/docx", "/tmp/out", job_id="custom-id")

        assert job.id == "custom-id"
        assert "custom-id" in mgr.jobs

    def test_get_job_exists(self):
        mgr = JobManager()
        job = Job(id="abc", dsd_path="", docx_path="", output_path="")
        mgr.jobs["abc"] = job

        assert mgr.get_job("abc") is job

    def test_get_job_not_found(self):
        mgr = JobManager()
        assert mgr.get_job("nonexistent") is None

    @patch("app.services.job_manager.db")
    async def test_get_job_from_db(self, mock_db):
        mock_db.get_job = AsyncMock(return_value={"id": "db-job", "status": "completed"})

        mgr = JobManager()
        result = await mgr.get_job_from_db("db-job")

        assert result["id"] == "db-job"
        mock_db.get_job.assert_called_once_with("db-job")

    @patch("app.services.job_manager.db")
    async def test_cancel_processing_job(self, mock_db):
        mock_db.update_job_status = AsyncMock()

        mgr = JobManager()
        job = Job(id="cancel-me", dsd_path="", docx_path="", output_path="",
                  status=JobStatus.PROCESSING)
        mgr.jobs["cancel-me"] = job

        result = await mgr.cancel_job("cancel-me")

        assert result is True
        assert job.status == JobStatus.CANCELLED
        assert job.completed_at is not None
        mock_db.update_job_status.assert_called_once()

    @patch("app.services.job_manager.db")
    async def test_cancel_completed_job_fails(self, mock_db):
        mgr = JobManager()
        job = Job(id="done", dsd_path="", docx_path="", output_path="",
                  status=JobStatus.COMPLETED)
        mgr.jobs["done"] = job

        result = await mgr.cancel_job("done")

        assert result is False

    @patch("app.services.job_manager.db")
    async def test_cancel_nonexistent_job(self, mock_db):
        mgr = JobManager()
        result = await mgr.cancel_job("nope")
        assert result is False

    @patch("app.services.job_manager.db")
    async def test_list_jobs(self, mock_db):
        mock_db.list_jobs = AsyncMock(return_value=[
            {"id": "j1", "status": "queued", "created_at": datetime.now()},
            {"id": "j2", "status": "completed", "created_at": datetime.now()},
        ])

        mgr = JobManager()
        jobs = await mgr.list_jobs(limit=10)

        assert len(jobs) == 2
        mock_db.list_jobs.assert_called_once_with(10)

    @patch("app.services.job_manager.db")
    async def test_run_job_success(self, mock_db):
        """Agent mock으로 run_job 성공 흐름 테스트."""
        mock_db.update_job_status = AsyncMock()
        mock_db.update_job_progress = AsyncMock()

        job = Job(id="run-test", dsd_path="/tmp/dsd", docx_path="/tmp/docx",
                  output_path="/tmp/out")

        mgr = JobManager()
        mgr.jobs["run-test"] = job

        mock_agent_instance = MagicMock()
        mock_agent_instance.run = AsyncMock(return_value={"summary": "done", "stats": {}})
        mock_agent_instance.ctx = MagicMock()

        # Agent는 run_job 내부에서 local import되므로 agent.agent 모듈을 직접 patch
        with patch.dict("sys.modules", {"agent.agent": MagicMock(Agent=MagicMock(return_value=mock_agent_instance))}), \
             patch("app.services.job_manager._create_llm_client", new_callable=AsyncMock):

            await mgr.run_job(job)

        assert job.status == JobStatus.COMPLETED
        assert job.progress == 100
        assert job.result == {"summary": "done", "stats": {}}
        assert job.completed_at is not None

    @patch("app.services.job_manager.db")
    async def test_run_job_failure(self, mock_db):
        """Agent 실행 실패 시 상태 전이 테스트."""
        mock_db.update_job_status = AsyncMock()

        job = Job(id="fail-test", dsd_path="/tmp/dsd", docx_path="/tmp/docx",
                  output_path="/tmp/out")

        mgr = JobManager()

        # _create_llm_client에서 에러 발생시키면 Agent import 전에 실패
        with patch("app.services.job_manager._create_llm_client",
                   new_callable=AsyncMock, side_effect=RuntimeError("Agent crashed")):

            await mgr.run_job(job)

        assert job.status == JobStatus.FAILED
        assert "Agent crashed" in job.error
        assert job.completed_at is not None

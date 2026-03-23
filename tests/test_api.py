"""FastAPI 엔드포인트 통합 테스트 — DB mock, Agent mock."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from io import BytesIO
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.models import JobStatus


# ==================================================================
# FastAPI TestClient 픽스처
# ==================================================================

@pytest.fixture
def mock_db():
    """DB 모듈 전체를 mock."""
    with patch("app.services.database.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("app.services.database.close_pool", new_callable=AsyncMock), \
         patch("app.services.database.recover_stale_jobs", new_callable=AsyncMock, return_value=0), \
         patch("app.services.database.create_job", new_callable=AsyncMock) as mock_create, \
         patch("app.services.database.update_job_status", new_callable=AsyncMock), \
         patch("app.services.database.update_job_progress", new_callable=AsyncMock), \
         patch("app.services.database.get_job", new_callable=AsyncMock) as mock_get, \
         patch("app.services.database.list_jobs", new_callable=AsyncMock) as mock_list:

        mock_create.return_value = {"id": "test-id", "status": "queued"}
        mock_get.return_value = None
        mock_list.return_value = []

        yield {
            "get_pool": mock_get_pool,
            "create_job": mock_create,
            "get_job": mock_get,
            "list_jobs": mock_list,
        }


@pytest.fixture
def client(mock_db, tmp_dirs):
    """DB mock + 임시 디렉토리 설정된 TestClient."""
    with patch("app.config.settings") as mock_settings:
        mock_settings.upload_dir = tmp_dirs["upload_dir"]
        mock_settings.output_dir = tmp_dirs["output_dir"]
        mock_settings.max_file_size_mb = 50
        mock_settings.cors_origins = ["http://localhost:3000"]
        mock_settings.host = "0.0.0.0"
        mock_settings.port = 8000
        mock_settings.debug = False
        mock_settings.database_url = "postgresql://test:test@localhost/test"
        mock_settings.agent_skills_dir = "./agent_skills"
        mock_settings.agent_max_steps = 200
        mock_settings.genai_api_url = ""
        mock_settings.genai_api_key = ""
        mock_settings.genai_model = "test"
        mock_settings.job_retention_hours = 24

        from app.main import app
        with TestClient(app) as c:
            yield c


# ==================================================================
# Health Check
# ==================================================================

class TestHealthCheck:

    def test_health_returns_200(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data


# ==================================================================
# POST /api/jobs (파일 업로드 + Job 생성)
# ==================================================================

class TestCreateJob:

    def test_valid_upload(self, client):
        """DSD + DOCX 업로드 성공."""
        with patch("app.routers.jobs.job_manager") as mock_mgr:
            from app.services.job_manager import Job
            mock_job = Job(
                id="new-job-id",
                dsd_path="/tmp/dsd",
                docx_path="/tmp/docx",
                output_path="/tmp/out",
            )
            mock_mgr.create_job = AsyncMock(return_value=mock_job)
            mock_mgr.run_job = AsyncMock()

            resp = client.post(
                "/api/jobs",
                files={
                    "dsd_file": ("test.dsd", b"dsd content", "application/octet-stream"),
                    "docx_file": ("test.docx", b"docx content", "application/octet-stream"),
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "queued"

    def test_invalid_dsd_extension(self, client):
        """잘못된 DSD 확장자 → 400."""
        resp = client.post(
            "/api/jobs",
            files={
                "dsd_file": ("test.txt", b"content", "text/plain"),
                "docx_file": ("test.docx", b"content", "application/octet-stream"),
            },
        )
        assert resp.status_code == 400

    def test_invalid_docx_extension(self, client):
        """잘못된 DOCX 확장자 → 400."""
        resp = client.post(
            "/api/jobs",
            files={
                "dsd_file": ("test.dsd", b"content", "application/octet-stream"),
                "docx_file": ("test.txt", b"content", "text/plain"),
            },
        )
        assert resp.status_code == 400

    def test_missing_files(self, client):
        """파일 누락 → 422."""
        resp = client.post("/api/jobs")
        assert resp.status_code == 422


# ==================================================================
# GET /api/jobs (목록 조회)
# ==================================================================

class TestListJobs:

    def test_list_empty(self, client, mock_db):
        mock_db["list_jobs"].return_value = []

        with patch("app.routers.jobs.job_manager") as mock_mgr:
            mock_mgr.list_jobs = AsyncMock(return_value=[])
            resp = client.get("/api/jobs")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_jobs(self, client, mock_db):
        now = datetime.now()
        with patch("app.routers.jobs.job_manager") as mock_mgr:
            mock_mgr.list_jobs = AsyncMock(return_value=[
                {"id": "j1", "status": "completed", "created_at": now},
                {"id": "j2", "status": "processing", "created_at": now},
            ])
            resp = client.get("/api/jobs")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["job_id"] == "j1"
        assert data[1]["status"] == "processing"


# ==================================================================
# GET /api/jobs/{job_id} (상태 조회)
# ==================================================================

class TestGetJobStatus:

    def test_in_memory_job(self, client):
        """인메모리에 있는 job 조회."""
        from app.services.job_manager import Job
        job = Job(
            id="mem-job",
            dsd_path="/tmp/dsd",
            docx_path="/tmp/docx",
            output_path="/tmp/out",
            status=JobStatus.PROCESSING,
            progress=42,
            current_step="매칭 중",
        )

        with patch("app.routers.jobs.job_manager") as mock_mgr:
            mock_mgr.get_job.return_value = job
            resp = client.get("/api/jobs/mem-job")

        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "mem-job"
        assert data["status"] == "processing"
        assert data["progress"] == 42

    def test_db_fallback(self, client, mock_db):
        """인메모리에 없으면 DB fallback."""
        now = datetime.now()
        with patch("app.routers.jobs.job_manager") as mock_mgr:
            mock_mgr.get_job.return_value = None
            mock_mgr.get_job_from_db = AsyncMock(return_value={
                "id": "db-job",
                "status": "completed",
                "progress": 100,
                "current_step": "완료",
                "created_at": now,
                "completed_at": now,
                "error": None,
            })
            resp = client.get("/api/jobs/db-job")

        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "db-job"
        assert data["status"] == "completed"

    def test_job_not_found(self, client, mock_db):
        """인메모리도 DB도 없으면 404."""
        with patch("app.routers.jobs.job_manager") as mock_mgr:
            mock_mgr.get_job.return_value = None
            mock_mgr.get_job_from_db = AsyncMock(return_value=None)
            resp = client.get("/api/jobs/nonexistent")

        assert resp.status_code == 404


# ==================================================================
# GET /api/jobs/{job_id}/download
# ==================================================================

class TestDownload:

    def test_download_completed_job(self, client, tmp_dirs):
        """완료된 job의 결과 파일 다운로드."""
        # 임시 결과 파일 생성
        output_path = os.path.join(tmp_dirs["output_dir"], "test-job", "SARA_result.docx")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(b"PK\x03\x04" + b"\x00" * 100)  # 가짜 DOCX

        from app.services.job_manager import Job
        job = Job(
            id="dl-job",
            dsd_path="/tmp/dsd",
            docx_path="/tmp/docx",
            output_path=output_path,
            status=JobStatus.COMPLETED,
        )

        with patch("app.routers.jobs.job_manager") as mock_mgr:
            mock_mgr.get_job.return_value = job
            resp = client.get("/api/jobs/dl-job/download")

        assert resp.status_code == 200
        assert "SARA_result.docx" in resp.headers.get("content-disposition", "")

    def test_download_not_completed(self, client):
        """미완료 job 다운로드 시도 → 409."""
        from app.services.job_manager import Job
        job = Job(
            id="incomplete",
            dsd_path="/tmp/dsd",
            docx_path="/tmp/docx",
            output_path="/tmp/out",
            status=JobStatus.PROCESSING,
        )

        with patch("app.routers.jobs.job_manager") as mock_mgr:
            mock_mgr.get_job.return_value = job
            resp = client.get("/api/jobs/incomplete/download")

        assert resp.status_code == 409

    def test_download_db_fallback_not_found(self, client, mock_db):
        """DB fallback에서도 못 찾으면 404."""
        with patch("app.routers.jobs.job_manager") as mock_mgr:
            mock_mgr.get_job.return_value = None
            mock_mgr.get_job_from_db = AsyncMock(return_value=None)
            resp = client.get("/api/jobs/ghost/download")

        assert resp.status_code == 404


# ==================================================================
# DELETE /api/jobs/{job_id} (취소)
# ==================================================================

class TestCancelJob:

    def test_cancel_processing_job(self, client):
        from app.services.job_manager import Job
        job = Job(
            id="cancel-me",
            dsd_path="/tmp/dsd",
            docx_path="/tmp/docx",
            output_path="/tmp/out",
            status=JobStatus.PROCESSING,
        )

        with patch("app.routers.jobs.job_manager") as mock_mgr:
            mock_mgr.get_job.return_value = job
            mock_mgr.cancel_job = AsyncMock(return_value=True)
            resp = client.delete("/api/jobs/cancel-me")

        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_cancel_completed_job_fails(self, client):
        from app.services.job_manager import Job
        job = Job(
            id="done",
            dsd_path="/tmp/dsd",
            docx_path="/tmp/docx",
            output_path="/tmp/out",
            status=JobStatus.COMPLETED,
        )

        with patch("app.routers.jobs.job_manager") as mock_mgr:
            mock_mgr.get_job.return_value = job
            mock_mgr.cancel_job = AsyncMock(return_value=False)
            resp = client.delete("/api/jobs/done")

        assert resp.status_code == 409

    def test_cancel_not_found(self, client):
        with patch("app.routers.jobs.job_manager") as mock_mgr:
            mock_mgr.get_job.return_value = None
            resp = client.delete("/api/jobs/nope")

        assert resp.status_code == 404

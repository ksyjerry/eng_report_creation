"""공통 테스트 픽스처."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from unittest.mock import AsyncMock, patch

# backend/ 디렉토리를 sys.path에 추가 → `from app.xxx` import가 동작하도록
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_dirs(tmp_path):
    """임시 upload/output 디렉토리."""
    upload_dir = tmp_path / "uploads"
    output_dir = tmp_path / "outputs"
    upload_dir.mkdir()
    output_dir.mkdir()
    return {"upload_dir": str(upload_dir), "output_dir": str(output_dir)}


@pytest.fixture
def mock_settings(tmp_dirs):
    """DB 없이 테스트할 수 있는 설정 패치."""
    with patch("app.config.settings") as mock:
        mock.upload_dir = tmp_dirs["upload_dir"]
        mock.output_dir = tmp_dirs["output_dir"]
        mock.max_file_size_mb = 50
        mock.cors_origins = ["http://localhost:3000"]
        mock.host = "0.0.0.0"
        mock.port = 8000
        mock.debug = False
        mock.agent_skills_dir = "./agent_skills"
        mock.agent_max_steps = 200
        mock.database_url = "postgresql://test:test@localhost:5432/test"
        mock.genai_api_url = ""
        mock.genai_api_key = ""
        mock.genai_model = "test-model"
        mock.job_retention_hours = 24
        yield mock


@pytest.fixture
def sample_dsd_path():
    """테스트용 DSD 파일 경로."""
    path = "/Users/jkim564/Documents/ai/eng_fs_creation/files/SBL_2024_별도감사보고서.dsd"
    if not os.path.exists(path):
        pytest.skip("SBL DSD file not found")
    return path


@pytest.fixture
def sample_docx_path():
    """테스트용 DOCX 파일 경로."""
    path = "/Users/jkim564/Documents/ai/eng_fs_creation/files/SBL_2023_English report_vF.docx"
    if not os.path.exists(path):
        pytest.skip("SBL DOCX file not found")
    return path

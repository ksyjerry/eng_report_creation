"""file_manager 단위 테스트."""

from __future__ import annotations

import os
from io import BytesIO
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.file_manager import (
    save_upload,
    get_output_path,
    validate_dsd_file,
    validate_docx_file,
    cleanup_job_files,
)


# ==================================================================
# validate 함수 테스트
# ==================================================================

class TestValidation:

    def test_valid_dsd_extensions(self):
        assert validate_dsd_file("report.dsd") is True
        assert validate_dsd_file("report.zip") is True

    def test_invalid_dsd_extensions(self):
        assert validate_dsd_file("report.docx") is False
        assert validate_dsd_file("report.pdf") is False
        assert validate_dsd_file("report.txt") is False
        assert validate_dsd_file("") is False

    def test_valid_docx_extensions(self):
        assert validate_docx_file("report.docx") is True
        assert validate_docx_file("report.pdf") is True

    def test_invalid_docx_extensions(self):
        assert validate_docx_file("report.dsd") is False
        assert validate_docx_file("report.txt") is False
        assert validate_docx_file("report.zip") is False
        assert validate_docx_file("") is False

    def test_case_insensitive(self):
        assert validate_dsd_file("REPORT.DSD") is True
        assert validate_docx_file("REPORT.DOCX") is True


# ==================================================================
# save_upload 테스트
# ==================================================================

class TestSaveUpload:

    async def test_save_dsd_file(self, tmp_dirs):
        with patch("app.services.file_manager.settings") as mock_settings:
            mock_settings.upload_dir = tmp_dirs["upload_dir"]
            mock_settings.max_file_size_mb = 50

            mock_file = AsyncMock()
            mock_file.filename = "test_report.dsd"
            mock_file.read = AsyncMock(return_value=b"fake dsd content")

            path = await save_upload(mock_file, "job-123", "dsd")

            assert path.endswith("dsd.dsd")
            assert os.path.exists(path)
            with open(path, "rb") as f:
                assert f.read() == b"fake dsd content"

    async def test_save_docx_file(self, tmp_dirs):
        with patch("app.services.file_manager.settings") as mock_settings:
            mock_settings.upload_dir = tmp_dirs["upload_dir"]
            mock_settings.max_file_size_mb = 50

            mock_file = AsyncMock()
            mock_file.filename = "english_report.docx"
            mock_file.read = AsyncMock(return_value=b"fake docx content")

            path = await save_upload(mock_file, "job-456", "docx")

            assert path.endswith("docx.docx")
            assert os.path.exists(path)

    async def test_file_too_large(self, tmp_dirs):
        with patch("app.services.file_manager.settings") as mock_settings:
            mock_settings.upload_dir = tmp_dirs["upload_dir"]
            mock_settings.max_file_size_mb = 1  # 1MB 제한

            large_content = b"x" * (2 * 1024 * 1024)  # 2MB
            mock_file = AsyncMock()
            mock_file.filename = "big.dsd"
            mock_file.read = AsyncMock(return_value=large_content)

            with pytest.raises(ValueError, match="too large"):
                await save_upload(mock_file, "job-big", "dsd")


# ==================================================================
# get_output_path 테스트
# ==================================================================

class TestGetOutputPath:

    def test_creates_directory(self, tmp_dirs):
        with patch("app.services.file_manager.settings") as mock_settings:
            mock_settings.output_dir = tmp_dirs["output_dir"]

            path = get_output_path("job-out-1")
            assert "SARA_result.docx" in path
            assert os.path.isdir(os.path.dirname(path))

    def test_custom_company_name(self, tmp_dirs):
        with patch("app.services.file_manager.settings") as mock_settings:
            mock_settings.output_dir = tmp_dirs["output_dir"]

            path = get_output_path("job-out-2", company_name="SBL")
            assert "SARA_SBL.docx" in path


# ==================================================================
# cleanup_job_files 테스트
# ==================================================================

class TestCleanup:

    def test_cleanup_removes_directories(self, tmp_dirs):
        with patch("app.services.file_manager.settings") as mock_settings:
            mock_settings.upload_dir = tmp_dirs["upload_dir"]
            mock_settings.output_dir = tmp_dirs["output_dir"]

            # 디렉토리 생성
            job_id = "cleanup-test"
            os.makedirs(os.path.join(tmp_dirs["upload_dir"], job_id))
            os.makedirs(os.path.join(tmp_dirs["output_dir"], job_id))

            cleanup_job_files(job_id)

            assert not os.path.exists(os.path.join(tmp_dirs["upload_dir"], job_id))
            assert not os.path.exists(os.path.join(tmp_dirs["output_dir"], job_id))

    def test_cleanup_nonexistent_job(self, tmp_dirs):
        with patch("app.services.file_manager.settings") as mock_settings:
            mock_settings.upload_dir = tmp_dirs["upload_dir"]
            mock_settings.output_dir = tmp_dirs["output_dir"]

            # 에러 없이 실행
            cleanup_job_files("nonexistent-job")

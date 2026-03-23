"""파일 업로드/저장/정리 서비스."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import settings


ALLOWED_DSD_EXTENSIONS = {".dsd", ".zip"}
ALLOWED_DOCX_EXTENSIONS = {".docx", ".pdf"}


async def save_upload(file: UploadFile, job_id: str, file_type: str) -> str:
    """업로드 파일을 저장하고 경로 반환."""
    job_dir = os.path.join(settings.upload_dir, job_id)
    os.makedirs(job_dir, exist_ok=True)

    ext = Path(file.filename or "").suffix.lower()
    safe_name = f"{file_type}{ext}"
    file_path = os.path.join(job_dir, safe_name)

    content = await file.read()

    # 파일 크기 체크
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_file_size_mb:
        raise ValueError(f"File too large: {size_mb:.1f}MB (max {settings.max_file_size_mb}MB)")

    with open(file_path, "wb") as f:
        f.write(content)

    return file_path


def get_output_path(job_id: str, company_name: str = "result") -> str:
    """출력 파일 경로 생성."""
    output_dir = os.path.join(settings.output_dir, job_id)
    os.makedirs(output_dir, exist_ok=True)
    return os.path.join(output_dir, f"SARA_{company_name}.docx")


def validate_dsd_file(filename: str) -> bool:
    """DSD 파일 확장자 검증."""
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_DSD_EXTENSIONS


def validate_docx_file(filename: str) -> bool:
    """DOCX 파일 확장자 검증."""
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_DOCX_EXTENSIONS


def cleanup_job_files(job_id: str) -> None:
    """작업 파일 정리."""
    for base_dir in [settings.upload_dir, settings.output_dir]:
        job_dir = os.path.join(base_dir, job_id)
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir, ignore_errors=True)

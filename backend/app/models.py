"""Pydantic 모델 — Request/Response 스키마."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime


class JobDetail(BaseModel):
    job_id: str
    status: JobStatus
    progress: int = 0
    current_step: str = ""
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


class LogEntry(BaseModel):
    type: str = "log"
    level: str = "info"
    message: str
    step: int = 0
    timestamp: str = ""
    detail: str | None = None


class ProgressEvent(BaseModel):
    type: str = "progress"
    progress: int = 0
    step: str = ""


class CompleteEvent(BaseModel):
    type: str = "complete"
    summary: dict[str, Any] = {}


class ErrorEvent(BaseModel):
    type: str = "error"
    message: str = ""

"""PostgreSQL 데이터베이스 연결 및 Job CRUD."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.config import settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """커넥션 풀 가져오기 (lazy init)."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=2,
            max_size=10,
        )
    return _pool


async def close_pool() -> None:
    """커넥션 풀 닫기."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# ---------------------------------------------------------------------------
# Job CRUD
# ---------------------------------------------------------------------------

async def create_job(
    job_id: str,
    dsd_path: str,
    docx_path: str,
    output_path: str,
) -> dict:
    """새 Job 레코드 생성."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO jobs (id, dsd_path, docx_path, output_path)
        VALUES ($1, $2, $3, $4)
        RETURNING id, status, progress, current_step, created_at
        """,
        UUID(job_id), dsd_path, docx_path, output_path,
    )
    return dict(row)


async def update_job_status(
    job_id: str,
    status: str,
    progress: int | None = None,
    current_step: str | None = None,
    result: dict | None = None,
    error: str | None = None,
    completed_at: datetime | None = None,
) -> None:
    """Job 상태 업데이트."""
    pool = await get_pool()

    sets = ["status = $2"]
    vals: list[Any] = [UUID(job_id), status]
    idx = 3

    if progress is not None:
        sets.append(f"progress = ${idx}")
        vals.append(progress)
        idx += 1
    if current_step is not None:
        sets.append(f"current_step = ${idx}")
        vals.append(current_step[:200])
        idx += 1
    if result is not None:
        sets.append(f"result = ${idx}")
        vals.append(json.dumps(result, ensure_ascii=False, default=str))
        idx += 1
    if error is not None:
        sets.append(f"error = ${idx}")
        vals.append(error)
        idx += 1
    if completed_at is not None:
        sets.append(f"completed_at = ${idx}")
        vals.append(completed_at)
        idx += 1

    query = f"UPDATE jobs SET {', '.join(sets)} WHERE id = $1"
    await pool.execute(query, *vals)


async def update_job_progress(
    job_id: str,
    progress: int,
    current_step: str = "",
) -> None:
    """진행률만 빠르게 업데이트."""
    pool = await get_pool()
    await pool.execute(
        "UPDATE jobs SET progress = $2, current_step = $3 WHERE id = $1",
        UUID(job_id), progress, current_step[:200],
    )


async def get_job(job_id: str) -> dict | None:
    """Job 조회."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM jobs WHERE id = $1",
        UUID(job_id),
    )
    if row is None:
        return None
    d = dict(row)
    d["id"] = str(d["id"])
    return d


async def list_jobs(limit: int = 20) -> list[dict]:
    """최근 Job 목록."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT id, status, progress, current_step, created_at, completed_at "
        "FROM jobs ORDER BY created_at DESC LIMIT $1",
        limit,
    )
    return [dict(r) | {"id": str(r["id"])} for r in rows]


async def recover_stale_jobs() -> int:
    """서버 재시작 시 processing/queued 상태의 Job을 failed로 전환."""
    pool = await get_pool()
    result = await pool.execute(
        "UPDATE jobs SET status = 'failed', error = 'Server restarted during processing', "
        "completed_at = NOW() WHERE status IN ('processing', 'queued')",
    )
    return int(result.split()[-1]) if result else 0


async def delete_old_jobs(retention_hours: int = 24) -> int:
    """오래된 Job 삭제."""
    pool = await get_pool()
    result = await pool.execute(
        "DELETE FROM jobs WHERE created_at < NOW() - INTERVAL '1 hour' * $1",
        retention_hours,
    )
    # result is like "DELETE 5"
    return int(result.split()[-1]) if result else 0

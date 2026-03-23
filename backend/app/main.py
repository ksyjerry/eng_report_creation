"""SARA Backend — FastAPI 서버."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import jobs
from app.services import database as db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작/종료 시 DB 풀 관리 + 미완료 Job 복구."""
    await db.get_pool()  # 시작 시 풀 초기화
    recovered = await db.recover_stale_jobs()
    if recovered:
        import logging
        logging.getLogger(__name__).warning("Recovered %d stale jobs on startup", recovered)
    yield
    await db.close_pool()  # 종료 시 풀 닫기


app = FastAPI(
    title="SARA API",
    description="영문보고서 Agent — AI Agent Backend",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(jobs.router)


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )

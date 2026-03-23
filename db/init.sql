-- SARA DB 초기화
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS jobs (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    status      VARCHAR(20) NOT NULL DEFAULT 'queued',
    progress    INTEGER NOT NULL DEFAULT 0,
    current_step VARCHAR(200) DEFAULT '',
    dsd_path    TEXT NOT NULL,
    docx_path   TEXT NOT NULL,
    output_path TEXT NOT NULL,
    result      JSONB,
    error       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);

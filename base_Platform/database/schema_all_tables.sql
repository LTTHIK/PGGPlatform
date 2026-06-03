BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- -----------------------------------------------------------------------------
-- 枚举类型
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'recording_source') THEN
        CREATE TYPE recording_source AS ENUM ('live', 'offline_import');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'session_status') THEN
        CREATE TYPE session_status AS ENUM ('recording', 'stopped', 'uploaded', 'partial_failed', 'completed');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'artifact_type') THEN
        CREATE TYPE artifact_type AS ENUM ('recording_wav', 'raw_transcript', 'formal_text', 'meeting_minutes');
    END IF;
END$$;

-- -----------------------------------------------------------------------------
-- 通用更新时间触发器函数
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------------------------
-- 1) 旧索引表（兼容历史逻辑）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS file_records (
    id           BIGSERIAL PRIMARY KEY,
    session_id   TEXT,
    bucket_name  TEXT NOT NULL,
    object_key   TEXT NOT NULL,
    kind         TEXT NOT NULL,
    content_type TEXT,
    byte_length  BIGINT,
    local_path   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (bucket_name, object_key)
);

CREATE INDEX IF NOT EXISTS idx_file_records_session ON file_records(session_id);
CREATE INDEX IF NOT EXISTS idx_file_records_kind ON file_records(kind);
CREATE INDEX IF NOT EXISTS idx_file_records_created ON file_records(created_at DESC);

DROP TRIGGER IF EXISTS trg_file_records_updated ON file_records;
CREATE TRIGGER trg_file_records_updated
    BEFORE UPDATE ON file_records
    FOR EACH ROW EXECUTE PROCEDURE set_updated_at();

-- -----------------------------------------------------------------------------
-- 2) 会话主表（一次录音一条）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recording_sessions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_code TEXT NOT NULL UNIQUE,
    bucket_name  TEXT NOT NULL,
    source       recording_source NOT NULL DEFAULT 'live',
    status       session_status NOT NULL DEFAULT 'recording',
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at     TIMESTAMPTZ,
    note         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recording_sessions_bucket_created
    ON recording_sessions(bucket_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recording_sessions_status_created
    ON recording_sessions(status, created_at DESC);

DROP TRIGGER IF EXISTS trg_recording_sessions_updated ON recording_sessions;
CREATE TRIGGER trg_recording_sessions_updated
    BEFORE UPDATE ON recording_sessions
    FOR EACH ROW EXECUTE PROCEDURE set_updated_at();

-- -----------------------------------------------------------------------------
-- 3) 会话文件明细（四类文件）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS session_artifacts (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    UUID NOT NULL REFERENCES recording_sessions(id) ON DELETE CASCADE,
    artifact_type artifact_type NOT NULL,
    bucket_name   TEXT NOT NULL,
    object_key    TEXT NOT NULL,
    content_type  TEXT,
    byte_length   BIGINT CHECK (byte_length IS NULL OR byte_length >= 0),
    file_ext      TEXT,
    sha256        TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_session_artifacts_object UNIQUE (bucket_name, object_key)
);

CREATE INDEX IF NOT EXISTS idx_session_artifacts_session_type_created
    ON session_artifacts(session_id, artifact_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_artifacts_bucket_created
    ON session_artifacts(bucket_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_artifacts_sha256
    ON session_artifacts(sha256);

-- -----------------------------------------------------------------------------
-- 4) 会话事件审计
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS session_events (
    id            BIGSERIAL PRIMARY KEY,
    session_id    UUID REFERENCES recording_sessions(id) ON DELETE CASCADE,
    event_type    TEXT NOT NULL,
    event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_session_events_session_created
    ON session_events(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_events_type_created
    ON session_events(event_type, created_at DESC);

-- -----------------------------------------------------------------------------
-- 5) 用户（登录与权限）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id             BIGSERIAL PRIMARY KEY,
    username       TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    is_active      BOOLEAN NOT NULL DEFAULT true,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at DESC);

DROP TRIGGER IF EXISTS trg_users_updated ON users;
CREATE TRIGGER trg_users_updated
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE PROCEDURE set_updated_at();

COMMIT;

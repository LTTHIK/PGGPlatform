BEGIN;

-- 1) 将历史 file_records 聚合为会话主记录
WITH normalized AS (
    SELECT
        fr.*,
        COALESCE(NULLIF(fr.session_id, ''), 'legacy-bucket:' || fr.bucket_name) AS session_code_norm
    FROM file_records fr
),
session_agg AS (
    SELECT
        session_code_norm,
        MIN(bucket_name) AS bucket_name,
        MIN(created_at) AS started_at,
        MAX(updated_at) AS ended_at
    FROM normalized
    GROUP BY session_code_norm
)
INSERT INTO recording_sessions (
    session_code,
    bucket_name,
    source,
    status,
    started_at,
    ended_at,
    note
)
SELECT
    sa.session_code_norm,
    sa.bucket_name,
    'live'::recording_source,
    'completed'::session_status,
    sa.started_at,
    sa.ended_at,
    'migrated from file_records'
FROM session_agg sa
ON CONFLICT (session_code) DO UPDATE SET
    bucket_name = EXCLUDED.bucket_name,
    started_at = LEAST(recording_sessions.started_at, EXCLUDED.started_at),
    ended_at = GREATEST(COALESCE(recording_sessions.ended_at, EXCLUDED.ended_at), EXCLUDED.ended_at),
    updated_at = now();

-- 2) 迁移文件记录到会话附件表
WITH normalized AS (
    SELECT
        fr.*,
        COALESCE(NULLIF(fr.session_id, ''), 'legacy-bucket:' || fr.bucket_name) AS session_code_norm,
        CASE
            WHEN fr.kind IN ('recording_wav', 'raw_transcript', 'formal_text', 'meeting_minutes') THEN fr.kind
            WHEN fr.kind = 'recordings' THEN 'recording_wav'
            ELSE NULL
        END AS mapped_kind
    FROM file_records fr
),
resolved AS (
    SELECT
        n.*,
        rs.id AS resolved_session_id
    FROM normalized n
    JOIN recording_sessions rs
      ON rs.session_code = n.session_code_norm
    WHERE n.mapped_kind IS NOT NULL
)
INSERT INTO session_artifacts (
    session_id,
    artifact_type,
    bucket_name,
    object_key,
    content_type,
    byte_length,
    file_ext,
    created_at
)
SELECT
    r.resolved_session_id,
    r.mapped_kind::artifact_type,
    r.bucket_name,
    r.object_key,
    r.content_type,
    r.byte_length,
    lower(split_part(r.object_key, '.', array_length(string_to_array(r.object_key, '.'), 1))),
    r.created_at
FROM resolved r
ON CONFLICT (bucket_name, object_key) DO UPDATE SET
    session_id = EXCLUDED.session_id,
    artifact_type = EXCLUDED.artifact_type,
    content_type = EXCLUDED.content_type,
    byte_length = EXCLUDED.byte_length;

-- 3) 记录迁移事件
INSERT INTO session_events (session_id, event_type, event_payload, created_at)
SELECT
    rs.id,
    'migration',
    jsonb_build_object(
        'source', 'file_records',
        'session_code', rs.session_code
    ),
    now()
FROM recording_sessions rs
WHERE rs.note = 'migrated from file_records'
ON CONFLICT DO NOTHING;

COMMIT;

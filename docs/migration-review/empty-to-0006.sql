-- REVIEW ONLY. Not applied. Actual production inventory/backup/approval required.
-- Proposed schema memo MUST already exist and be reconciled with legacy data.
BEGIN;

SET LOCAL search_path TO "memo",pg_catalog;

CREATE TABLE memo.alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TYPE source_type_enum AS ENUM ('telegram', 'api');

CREATE TYPE event_status_enum AS ENUM ('draft', 'processed', 'exported');

CREATE TYPE file_type_enum AS ENUM ('photo', 'document', 'audio', 'video', 'voice');

CREATE TABLE users (
    id UUID NOT NULL,
    telegram_id BIGINT NOT NULL,
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255),
    username VARCHAR(255),
    university VARCHAR(500) NOT NULL,
    department VARCHAR(500) NOT NULL,
    programme VARCHAR(500) NOT NULL,
    company VARCHAR(500) NOT NULL,
    supervisor VARCHAR(500),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_users_telegram_id UNIQUE (telegram_id)
);

CREATE INDEX ix_users_telegram_id ON users (telegram_id);

CREATE TABLE conversations (
    id UUID NOT NULL,
    user_id UUID NOT NULL,
    state VARCHAR(100) NOT NULL,
    last_message_id INTEGER,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT uq_conversations_user_id UNIQUE (user_id)
);

COMMENT ON COLUMN conversations.state IS 'Current ConversationHandler state name for observability.';

COMMENT ON COLUMN conversations.last_message_id IS 'Telegram message_id of the most recent bot reply.';

CREATE TABLE events (
    id UUID NOT NULL,
    user_id UUID NOT NULL,
    event_date DATE NOT NULL,
    source_type source_type_enum NOT NULL,
    raw_text TEXT,
    status event_status_enum DEFAULT 'draft' NOT NULL,
    payload_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

COMMENT ON COLUMN events.payload_metadata IS 'Schema-less metadata for AI-extracted fields (Sprint 2+).';

CREATE INDEX ix_events_user_id ON events (user_id);

CREATE TABLE attachments (
    id UUID NOT NULL,
    event_id UUID NOT NULL,
    file_type file_type_enum NOT NULL,
    telegram_file_id VARCHAR(512) NOT NULL,
    storage_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE
);

COMMENT ON COLUMN attachments.storage_url IS 'Cloud storage URL, populated by Sprint 2 upload pipeline.';

CREATE INDEX ix_attachments_event_id ON attachments (event_id);

INSERT INTO memo.alembic_version (version_num) VALUES ('0001') RETURNING memo.alembic_version.version_num;

-- Running upgrade 0001 -> 0002

CREATE TYPE payload_type_enum AS ENUM ('text', 'voice', 'photo', 'document', 'multimodal');

ALTER TYPE event_status_enum RENAME TO processing_status_enum;

ALTER TYPE processing_status_enum ADD VALUE IF NOT EXISTS 'pending';

ALTER TYPE processing_status_enum ADD VALUE IF NOT EXISTS 'failed';

ALTER TABLE events ADD COLUMN captured_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL;

ALTER TABLE events ADD COLUMN payload_type payload_type_enum DEFAULT 'text' NOT NULL;

ALTER TABLE events ADD COLUMN is_deleted BOOLEAN DEFAULT 'false' NOT NULL;

CREATE INDEX ix_events_event_date ON events (event_date);

ALTER TABLE attachments ADD COLUMN original_filename VARCHAR(512);

ALTER TABLE attachments ADD COLUMN mime_type VARCHAR(255);

ALTER TABLE attachments ADD COLUMN file_size BIGINT;

ALTER TABLE attachments ADD COLUMN duration_seconds INTEGER;

ALTER TABLE attachments ADD COLUMN width INTEGER;

ALTER TABLE attachments ADD COLUMN height INTEGER;

ALTER TABLE attachments ADD COLUMN checksum VARCHAR(64);

ALTER TABLE attachments ADD COLUMN downloaded_at TIMESTAMP WITH TIME ZONE;

UPDATE memo.alembic_version SET version_num='0002' WHERE memo.alembic_version.version_num = '0001';

-- Running upgrade 0002 -> 0003

ALTER TYPE processing_status_enum ADD VALUE IF NOT EXISTS 'processing';

ALTER TABLE events ADD COLUMN ai_analysis JSONB;

ALTER TABLE events ADD COLUMN processing_retry_count INTEGER DEFAULT 0 NOT NULL;

UPDATE memo.alembic_version SET version_num='0003' WHERE memo.alembic_version.version_num = '0002';

-- Running upgrade 0003 -> 0004

CREATE TYPE topic_status_enum AS ENUM ('emerging', 'developing', 'established');

CREATE TYPE topic_trend_enum AS ENUM ('new', 'growing', 'stable', 'declining');

CREATE TABLE knowledge_topics (
    id UUID NOT NULL,
    user_id UUID NOT NULL,
    topic VARCHAR(500) NOT NULL,
    category VARCHAR(255),
    first_seen DATE NOT NULL,
    last_seen DATE NOT NULL,
    memory_count INTEGER DEFAULT '0' NOT NULL,
    status topic_status_enum DEFAULT 'emerging' NOT NULL,
    trend topic_trend_enum DEFAULT 'new' NOT NULL,
    evidence JSONB DEFAULT '[]'::jsonb NOT NULL,
    progression JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT uq_knowledge_topics_user_topic UNIQUE (user_id, topic)
);

CREATE INDEX ix_knowledge_topics_user_id ON knowledge_topics (user_id);

CREATE TYPE connection_type_enum AS ENUM ('CONTINUES', 'EXPANDS', 'REFLECTS', 'SOLVES', 'FOLLOWS_FROM', 'RELATES_TO');

CREATE TABLE memory_connections (
    id UUID NOT NULL,
    user_id UUID NOT NULL,
    source_event_id UUID NOT NULL,
    target_event_id UUID NOT NULL,
    connection_type connection_type_enum NOT NULL,
    explanation TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY(source_event_id) REFERENCES events (id) ON DELETE CASCADE,
    FOREIGN KEY(target_event_id) REFERENCES events (id) ON DELETE CASCADE,
    CONSTRAINT uq_memory_connections_pair_type UNIQUE (source_event_id, target_event_id, connection_type)
);

CREATE INDEX ix_memory_connections_user_id ON memory_connections (user_id);

CREATE INDEX ix_memory_connections_source_event_id ON memory_connections (source_event_id);

CREATE INDEX ix_memory_connections_target_event_id ON memory_connections (target_event_id);

CREATE TYPE snapshot_trigger_enum AS ENUM ('manual', 'threshold', 'scheduled');

CREATE TABLE progress_snapshots (
    id UUID NOT NULL,
    user_id UUID NOT NULL,
    narrative JSONB NOT NULL,
    evidence_event_ids JSONB DEFAULT '[]'::jsonb NOT NULL,
    memory_count INTEGER DEFAULT '0' NOT NULL,
    trigger snapshot_trigger_enum DEFAULT 'manual' NOT NULL,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_progress_snapshots_user_id ON progress_snapshots (user_id);

CREATE TABLE weekly_reflections (
    id UUID NOT NULL,
    user_id UUID NOT NULL,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    content JSONB NOT NULL,
    memory_count INTEGER DEFAULT '0' NOT NULL,
    active_days INTEGER DEFAULT '0' NOT NULL,
    insufficient_evidence BOOLEAN DEFAULT false NOT NULL,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_weekly_reflections_user_id ON weekly_reflections (user_id);

CREATE TABLE user_longitudinal_states (
    user_id UUID NOT NULL,
    last_analysis_at TIMESTAMP WITH TIME ZONE,
    events_since_last_analysis INTEGER DEFAULT '0' NOT NULL,
    last_analyzed_memory_count INTEGER DEFAULT '0' NOT NULL,
    last_proactive_insight_at TIMESTAMP WITH TIME ZONE,
    pending_proactive_insight JSONB,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (user_id),
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

UPDATE memo.alembic_version SET version_num='0004' WHERE memo.alembic_version.version_num = '0003';

-- Running upgrade 0004 -> 0005

ALTER TABLE users ALTER COLUMN university DROP NOT NULL;

ALTER TABLE users ALTER COLUMN department DROP NOT NULL;

ALTER TABLE users ALTER COLUMN programme DROP NOT NULL;

ALTER TABLE users ALTER COLUMN company DROP NOT NULL;

ALTER TABLE users ALTER COLUMN start_date DROP NOT NULL;

ALTER TABLE users ALTER COLUMN end_date DROP NOT NULL;

CREATE TABLE memo_projects (
    id UUID NOT NULL,
    user_id UUID NOT NULL,
    name VARCHAR(100) NOT NULL,
    name_key VARCHAR(100) NOT NULL,
    archived BOOLEAN DEFAULT 'false' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (user_id, name_key),
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_memo_projects_user_id ON memo_projects (user_id);

ALTER TABLE events ADD COLUMN project_id UUID;

ALTER TABLE events ADD CONSTRAINT fk_events_memo_project FOREIGN KEY(project_id) REFERENCES memo_projects (id);

CREATE INDEX ix_events_project_id ON events (project_id);

CREATE TABLE memo_capture_drafts (
    id UUID NOT NULL,
    user_id UUID NOT NULL,
    source_key VARCHAR(200) NOT NULL,
    kind VARCHAR(20) NOT NULL,
    state VARCHAR(20) NOT NULL,
    original_text TEXT,
    text TEXT,
    step INTEGER NOT NULL,
    answers JSONB NOT NULL,
    media JSONB NOT NULL,
    processing_error VARCHAR(100),
    project_id UUID,
    event_id UUID,
    verified_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (user_id, source_key),
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY(project_id) REFERENCES memo_projects (id),
    UNIQUE (event_id),
    FOREIGN KEY(event_id) REFERENCES events (id)
);

CREATE INDEX ix_memo_capture_drafts_user_id ON memo_capture_drafts (user_id);

CREATE INDEX ix_memo_capture_drafts_state ON memo_capture_drafts (state);

UPDATE memo.alembic_version SET version_num='0005' WHERE memo.alembic_version.version_num = '0004';

-- Running upgrade 0005 -> 0006

CREATE TABLE memo_telegram_state (
    namespace VARCHAR(150) NOT NULL,
    key VARCHAR(200) NOT NULL,
    data JSONB NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (namespace, key)
);

CREATE INDEX ix_memo_telegram_state_expires_at ON memo_telegram_state (expires_at);

CREATE TABLE memo_telegram_inbox (
    update_id BIGSERIAL NOT NULL,
    payload JSONB NOT NULL,
    state VARCHAR(20) NOT NULL,
    attempts INTEGER NOT NULL,
    received_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    available_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    locked_at TIMESTAMP WITH TIME ZONE,
    last_error_type VARCHAR(100),
    PRIMARY KEY (update_id)
);

CREATE INDEX ix_memo_telegram_inbox_state ON memo_telegram_inbox (state);

CREATE INDEX ix_memo_telegram_inbox_pending ON memo_telegram_inbox (state, available_at);

CREATE TABLE memo_telegram_lease (
    key VARCHAR(100) NOT NULL,
    owner VARCHAR(50) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (key)
);

UPDATE memo.alembic_version SET version_num='0006' WHERE memo.alembic_version.version_num = '0005';

COMMIT;


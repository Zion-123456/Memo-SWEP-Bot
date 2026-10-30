-- REVIEW ONLY. Not applied. Actual production inventory/backup/approval required.
-- Proposed schema memo MUST already exist and be reconciled with legacy data.
BEGIN;

SET LOCAL search_path TO "memo",pg_catalog;

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


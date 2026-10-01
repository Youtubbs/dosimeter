-- Initial schema. No column anywhere stores a worker name.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE exposures (
    id                  text PRIMARY KEY,
    worker_id           text NOT NULL,
    district            text NOT NULL,
    occurred_on         date,
    status              text NOT NULL DEFAULT 'received',
    narrative           text,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX exposures_district_idx ON exposures (district);
CREATE INDEX exposures_worker_idx ON exposures (worker_id);

CREATE TABLE artifacts (
    id                  bigserial PRIMARY KEY,
    exposure_id         text NOT NULL REFERENCES exposures (id) ON DELETE CASCADE,
    kind                text NOT NULL,
    content_sha256      text NOT NULL,
    s3_bucket           text NOT NULL,
    s3_key              text NOT NULL,
    status              text NOT NULL DEFAULT 'pending',
    skipped_reason      text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (exposure_id, content_sha256)
);

CREATE TABLE extracted_fields (
    id                  bigserial PRIMARY KEY,
    exposure_id         text NOT NULL REFERENCES exposures (id) ON DELETE CASCADE,
    artifact_id         bigint NOT NULL REFERENCES artifacts (id) ON DELETE CASCADE,
    field_key           text NOT NULL,
    value               text,
    unit                text,
    confidence          numeric(6, 5),
    page                integer,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX extracted_fields_exposure_idx ON extracted_fields (exposure_id);

CREATE TABLE officers (
    id                  bigserial PRIMARY KEY,
    officer_code        text NOT NULL UNIQUE,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE grants (
    id                  bigserial PRIMARY KEY,
    officer_id          bigint NOT NULL REFERENCES officers (id) ON DELETE CASCADE,
    district            text NOT NULL,
    granted_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (officer_id, district)
);

CREATE TABLE worker_dose_histories (
    id                  bigserial PRIMARY KEY,
    worker_id           text NOT NULL,
    quantity            text NOT NULL,
    value               numeric(12, 4) NOT NULL,
    unit                text NOT NULL,
    as_of               date NOT NULL,
    note                text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (worker_id, quantity, as_of)
);

-- 1024 matches the embedding model recorded in the decisions table. Changing
-- the model means a new migration, not an edit to this one.
CREATE TABLE historical_exposures (
    id                  bigserial PRIMARY KEY,
    exposure_id         text NOT NULL UNIQUE,
    worker_id           text NOT NULL,
    district            text NOT NULL,
    occurred_on         date NOT NULL,
    outcome             text NOT NULL,
    deciding_rule       text NOT NULL,
    narrative           text NOT NULL,
    normalized_fields   jsonb NOT NULL DEFAULT '{}'::jsonb,
    embedding           vector(1024),
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX historical_exposures_district_idx ON historical_exposures (district);

CREATE TABLE sessions (
    id                  uuid PRIMARY KEY,
    officer_id          bigint REFERENCES officers (id),
    exposure_id         text REFERENCES exposures (id),
    correlation_id      text NOT NULL,
    started_at          timestamptz NOT NULL DEFAULT now(),
    ended_at            timestamptz
);

CREATE TABLE review_queue (
    id                  bigserial PRIMARY KEY,
    exposure_id         text NOT NULL REFERENCES exposures (id) ON DELETE CASCADE,
    district            text NOT NULL,
    reason              text NOT NULL,
    state               text NOT NULL DEFAULT 'waiting',
    created_at          timestamptz NOT NULL DEFAULT now(),
    claimed_by          bigint REFERENCES officers (id),
    claimed_at          timestamptz
);

CREATE INDEX review_queue_state_idx ON review_queue (state, district);

CREATE TABLE review_decisions (
    id                  bigserial PRIMARY KEY,
    queue_id            bigint NOT NULL REFERENCES review_queue (id) ON DELETE CASCADE,
    decision            text NOT NULL,
    original_payload    jsonb NOT NULL,
    edited_payload      jsonb,
    approver_officer_id bigint NOT NULL REFERENCES officers (id),
    decided_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE run_records (
    id                  uuid PRIMARY KEY,
    correlation_id      text NOT NULL,
    exposure_id         text REFERENCES exposures (id),
    officer_id          bigint REFERENCES officers (id),
    command             text NOT NULL,
    turn_kind           text NOT NULL,
    outcome             text,
    started_at          timestamptz NOT NULL DEFAULT now(),
    finished_at         timestamptz
);

CREATE INDEX run_records_correlation_idx ON run_records (correlation_id);

CREATE TABLE tool_invocations (
    id                  bigserial PRIMARY KEY,
    run_id              uuid NOT NULL REFERENCES run_records (id) ON DELETE CASCADE,
    tool_name           text NOT NULL,
    argument_sha256     text NOT NULL,
    outcome             text NOT NULL,
    duration_ms         numeric(12, 3),
    occurred_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rule_invocations (
    id                  bigserial PRIMARY KEY,
    run_id              uuid NOT NULL REFERENCES run_records (id) ON DELETE CASCADE,
    rule_id             text NOT NULL,
    outcome             text NOT NULL,
    threshold_named     text,
    inputs              jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE retrievals (
    id                  bigserial PRIMARY KEY,
    run_id              uuid NOT NULL REFERENCES run_records (id) ON DELETE CASCADE,
    query_sha256        text NOT NULL,
    chunk_ids           text[] NOT NULL DEFAULT '{}',
    scores              double precision[] NOT NULL DEFAULT '{}',
    status_filter       text,
    occurred_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE model_calls (
    id                  bigserial PRIMARY KEY,
    run_id              uuid NOT NULL REFERENCES run_records (id) ON DELETE CASCADE,
    model_id            text NOT NULL,
    role                text NOT NULL,
    input_tokens        integer NOT NULL DEFAULT 0,
    output_tokens       integer NOT NULL DEFAULT 0,
    duration_ms         numeric(12, 3),
    occurred_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE escalation_triggers (
    id                  bigserial PRIMARY KEY,
    run_id              uuid NOT NULL REFERENCES run_records (id) ON DELETE CASCADE,
    trigger_name        text NOT NULL,
    evaluated           boolean NOT NULL DEFAULT false,
    fired               boolean NOT NULL DEFAULT false,
    detail              text,
    occurred_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE guardrail_events (
    id                  bigserial PRIMARY KEY,
    run_id              uuid NOT NULL REFERENCES run_records (id) ON DELETE CASCADE,
    stage               text NOT NULL,
    guardrail_id        text,
    action              text NOT NULL,
    detail              jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE idempotency_keys (
    key                 text PRIMARY KEY,
    scope               text NOT NULL,
    result_ref          text,
    created_at          timestamptz NOT NULL DEFAULT now()
);

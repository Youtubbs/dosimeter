-- What a turn did, in enough detail for trace and the evaluators.

ALTER TABLE run_records ADD COLUMN session_id uuid REFERENCES sessions (id);
ALTER TABLE run_records ADD COLUMN corrects_run_id uuid REFERENCES run_records (id);
ALTER TABLE run_records ADD COLUMN token_totals jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE tool_invocations ADD COLUMN arguments jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE tool_invocations ADD COLUMN result jsonb;
ALTER TABLE tool_invocations ADD COLUMN worker text;

ALTER TABLE rule_invocations ADD COLUMN result jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE rule_invocations ADD COLUMN dose_quantity text;
ALTER TABLE rule_invocations ADD COLUMN path text;

ALTER TABLE retrievals ADD COLUMN statuses text[] NOT NULL DEFAULT '{}';
ALTER TABLE retrievals ADD COLUMN query_text text;

ALTER TABLE model_calls ADD COLUMN agent text;

CREATE TABLE worker_dispatches (
    id                  bigserial PRIMARY KEY,
    run_id              uuid NOT NULL REFERENCES run_records (id) ON DELETE CASCADE,
    worker              text NOT NULL,
    reason              text NOT NULL,
    iteration           integer NOT NULL DEFAULT 1,
    redispatch_trigger  text,
    occurred_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE reviewer_verdicts (
    id                  bigserial PRIMARY KEY,
    run_id              uuid NOT NULL REFERENCES run_records (id) ON DELETE CASCADE,
    iteration           integer NOT NULL,
    worker              text NOT NULL,
    verdict             text NOT NULL,
    objections          jsonb NOT NULL DEFAULT '[]'::jsonb,
    occurred_at         timestamptz NOT NULL DEFAULT now()
);

-- The approved record. Written by the harness after a recorded approval, never
-- by an agent, and never transmitted anywhere.
CREATE TABLE approved_records (
    id                  bigserial PRIMARY KEY,
    exposure_id         text NOT NULL REFERENCES exposures (id) ON DELETE CASCADE,
    decision_id         bigint NOT NULL REFERENCES review_decisions (id),
    idempotency_key     text NOT NULL UNIQUE,
    payload             jsonb NOT NULL,
    approver_officer_id bigint NOT NULL REFERENCES officers (id),
    written_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX worker_dispatches_run_idx ON worker_dispatches (run_id);
CREATE INDEX reviewer_verdicts_run_idx ON reviewer_verdicts (run_id, iteration);

-- The dossier a turn produced. Rendering is a separate concern; this is the
-- stored payload that a later command reads back cold.
CREATE TABLE dossiers (
    id                  bigserial PRIMARY KEY,
    exposure_id         text NOT NULL REFERENCES exposures (id) ON DELETE CASCADE,
    run_id              uuid NOT NULL REFERENCES run_records (id) ON DELETE CASCADE,
    payload             jsonb NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX dossiers_exposure_idx ON dossiers (exposure_id, created_at DESC);

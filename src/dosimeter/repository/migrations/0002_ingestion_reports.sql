-- What one submit run did with a packet.

CREATE TABLE ingestion_reports (
    id                    bigserial PRIMARY KEY,
    exposure_id           text NOT NULL REFERENCES exposures (id) ON DELETE CASCADE,
    artifacts_processed   integer NOT NULL DEFAULT 0,
    artifacts_skipped     integer NOT NULL DEFAULT 0,
    fields_extracted      integer NOT NULL DEFAULT 0,
    low_confidence_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
    failures              jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ingestion_reports_exposure_idx ON ingestion_reports (exposure_id, created_at DESC);

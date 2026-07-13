-- Tracks the processing status of an uploaded lease through each pipeline
-- stage, independent of the pipeline's own tables (lease_clauses,
-- compliance_findings). This exists specifically to support the async
-- upload flow: POST /leases creates a row and returns immediately;
-- GET /leases/{id} reads this row so the frontend can poll for progress
-- without the pipeline's own tables needing to double as a status system.
CREATE TABLE IF NOT EXISTS leases (
    id                UUID PRIMARY KEY,
    original_filename TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'uploaded'
                       CHECK (status IN (
                           'uploaded', 'extracting_text', 'parsing_clauses',
                           'checking_compliance', 'verifying', 'complete', 'failed'
                       )),
    error_message     TEXT,
    uploaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at      TIMESTAMPTZ
);

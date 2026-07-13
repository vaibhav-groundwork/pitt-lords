-- Enables vector similarity search directly inside Postgres.
CREATE EXTENSION IF NOT EXISTS vector;

-- One row per legal requirement, hand-sourced from Phase 1.
-- This IS your source-of-record table, living in the DB instead of a spreadsheet.
CREATE TABLE IF NOT EXISTS legal_sources (
    id              SERIAL PRIMARY KEY,
    jurisdiction    TEXT NOT NULL,         -- 'PA_STATE' or 'PITTSBURGH_CITY'
    citation        TEXT NOT NULL,         -- e.g. '68 P.S. § 250.511a'
    requirement_key TEXT NOT NULL,         -- e.g. 'security_deposit_max_year1'
    summary         TEXT NOT NULL,         -- plain-language description
    full_text       TEXT NOT NULL,         -- exact statutory/ordinance text
    source_url      TEXT NOT NULL,
    retrieved_on    DATE NOT NULL,
    source_currency_date DATE,             -- date the source claims to be current through
    last_verified   DATE NOT NULL DEFAULT CURRENT_DATE,
    embedding       vector(384)            -- matches all-MiniLM-L6-v2 dimension, same as Groundwork
);

-- One row per uploaded lease's parsed clauses (Phase 3 output lands here).
CREATE TABLE IF NOT EXISTS lease_clauses (
    id              SERIAL PRIMARY KEY,
    lease_id        UUID NOT NULL,
    requirement_key TEXT,                  -- matches legal_sources.requirement_key, null if unmatched
    clause_text     TEXT,                  -- null if requirement was absent from the lease
    confidence      REAL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per compliance flag in a generated report (Phase 4 + 5 output).
CREATE TABLE IF NOT EXISTS compliance_findings (
    id                SERIAL PRIMARY KEY,
    lease_id          UUID NOT NULL,
    requirement_key   TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('compliant', 'contradicts', 'absent', 'needs_review')),
    explanation       TEXT NOT NULL,
    verifier_confirmed BOOLEAN NOT NULL DEFAULT false,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_legal_sources_requirement_key ON legal_sources (requirement_key);
CREATE INDEX IF NOT EXISTS idx_lease_clauses_lease_id ON lease_clauses (lease_id);
CREATE INDEX IF NOT EXISTS idx_compliance_findings_lease_id ON compliance_findings (lease_id);

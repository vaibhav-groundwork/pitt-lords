-- Human-readable titles for legal_sources.family_key groups, used by
-- report_builder.py to show plain-language section headings in the report
-- ("Notice before ending a lease") instead of raw citation numbers
-- ("501") as the primary heading. Keyed by (family_key, jurisdiction)
-- since family_key derivation is per-citation and not guaranteed unique
-- across jurisdictions, even though no real collision currently exists.
CREATE TABLE IF NOT EXISTS family_labels (
    family_key      TEXT NOT NULL,
    jurisdiction    TEXT NOT NULL,
    friendly_title  TEXT NOT NULL,
    PRIMARY KEY (family_key, jurisdiction)
);

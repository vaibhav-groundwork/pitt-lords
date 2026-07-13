-- family_key groups subsections of the same statutory/ordinance section
-- together (e.g. 511.1(a), 511.1(b), 511.1(c) all get family_key '511.1'),
-- derived mechanically from each row's own citation string. This lets
-- compliance-diff see modifying/related subsections (like the notice-can-be-
-- waived clause, 501(e), alongside the default notice periods, 501(a)-(b))
-- without maintaining a hand-curated relationship list.
ALTER TABLE legal_sources
    ADD COLUMN IF NOT EXISTS family_key TEXT;

CREATE INDEX IF NOT EXISTS idx_legal_sources_family_key ON legal_sources (family_key);

-- Some relationships cross section families entirely (e.g. 511.1(c)'s own
-- text explicitly says "in accordance with sections 511.2 and 512"). These
-- are detected automatically by parsing full_text for explicit citation
-- mentions, not hand-curated, so the mechanism scales as the corpus grows.
-- Stored at the family level (not per-row) since a reference to "section 512"
-- should pull in every subsection of 512, not one arbitrarily chosen row.
CREATE TABLE IF NOT EXISTS family_cross_references (
    id                  SERIAL PRIMARY KEY,
    source_family_key   TEXT NOT NULL,
    target_family_key   TEXT NOT NULL,
    jurisdiction        TEXT NOT NULL,  -- cross-references are intra-jurisdiction
    UNIQUE (source_family_key, target_family_key, jurisdiction)
);

-- Adds the two-tier distinction agreed on: 'requirement' items are checked
-- against a specific lease clause and produce a compliant/absent/contradicts
-- verdict. 'awareness' items are background legal facts that are true
-- regardless of lease wording, surfaced only if the lease doesn't already
-- address the topic, with no compliance verdict attached.
ALTER TABLE legal_sources
    ADD COLUMN IF NOT EXISTS check_tier TEXT NOT NULL DEFAULT 'requirement'
        CHECK (check_tier IN ('requirement', 'awareness'));

-- Reclassify the two existing entries that don't actually have a specific
-- lease clause to check against -- they're background rights/duties that
-- apply regardless of what the lease says, not something a lease clause
-- states, omits, or contradicts. See decisions.md for the full reasoning.
UPDATE legal_sources
SET check_tier = 'awareness'
WHERE requirement_key IN (
    'landlord_duty_common_area_care',
    'drug_violation_lease_breach_grounds'
);

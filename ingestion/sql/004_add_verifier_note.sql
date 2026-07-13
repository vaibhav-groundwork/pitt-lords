-- Records why the verifier did or didn't confirm a compliance finding.
-- Without this, verifier_confirmed=false alone would give no explanation
-- of the disagreement, exactly the kind of opaque signal this project has
-- been designed against throughout.
ALTER TABLE compliance_findings
    ADD COLUMN IF NOT EXISTS verifier_note TEXT;

-- verifier_confirmed was originally NOT NULL DEFAULT false, a two-state
-- column. The verifier agent needs a genuine three-state signal: never
-- verified yet (NULL), confirmed (true), or disputed (false) -- collapsing
-- "not yet run" and "genuinely disputed" into the same false value would
-- make a finding that simply hasn't been verified indistinguishable from
-- one the verifier actively disagreed with.
ALTER TABLE compliance_findings
    ALTER COLUMN verifier_confirmed DROP NOT NULL,
    ALTER COLUMN verifier_confirmed DROP DEFAULT;

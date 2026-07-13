-- Adds a status field so a requirement can be marked as something other than
-- straightforwardly active, e.g. Pittsburgh's Chapter 781 rental registration
-- ordinance, which is currently stayed pending litigation.
ALTER TABLE legal_sources
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'stayed_pending_litigation', 'superseded'));

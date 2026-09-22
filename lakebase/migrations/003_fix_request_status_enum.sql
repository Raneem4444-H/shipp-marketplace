-- ============================================================================
-- Migration: 003_fix_request_status_enum.sql
-- Resolves: GitHub Issue #12 (requests.status enum mismatch with spec §7.2)
-- Depends on: 001_init_lakebase_schema.sql having already run
-- Platform: Databricks Lakebase (PostgreSQL-compatible)
--
-- Problem:
--   DDL enum:  OPEN / PENDING / MATCHED / FULFILLED / CANCELLED
--   Spec §7.2: Open / MatchesAvailable / ItemSaved / Closed
--   Same failure class as Issue #6 (listings.status) on a different table.
--
-- ⚠ TEAM CONFIRMATION REQUIRED BEFORE RUNNING:
--   PENDING   -> mapped to OPEN below (best guess). If PENDING actually
--     means "submitted but not yet processed by the ingestion pipeline"
--     (a real transient state during your <60s window), it may deserve
--     its own spec state instead of collapsing into OPEN.
--   CANCELLED -> mapped to CLOSED below (best guess). A request the
--     requester withdrew is arguably different from one closed because
--     it was fulfilled — your §5.8 analytics (save rate, fulfillment
--     rate) may need that distinction. If so, add CANCELLED as a 5th
--     state to the spec and to the CHECK constraint below, don't
--     silently fold it into CLOSED.
-- ============================================================================
-- ----------------------------------------------------------------------------
-- STEP 0 — verify the constraint name matches what this migration assumes.
-- ----------------------------------------------------------------------------
SET search_path TO shipp;
SELECT conname,
    pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'shipp.requests'::regclass
    AND contype = 'c';
-- ----------------------------------------------------------------------------
-- STEP 1 — the migration, as one atomic transaction.
-- ----------------------------------------------------------------------------
BEGIN;
SET search_path TO shipp;
UPDATE shipp.requests
SET status = CASE
        status
        WHEN 'OPEN' THEN 'OPEN'
        WHEN 'PENDING' THEN 'OPEN' -- CONFIRM with team, see header note
        WHEN 'MATCHED' THEN 'MATCHES_AVAILABLE'
        WHEN 'FULFILLED' THEN 'ITEM_SAVED'
        WHEN 'CANCELLED' THEN 'CLOSED' -- CONFIRM with team, see header note
        ELSE status
    END
WHERE status IN (
        'OPEN',
        'PENDING',
        'MATCHED',
        'FULFILLED',
        'CANCELLED'
    );
ALTER TABLE shipp.requests DROP CONSTRAINT IF EXISTS chk_request_status;
ALTER TABLE shipp.requests
ADD CONSTRAINT chk_request_status CHECK (
        status IN (
            'OPEN',
            'MATCHES_AVAILABLE',
            'ITEM_SAVED',
            'CLOSED'
        )
    );
-- If the team decides CANCELLED needs to stay distinct, add it here:
-- CHECK (status IN ('OPEN','MATCHES_AVAILABLE','ITEM_SAVED','CLOSED','CANCELLED'));
COMMENT ON COLUMN shipp.requests.status IS 'Request lifecycle status: OPEN, MATCHES_AVAILABLE, ITEM_SAVED, CLOSED. Aligned with spec §7.2 via Issue #12.';
COMMIT;
-- To dry-run instead: replace COMMIT with ROLLBACK, inspect the
-- verification queries below, then re-run with COMMIT.
-- ----------------------------------------------------------------------------
-- STEP 2 — verification (safe to run standalone, read-only)
-- ----------------------------------------------------------------------------
-- Should return 0 rows.
SELECT *
FROM shipp.requests
WHERE status NOT IN (
        'OPEN',
        'MATCHES_AVAILABLE',
        'ITEM_SAVED',
        'CLOSED'
    );
-- Distribution check — useful for your capstone demo narrative.
SELECT status,
    COUNT(*)
FROM shipp.requests
GROUP BY status
ORDER BY status;
-- Confirms the constraint rejects old values (should FAIL — that's the pass):
-- INSERT INTO shipp.requests
--   (request_id, requester_id, request_text, status)
--   VALUES ('test-status-check', (SELECT user_id FROM shipp.users LIMIT 1), 'Test', 'PENDING');
-- ----------------------------------------------------------------------------
-- ROLLBACK SCRIPT
-- ----------------------------------------------------------------------------
-- BEGIN;
-- UPDATE shipp.requests SET status = CASE status
--     WHEN 'OPEN'              THEN 'OPEN'
--     WHEN 'MATCHES_AVAILABLE' THEN 'MATCHED'
--     WHEN 'ITEM_SAVED'        THEN 'FULFILLED'
--     WHEN 'CLOSED'            THEN 'CANCELLED'
--     ELSE status
-- END;
-- ALTER TABLE shipp.requests DROP CONSTRAINT IF EXISTS chk_request_status;
-- ALTER TABLE shipp.requests ADD CONSTRAINT chk_request_status
--     CHECK (status IN ('OPEN', 'PENDING', 'MATCHED', 'FULFILLED', 'CANCELLED'));
-- COMMIT;
-- ----------------------------------------------------------------------------
-- STILL OPEN AFTER THIS MIGRATION
-- ----------------------------------------------------------------------------
-- 1. Notify matching-engine and frontend owners — same field, same risk
--    as Issue #6's listings.status.
-- 2. Update shipp-marketplace-spec_V2.md §7.2 only if PENDING/CANCELLED
--    end up needing their own states rather than the mapping above.
-- 3. This is now the LAST status-vocabulary fix — #6 and #12 both closed
--    after this runs. Confirm both together in the same demo dry run.
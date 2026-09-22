-- ============================================================================
-- Migration: 002_fix_listing_status_enum.sql
-- Resolves: GitHub Issue #6 (listings.status enum mismatch with spec §7.1)
-- Depends on: 001_init_lakebase_schema.sql having already run
-- Platform: Databricks Lakebase (PostgreSQL-compatible)
--
-- Problem:
--   DDL enum:  ACTIVE / MATCHED / RESERVED / ARCHIVED / EXPIRED
--   Spec §7.1: Draft / Available / Unavailable / Withdrawn / Expired
--   These do not map 1:1. Left unresolved, the matching engine or frontend
--   will check for one vocabulary while the database only ever returns
--   the other — a silent failure, not a thrown error.
--
-- ⚠ TEAM CONFIRMATION REQUIRED BEFORE RUNNING:
--   MATCHED  -> mapped to AVAILABLE below (best guess, not confirmed)
--   RESERVED -> mapped to UNAVAILABLE below (best guess, not confirmed)
--   If MATCHED/RESERVED carry meaning the spec's 5 states can't express
--   (e.g. "has candidate matches" vs. generically available), the SPEC
--   may need a 6th state instead of forcing this lossy mapping. Settle
--   that with your team before running this against real data.
-- ============================================================================
-- ----------------------------------------------------------------------------
-- STEP 0 — verify the constraint name matches what this migration assumes.
-- Run standalone first; compare output to chk_listing_status below.
-- ----------------------------------------------------------------------------
SET search_path TO shipp;
SELECT conname,
    pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'shipp.listings'::regclass
    AND contype = 'c';
-- ----------------------------------------------------------------------------
-- STEP 1 — the migration itself, as one atomic transaction.
-- If anything fails, the whole thing rolls back.
-- ----------------------------------------------------------------------------
BEGIN;
SET search_path TO shipp;
-- Migrate existing data BEFORE tightening the constraint — the ALTER
-- below will fail if any row still holds an old-vocabulary value.
UPDATE shipp.listings
SET status = CASE
        status
        WHEN 'ACTIVE' THEN 'AVAILABLE'
        WHEN 'MATCHED' THEN 'AVAILABLE' -- CONFIRM with team, see header note
        WHEN 'RESERVED' THEN 'UNAVAILABLE' -- CONFIRM with team, see header note
        WHEN 'ARCHIVED' THEN 'WITHDRAWN'
        WHEN 'EXPIRED' THEN 'EXPIRED'
        ELSE status
    END
WHERE status IN ('ACTIVE', 'MATCHED', 'RESERVED', 'ARCHIVED');
-- Replace the constraint with the spec-aligned vocabulary.
ALTER TABLE shipp.listings DROP CONSTRAINT IF EXISTS chk_listing_status;
ALTER TABLE shipp.listings
ADD CONSTRAINT chk_listing_status CHECK (
        status IN (
            'DRAFT',
            'AVAILABLE',
            'UNAVAILABLE',
            'WITHDRAWN',
            'EXPIRED'
        )
    );
-- Update the default so newly-inserted listings start in a valid,
-- spec-aligned state instead of the old default of 'ACTIVE'.
ALTER TABLE shipp.listings
ALTER COLUMN status
SET DEFAULT 'DRAFT';
-- Update the column comment to reflect the new canonical vocabulary.
COMMENT ON COLUMN shipp.listings.status IS 'Listing lifecycle status: DRAFT, AVAILABLE, UNAVAILABLE, WITHDRAWN, EXPIRED. Aligned with spec §7.1 via Issue #6.';
COMMIT;
-- To dry-run instead: replace COMMIT with ROLLBACK, inspect row counts
-- from the verification queries below, then re-run with COMMIT.
-- ----------------------------------------------------------------------------
-- STEP 2 — verification (safe to run standalone, read-only)
-- ----------------------------------------------------------------------------
-- Should return 0 rows — confirms no listing is left with an old value.
SELECT *
FROM shipp.listings
WHERE status NOT IN (
        'DRAFT',
        'AVAILABLE',
        'UNAVAILABLE',
        'WITHDRAWN',
        'EXPIRED'
    );
-- Confirms the constraint now rejects old values (this INSERT should FAIL —
-- that failure is the pass condition; uncomment to test):
-- INSERT INTO shipp.listings
--   (listing_id, donor_id, title, status)
--   VALUES ('test-status-check', (SELECT user_id FROM shipp.users LIMIT 1), 'Test', 'ACTIVE');
-- Sanity check on the distribution after migration (useful for your
-- capstone demo — shows the data actually moved, not just the constraint):
SELECT status,
    COUNT(*)
FROM shipp.listings
GROUP BY status
ORDER BY status;
-- ----------------------------------------------------------------------------
-- ROLLBACK SCRIPT — only use if this migration needs to be fully reverted
-- (e.g. team decides on a different mapping after this already ran)
-- ----------------------------------------------------------------------------
-- BEGIN;
-- UPDATE shipp.listings SET status = CASE status
--     WHEN 'DRAFT'       THEN 'ACTIVE'
--     WHEN 'AVAILABLE'   THEN 'ACTIVE'
--     WHEN 'UNAVAILABLE' THEN 'RESERVED'
--     WHEN 'WITHDRAWN'   THEN 'ARCHIVED'
--     WHEN 'EXPIRED'     THEN 'EXPIRED'
--     ELSE status
-- END;
-- ALTER TABLE shipp.listings DROP CONSTRAINT IF EXISTS chk_listing_status;
-- ALTER TABLE shipp.listings ADD CONSTRAINT chk_listing_status
--     CHECK (status IN ('ACTIVE', 'MATCHED', 'RESERVED', 'ARCHIVED', 'EXPIRED'));
-- ALTER TABLE shipp.listings ALTER COLUMN status SET DEFAULT 'ACTIVE';
-- COMMIT;
-- ----------------------------------------------------------------------------
-- STILL OPEN AFTER THIS MIGRATION
-- ----------------------------------------------------------------------------
-- 1. Notify the matching-engine owner and frontend owner (per CODEOWNERS)
--    before either is built further against listings.status — this is
--    exactly the field they'll hardcode against.
-- 2. Update shipp-marketplace-spec_V2.md §7.1 only if the final vocabulary
--    ends up differing from what's already written there.
-- 3. Issue #12 (requests.status) is the same class of bug on a different
--    table — track and fix separately as 003_fix_request_status_enum.sql.
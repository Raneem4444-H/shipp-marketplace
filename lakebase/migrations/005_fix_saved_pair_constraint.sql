-- ============================================================================
-- Migration: 005_fix_saved_pair_constraint.sql
-- Resolves: GitHub Issue #10 (chk_saved_pair uses OR, allowing a
--           saved_item with a NULL request_id)
-- Depends on: 001_init_lakebase_schema.sql having already run
-- Platform: Databricks Lakebase (PostgreSQL-compatible)
--
-- Problem:
--   CONSTRAINT chk_saved_pair CHECK(request_id IS NOT NULL OR listing_id IS NOT NULL)
--   Per spec §5.6/§13.5, save_item() is always triggered from a Request
--   context — a Requester saves a Listing FOR a specific Request. There
--   is no documented workflow where a Listing is saved with no Request
--   attached. The constraint should be AND, not OR.
--
-- This migration is SELF-GUARDING: it checks for violating rows first
-- and raises an exception (aborting cleanly) if any exist, rather than
-- letting the ALTER fail with a less informative Postgres error, or
-- silently trusting you remembered to check first.
-- ============================================================================
-- ----------------------------------------------------------------------------
-- STEP 0 — verify the constraint name matches what this migration assumes.
-- ----------------------------------------------------------------------------
SET search_path TO shipp;
SELECT conname,
    pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'shipp.saved_items'::regclass
    AND contype = 'c';
-- ----------------------------------------------------------------------------
-- STEP 1 — the migration, as one atomic transaction with a guard clause.
-- ----------------------------------------------------------------------------
BEGIN;
SET search_path TO shipp;
DO $$
DECLARE violation_count INT;
BEGIN
SELECT COUNT(*) INTO violation_count
FROM shipp.saved_items
WHERE request_id IS NULL
    OR listing_id IS NULL;
IF violation_count > 0 THEN RAISE EXCEPTION 'Migration 005 aborted: % row(s) in saved_items have a NULL request_id or listing_id. Resolve these before tightening chk_saved_pair — see the resolution query below this block.',
violation_count;
END IF;
END $$;
-- Only reached if the guard above didn't raise — no violating rows exist.
ALTER TABLE shipp.saved_items DROP CONSTRAINT IF EXISTS chk_saved_pair;
ALTER TABLE shipp.saved_items
ADD CONSTRAINT chk_saved_pair CHECK (
        request_id IS NOT NULL
        AND listing_id IS NOT NULL
    );
COMMIT;
-- If the DO block raises, the transaction auto-rolls-back — nothing is
-- left half-applied. Fix the violating rows (see below) and re-run.
-- ----------------------------------------------------------------------------
-- IF THE GUARD ABORTED — run this to see exactly which rows are violating,
-- then decide: backfill a request_id, or delete the row if truly invalid.
-- ----------------------------------------------------------------------------
-- SELECT * FROM shipp.saved_items WHERE request_id IS NULL OR listing_id IS NULL;
--
-- To delete confirmed-invalid rows (only after team sign-off, not blindly):
-- DELETE FROM shipp.saved_items WHERE request_id IS NULL OR listing_id IS NULL;
-- ----------------------------------------------------------------------------
-- STEP 2 — verification (safe to run standalone, read-only)
-- ----------------------------------------------------------------------------
-- Should return 0 rows.
SELECT *
FROM shipp.saved_items
WHERE request_id IS NOT NULL
    AND listing_id IS NOT NULL;
-- Validate schema-level enforcement
SELECT column_name,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'shipp'
    AND table_name = 'saved_items'
    AND column_name IN ('request_id', 'listing_id');
-- Confirms the tightened constraint rejects bad inserts (should FAIL —
-- that failure is the pass condition):
-- INSERT INTO shipp.saved_items (saved_item_id, user_id, listing_id, saved_at)
--   VALUES ('test-pair-check', (SELECT user_id FROM shipp.users LIMIT 1),
--           (SELECT listing_id FROM shipp.listings LIMIT 1), now());
-- ----------------------------------------------------------------------------
-- ROLLBACK SCRIPT
-- ----------------------------------------------------------------------------
-- BEGIN;
-- ALTER TABLE shipp.saved_items DROP CONSTRAINT IF EXISTS chk_saved_pair;
-- ALTER TABLE shipp.saved_items ADD CONSTRAINT chk_saved_pair
--     CHECK (request_id IS NOT NULL OR listing_id IS NOT NULL);
-- COMMIT;
-- ----------------------------------------------------------------------------
-- STILL OPEN AFTER THIS MIGRATION
-- ----------------------------------------------------------------------------
-- 1. Add the same validation to the save_item() agent tool code itself
--    (defense-in-depth — don't rely on the DB constraint alone to catch
--    a bug in agent logic before it ever reaches the database).
-- 2. This closes the last of the four high-priority bugs (#6, #9, #10, #12)
--    flagged as blocking the matching engine and frontend. Confirm all
--    four together in one demo dry run before building further on top
--    of listings/requests/saved_items.
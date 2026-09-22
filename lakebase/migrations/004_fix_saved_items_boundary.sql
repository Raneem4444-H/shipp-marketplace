-- ============================================================================
-- Migration: 004_fix_saved_items_boundary.sql
-- Resolves: GitHub Issue #9 (saved_items.match_score/match_reason violate
--           the Lakebase/Delta boundary defined in spec §6.5)
-- Depends on: 001_init_lakebase_schema.sql having already run
-- Platform: Databricks Lakebase (PostgreSQL-compatible)
--
-- Problem:
--   Spec §6.5: "Lakebase = Operational Truth, Delta = Pipeline/Analytical
--   Data." match_score/match_reason are derived analytical output from
--   the Spark matching engine (BN-03/BN-06) — they belong in
--   gold_candidate_matches, not on the operational saved_items table.
--   Storing them here creates two sources of truth that can silently
--   diverge (Gold recomputes; Lakebase's copy doesn't).
--
-- DECISION IMPLEMENTED: Option A — remove the columns, matches spec.
--   Reading "why this was recommended" must join saved_items to
--   gold_candidate_matches (on listing_id + request_id) at read time
--   instead of reading a stored value. That query/agent-code change is
--   NOT in this SQL file — track it as a separate application-layer task.
--
-- ⚠ This migration is destructive (DROP COLUMN). A backup table is
--   created first so no data is lost even though the live columns go away.
-- ============================================================================
-- ----------------------------------------------------------------------------
-- STEP 0 — confirm current column state before touching anything.
-- ----------------------------------------------------------------------------
SET search_path TO shipp;
SELECT column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'shipp'
    AND table_name = 'saved_items'
ORDER BY ordinal_position;
-- ----------------------------------------------------------------------------
-- STEP 1 — the migration, as one atomic transaction.
-- ----------------------------------------------------------------------------
BEGIN;
SET search_path TO shipp;
-- Preserve the existing values before dropping the columns — this is
-- what makes the rollback below actually restorable, not just structural.
CREATE TABLE IF NOT EXISTS shipp.saved_items_match_data_backup AS
SELECT saved_item_id,
    match_score,
    match_reason,
    now() AS backed_up_at
FROM shipp.saved_items;
COMMENT ON TABLE shipp.saved_items_match_data_backup IS 'Pre-migration snapshot of saved_items.match_score/match_reason before removal in Issue #9. Safe to drop once gold_candidate_matches is confirmed as the sole source of truth.';
ALTER TABLE shipp.saved_items DROP COLUMN IF EXISTS match_score;
ALTER TABLE shipp.saved_items DROP COLUMN IF EXISTS match_reason;
COMMIT;
-- To dry-run instead: replace COMMIT with ROLLBACK, inspect the backup
-- table row count from Step 2, then re-run with COMMIT.
-- ----------------------------------------------------------------------------
-- STEP 2 — verification (safe to run standalone, read-only)
-- ----------------------------------------------------------------------------
-- Confirms the columns are actually gone.
SELECT column_name
FROM information_schema.columns
WHERE table_schema = 'shipp'
    AND table_name = 'saved_items';
-- Confirms the backup captured every row (should match saved_items' row
-- count at migration time).
SELECT COUNT(*)
FROM shipp.saved_items_match_data_backup;
-- Confirms gold_candidate_matches actually carries the join keys needed
-- to replace what was just removed — run this against your Gold layer,
-- not Lakebase, to confirm the read-time join will work:
-- SELECT listing_id, request_id, match_score, match_reason
--   FROM gold_candidate_matches
--   WHERE listing_id = '<some listing_id from saved_items>'
--     AND request_id = '<some request_id from saved_items>';
-- ----------------------------------------------------------------------------
-- ALTERNATIVE (Option B) — only use instead of Step 1 above if the team
-- decides a frozen point-in-time snapshot is genuinely wanted rather than
-- always reading the live Gold value:
-- ----------------------------------------------------------------------------
-- BEGIN;
-- ALTER TABLE shipp.saved_items RENAME COLUMN match_score TO match_score_at_save;
-- ALTER TABLE shipp.saved_items RENAME COLUMN match_reason TO match_reason_at_save;
-- COMMENT ON COLUMN shipp.saved_items.match_score_at_save IS
--     'Frozen snapshot at save() time — NOT live. Query gold_candidate_matches for current score. Issue #9, Option B.';
-- COMMIT;
-- ----------------------------------------------------------------------------
-- ROLLBACK SCRIPT — restores columns AND the data, using the backup table
-- ----------------------------------------------------------------------------
-- BEGIN;
-- ALTER TABLE shipp.saved_items ADD COLUMN match_score FLOAT;
-- ALTER TABLE shipp.saved_items ADD COLUMN match_reason VARCHAR(255);
-- UPDATE shipp.saved_items si
--   SET match_score = b.match_score, match_reason = b.match_reason
--   FROM shipp.saved_items_match_data_backup b
--   WHERE si.saved_item_id = b.saved_item_id;
-- COMMIT;
-- ----------------------------------------------------------------------------
-- STILL OPEN AFTER THIS MIGRATION
-- ----------------------------------------------------------------------------
-- 1. Update the Databricks App / agent code that currently displays
--    "why this was recommended" to join gold_candidate_matches instead
--    of reading saved_items.match_score/match_reason directly.
-- 2. Update shipp-marketplace-spec_V2.md §6.1 to remove match_score/
--    match_reason from the saved_items entity description.
-- 3. Once you've confirmed the app-code change works end to end, the
--    saved_items_match_data_backup table can be dropped — it's a
--    temporary safety net, not a permanent fixture.
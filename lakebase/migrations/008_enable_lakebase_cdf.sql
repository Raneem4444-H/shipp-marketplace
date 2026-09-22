-- ============================================================================
-- Migration: 008_enable_lakebase_cdf.sql
-- Resolves: GitHub #5 ("After the SQL setup, COMPLETE THIS CDC/CDF") — PARTIAL
-- Depends on: 001_init_lakebase_schema.sql having already run
-- Platform: Databricks Lakebase (PostgreSQL-compatible)
--
-- IMPORTANT: this migration only covers the SQL-executable half of enabling
-- Lakebase CDF. Confirmed against current Databricks documentation
-- (docs.databricks.com/aws/en/oltp/projects/lakebase-cdf), the full setup
-- is TWO steps, and only the first is SQL:
--
--   Step 1 (SQL, this file): set REPLICA IDENTITY FULL on every table you
--     want in the feed. Postgres needs full row data in the write-ahead
--     log for CDF to capture both old and new row state on every change.
--
--   Step 2 (NOT SQL — workspace UI, not covered by this file): a workspace
--     admin must first enable the Lakebase CDF preview from the workspace
--     Previews page. Then, from the Lakebase project's production branch,
--     open Branch Overview -> Lakebase CDF tab -> Start, choose
--     'bootcamp_shipp' as the source schema (every table in the schema is
--     included automatically — no per-table picker), and choose the
--     destination Unity Catalog catalog/schema for the resulting
--     lb_<table_name>_history Delta tables.
--
-- This resolves spec's own open question #1 (§12.4): "Is Lakebase CDF
-- available in the bootcamp workspace?" — the answer is: it's a Public
-- Preview feature, so this must be checked/enabled per-workspace first,
-- before Step 2 above can even be attempted.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- STEP 0 — confirm current REPLICA IDENTITY setting before changing anything.
-- 'd' = default (primary key only), 'f' = full, 'n' = nothing, 'i' = index.
-- ----------------------------------------------------------------------------
SET search_path TO bootcamp_shipp;

SELECT relname AS table_name,
       CASE relreplident
           WHEN 'd' THEN 'default (primary key only)'
           WHEN 'f' THEN 'full'
           WHEN 'n' THEN 'nothing'
           WHEN 'i' THEN 'index'
       END AS replica_identity
FROM pg_class
WHERE relnamespace = 'bootcamp_shipp'::regnamespace AND relkind = 'r'
ORDER BY relname;


-- ----------------------------------------------------------------------------
-- STEP 1 — set REPLICA IDENTITY FULL on all 8 Shipp tables.
-- This is metadata-only (no data rewrite, near-instant), but still run as
-- one transaction for a clean all-or-nothing result.
-- ----------------------------------------------------------------------------
BEGIN;

SET search_path TO bootcamp_shipp;

ALTER TABLE bootcamp_shipp.roles           REPLICA IDENTITY FULL;
ALTER TABLE bootcamp_shipp.users           REPLICA IDENTITY FULL;
ALTER TABLE bootcamp_shipp.user_roles      REPLICA IDENTITY FULL;
ALTER TABLE bootcamp_shipp.listings        REPLICA IDENTITY FULL;
ALTER TABLE bootcamp_shipp.listing_files   REPLICA IDENTITY FULL;
ALTER TABLE bootcamp_shipp.requests        REPLICA IDENTITY FULL;
ALTER TABLE bootcamp_shipp.saved_items     REPLICA IDENTITY FULL;
ALTER TABLE bootcamp_shipp.agent_activity  REPLICA IDENTITY FULL;

COMMIT;


-- ----------------------------------------------------------------------------
-- STEP 2 — verification (safe to run standalone, read-only)
-- All 8 rows should now show 'full'.
-- ----------------------------------------------------------------------------
SELECT relname AS table_name,
       CASE relreplident WHEN 'f' THEN 'full' ELSE 'NOT full — check this table' END AS replica_identity
FROM pg_class
WHERE relnamespace = 'bootcamp_shipp'::regnamespace AND relkind = 'r'
ORDER BY relname;


-- ----------------------------------------------------------------------------
-- STILL OPEN AFTER THIS MIGRATION — this issue is NOT fully closable by SQL
-- ----------------------------------------------------------------------------
-- 1. A workspace admin must confirm the Lakebase CDF Public Preview is
--    enabled for your bootcamp workspace (Previews page) — this may or may
--    not be available depending on your bootcamp's Databricks tier/access.
--    If it isn't available, spec §12.4's fallback question applies: what
--    ingestion approach replaces CDF (e.g. polling + Auto Loader on an
--    export, or a scheduled full/incremental extract job)?
-- 2. Once confirmed available: start the feed via Branch Overview ->
--    Lakebase CDF tab -> Start, source schema 'bootcamp_shipp', choosing
--    the destination Bronze catalog/schema.
-- 3. Confirm the resulting lb_<table>_history Delta tables actually appear
--    and populate on a test write (insert/update a row in Lakebase, check
--    the history table ~15 seconds later — CDF batches on that interval).
-- 4. This closes the SQL portion of GitHub #5. The Bronze ingestion job
--    that consumes these history tables is separate downstream work, not
--    part of this migration.

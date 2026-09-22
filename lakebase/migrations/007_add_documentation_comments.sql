-- ============================================================================
-- Migration: 007_add_documentation_comments.sql
-- Resolves: GitHub #7 (Issue #2 — roles PK rationale)
--           GitHub #8 (Issue #4 — idx_users_city rationale)
--           GitHub #9 (Issue #5 — user_roles FK cascade rationale)
-- Depends on: 001_init_lakebase_schema.sql having already run
-- Platform: Databricks Lakebase (PostgreSQL-compatible)
--
-- This is a documentation-only migration — no ALTER, no data touched.
-- Written as a separate file rather than a patch to 001 because 001 is
-- treated as already-run against a real environment (migration policy:
-- never edit a migration once it's touched real data).
-- ============================================================================
SET search_path TO shipp;
-- ----------------------------------------------------------------------------
-- GitHub #7 / Issue #2 — roles.role_id PK rationale
-- Decision on record: keep role_id as surrogate PK (no structural change).
-- If the team later chooses Option B (role_name as PK instead), that is a
-- real structural migration — see Issue #2's original write-up, not this file.
-- ----------------------------------------------------------------------------
COMMENT ON COLUMN shipp.roles.role_id IS 'Surrogate PK, kept for FK flexibility in user_roles even though role_name is already UNIQUE + CHECK-constrained to a fixed 3-value enum. Decision: GitHub #7.';
-- ----------------------------------------------------------------------------
-- GitHub #8 / Issue #4 — idx_users_city rationale
-- ----------------------------------------------------------------------------
COMMENT ON INDEX shipp.idx_users_city IS 'Supports location-based matching filter (BN-03/BN-06): WHERE current_city = ?. GitHub #8.';
-- ----------------------------------------------------------------------------
-- GitHub #9 / Issue #5 — user_roles FK cascade asymmetry rationale
-- Postgres has no COMMENT ON CONSTRAINT that surfaces in \d+ output the way
-- column/index comments do, so the rationale lives here in the migration
-- file itself, not as an executable statement.
--
--   FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
--     -> a role assignment for a deleted user is meaningless, so it cascades.
--   FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE RESTRICT
--     -> prevents deleting a foundational role (e.g. DONOR) while users
--        still hold it — protects against silently orphaning role mappings.
--
-- GitHub #9. No SQL statement to run for this one.
-- ----------------------------------------------------------------------------
-- ----------------------------------------------------------------------------
-- VERIFICATION — confirm all three comments landed
-- ----------------------------------------------------------------------------
SELECT col_description('shipp.roles'::regclass::oid, 1) AS role_id_comment;
-- ordinal position 1 = role_id, per the CREATE TABLE column order in 001
SELECT indexrelid::regclass AS index_name,
    obj_description(indexrelid, 'pg_class') AS comment
FROM pg_index
WHERE indexrelid = 'shipp.idx_users_city'::regclass;
-- ----------------------------------------------------------------------------
-- STILL OPEN AFTER THIS MIGRATION
-- ----------------------------------------------------------------------------
-- With 001–007 all applied, every issue from the original 12-issue schema
-- review has either a migration or a documentation fix on record. Remaining
-- work is outside this review's scope — see 008 and the Gate 01 validation
-- script below for what's next.
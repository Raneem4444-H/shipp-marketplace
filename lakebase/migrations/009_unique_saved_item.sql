-- ============================================================================
-- Migration: 009_unique_saved_item.sql
-- Resolves: spec §10.3 "save_item() must prevent duplicate Saved Items for the
--           same user, Request and Listing" — enforced in the database, not only
--           in agent code, so a retried tool call can never create a second row.
-- Depends on: 001-008
-- Platform: Databricks Lakebase (PostgreSQL-compatible)
-- ============================================================================

-- STEP 0 — read-only: any existing duplicates? Must return 0 rows before STEP 1.
SELECT user_id, request_id, listing_id, COUNT(*) AS copies
FROM shipp.saved_items
GROUP BY user_id, request_id, listing_id
HAVING COUNT(*) > 1;

-- STEP 1 — add the constraint (fails safely inside the transaction if duplicates exist)
BEGIN;
SET search_path TO shipp;
ALTER TABLE shipp.saved_items
    ADD CONSTRAINT uk_saved_item_user_request_listing UNIQUE (user_id, request_id, listing_id);
COMMENT ON CONSTRAINT uk_saved_item_user_request_listing ON shipp.saved_items IS
    'Spec §10.3: one saved row per (user, request, listing). save_item() uses INSERT ... ON CONFLICT DO NOTHING.';
COMMIT;

-- STEP 2 — verification
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'shipp.saved_items'::regclass AND contype = 'u';

-- save_item() pattern for the Agent (idempotent):
-- INSERT INTO shipp.saved_items (saved_item_id, user_id, request_id, listing_id, status)
-- VALUES (:id, :user_id, :request_id, :listing_id, 'SAVED')
-- ON CONFLICT (user_id, request_id, listing_id) DO NOTHING
-- RETURNING saved_item_id;

-- ROLLBACK:
-- ALTER TABLE shipp.saved_items DROP CONSTRAINT IF EXISTS uk_saved_item_user_request_listing;

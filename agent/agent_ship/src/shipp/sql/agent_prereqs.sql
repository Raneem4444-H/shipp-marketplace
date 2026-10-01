-- Lakebase prerequisites for the Shipp agent.
-- Run once, after shipp_schema_fixes_migration.sql. Review each block first.

-- 1. Duplicate-save prevention (spec §10.3).
--    save_item() relies on this constraint for ON CONFLICT ... DO NOTHING.
--    Skip if the migration already created an equivalent unique constraint.
ALTER TABLE bootcamp_shipp.saved_items
    ADD CONSTRAINT uq_saved_items_user_request_listing
    UNIQUE (user_id, request_id, listing_id);

-- 2. agent_activity reads for analytics and the demo audit view.
CREATE INDEX IF NOT EXISTS ix_agent_activity_user_created
    ON bootcamp_shipp.agent_activity (user_id, created_at);

-- 3. Least privilege for the App's service principal role (spec §9.2).
--    The agent only reads listings/requests and only inserts into its two tables.
--    Replace <app_sp_role> with the Postgres role Databricks created for the app.
--    The app's own listing/request forms need separate INSERT/UPDATE grants.
GRANT USAGE ON SCHEMA bootcamp_shipp TO "<app_sp_role>";
GRANT SELECT ON bootcamp_shipp.listings, bootcamp_shipp.requests TO "<app_sp_role>";
GRANT SELECT, INSERT ON bootcamp_shipp.saved_items, bootcamp_shipp.agent_activity
    TO "<app_sp_role>";

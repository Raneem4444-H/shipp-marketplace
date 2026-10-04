-- ============================================================================
-- Migration: 010_agent_activity_action_status.sql
-- Purpose: Align shipp.agent_activity.action_status with the canonical
--          ActionStatus enum used by agent/agent_ship/src/shipp/agent/contracts.py.
--
-- Canonical values:
--   SUCCESS
--   NO_MATCH
--   NOT_FOUND
--   REJECTED_UNAVAILABLE
--   REJECTED_DUPLICATE
--   REJECTED_NOT_A_MATCH
--   REJECTED_NOT_OWNER
--   REJECTED_REQUEST_CLOSED
--   ERROR
--
-- Safety:
-- - Existing action_status CHECK constraints are replaced dynamically.
-- - The new CHECK is added NOT VALID first. PostgreSQL enforces it for all new
--   writes immediately while preserving any legacy history that does not yet
--   use the canonical vocabulary.
-- - If all historical rows already use canonical values, the constraint is
--   validated automatically in this migration.
-- ============================================================================

BEGIN;

SET search_path TO shipp;

-- Remove only CHECK constraints on agent_activity that reference action_status.
-- This avoids assuming an environment-specific constraint name.
DO $$
DECLARE
    constraint_row record;
BEGIN
    FOR constraint_row IN
        SELECT c.conname
        FROM pg_constraint AS c
        WHERE c.conrelid = 'shipp.agent_activity'::regclass
          AND c.contype = 'c'
          AND pg_get_constraintdef(c.oid) ILIKE '%action_status%'
    LOOP
        EXECUTE format(
            'ALTER TABLE shipp.agent_activity DROP CONSTRAINT %I',
            constraint_row.conname
        );
    END LOOP;
END
$$;

ALTER TABLE shipp.agent_activity
    ADD CONSTRAINT ck_agent_activity_action_status
    CHECK (
        action_status IN (
            'SUCCESS',
            'NO_MATCH',
            'NOT_FOUND',
            'REJECTED_UNAVAILABLE',
            'REJECTED_DUPLICATE',
            'REJECTED_NOT_A_MATCH',
            'REJECTED_NOT_OWNER',
            'REJECTED_REQUEST_CLOSED',
            'ERROR'
        )
    )
    NOT VALID;

-- Validate immediately only when historical rows are already canonical.
DO $$
DECLARE
    invalid_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO invalid_count
    FROM shipp.agent_activity
    WHERE action_status IS NULL
       OR action_status NOT IN (
            'SUCCESS',
            'NO_MATCH',
            'NOT_FOUND',
            'REJECTED_UNAVAILABLE',
            'REJECTED_DUPLICATE',
            'REJECTED_NOT_A_MATCH',
            'REJECTED_NOT_OWNER',
            'REJECTED_REQUEST_CLOSED',
            'ERROR'
       );

    IF invalid_count = 0 THEN
        ALTER TABLE shipp.agent_activity
            VALIDATE CONSTRAINT ck_agent_activity_action_status;
    ELSE
        RAISE NOTICE
            'ck_agent_activity_action_status left NOT VALID because % legacy row(s) use non-canonical statuses. New writes are still protected.',
            invalid_count;
    END IF;
END
$$;

COMMIT;

-- --------------------------------------------------------------------------
-- Verification
-- --------------------------------------------------------------------------
SELECT
    conname,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'shipp.agent_activity'::regclass
  AND conname = 'ck_agent_activity_action_status';

SELECT
    action_status,
    COUNT(*) AS row_count
FROM shipp.agent_activity
GROUP BY action_status
ORDER BY action_status;

-- Rollback (if needed):
-- ALTER TABLE shipp.agent_activity
--   DROP CONSTRAINT IF EXISTS ck_agent_activity_action_status;

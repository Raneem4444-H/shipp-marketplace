-- ============================================================================
-- SHIPP P0 deterministic demo seed
-- File: lakebase/seeds/001_demo_data.sql
-- Purpose:
--   Create the smallest reproducible operational dataset required by the
--   SHIPP end-to-end demo.
--
-- Demo story:
--   demo-donor-001
--      ├── demo-listing-001
--      └── demo-listing-002
--
--   demo-requester-001
--      └── demo-request-001
--
-- Required starting state:
--   - 2 AVAILABLE listings
--   - 1 OPEN request
--   - same compatible category
--   - valid coordinates
--   - no existing saved_item for this demo request
--
-- Platform: Databricks Lakebase / PostgreSQL-compatible
-- Depends on migrations 001-008 having been applied.
-- ============================================================================

BEGIN;

SET search_path TO shipp;

-- ----------------------------------------------------------------------------
-- 1. Canonical roles
-- ----------------------------------------------------------------------------
INSERT INTO shipp.roles (role_id, role_name)
VALUES
    ('DONOR', 'DONOR'),
    ('REQUESTER', 'REQUESTER')
ON CONFLICT (role_id) DO UPDATE
SET role_name = EXCLUDED.role_name
WHERE shipp.roles.role_name IS DISTINCT FROM EXCLUDED.role_name;

-- ----------------------------------------------------------------------------
-- 2. Demo users
-- ----------------------------------------------------------------------------
INSERT INTO shipp.users (
    user_id,
    name,
    current_city,
    created_at,
    updated_at,
    is_active
)
VALUES
    (
        'demo-donor-001',
        'Demo Donor',
        'Abu Dhabi',
        TIMESTAMP '2026-09-26 00:00:00',
        TIMESTAMP '2026-09-26 00:00:00',
        TRUE
    ),
    (
        'demo-requester-001',
        'Demo Requester',
        'Abu Dhabi',
        TIMESTAMP '2026-09-26 00:00:00',
        TIMESTAMP '2026-09-26 00:00:00',
        TRUE
    )
ON CONFLICT (user_id) DO UPDATE
SET
    name = EXCLUDED.name,
    current_city = EXCLUDED.current_city,
    updated_at = EXCLUDED.updated_at,
    is_active = EXCLUDED.is_active
WHERE (
    shipp.users.name,
    shipp.users.current_city,
    shipp.users.updated_at,
    shipp.users.is_active
) IS DISTINCT FROM (
    EXCLUDED.name,
    EXCLUDED.current_city,
    EXCLUDED.updated_at,
    EXCLUDED.is_active
);

-- ----------------------------------------------------------------------------
-- 3. User-role assignments
-- ----------------------------------------------------------------------------
INSERT INTO shipp.user_roles (
    user_id,
    role_id,
    assigned_at,
    assigned_by
)
VALUES
    (
        'demo-donor-001',
        'DONOR',
        TIMESTAMP '2026-09-26 00:00:00',
        NULL
    ),
    (
        'demo-requester-001',
        'REQUESTER',
        TIMESTAMP '2026-09-26 00:00:00',
        NULL
    )
ON CONFLICT (user_id, role_id) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 4. Demo listings
--    Coordinates are real Abu Dhabi coordinates so ORS route enrichment can
--    be tested later without replacing the seed data.
-- ----------------------------------------------------------------------------
INSERT INTO shipp.listings (
    listing_id,
    donor_id,
    title,
    description,
    category,
    condition,
    location,
    latitude,
    longitude,
    available_from,
    available_until,
    status,
    created_at,
    updated_at
)
VALUES
    (
        'demo-listing-001',
        'demo-donor-001',
        'Wooden Dining Table',
        'Solid wooden dining table available for a household that needs it.',
        'FURNITURE',
        'GOOD',
        'Al Reem Island, Abu Dhabi',
        24.4976,
        54.4075,
        TIMESTAMP '2026-09-25 00:00:00',
        TIMESTAMP '2026-10-15 23:59:59',
        'AVAILABLE',
        TIMESTAMP '2026-09-26 00:00:00',
        TIMESTAMP '2026-09-26 00:00:00'
    ),
    (
        'demo-listing-002',
        'demo-donor-001',
        'Four-Seater Dining Table',
        'Compact four-seat dining table suitable for a small apartment.',
        'FURNITURE',
        'GOOD',
        'Al Khalidiyah, Abu Dhabi',
        24.4699,
        54.3526,
        TIMESTAMP '2026-09-25 00:00:00',
        TIMESTAMP '2026-10-15 23:59:59',
        'AVAILABLE',
        TIMESTAMP '2026-09-26 00:00:00',
        TIMESTAMP '2026-09-26 00:00:00'
    )
ON CONFLICT (listing_id) DO UPDATE
SET
    donor_id = EXCLUDED.donor_id,
    title = EXCLUDED.title,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    condition = EXCLUDED.condition,
    location = EXCLUDED.location,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    available_from = EXCLUDED.available_from,
    available_until = EXCLUDED.available_until,
    status = EXCLUDED.status,
    updated_at = EXCLUDED.updated_at
WHERE (
    shipp.listings.donor_id,
    shipp.listings.title,
    shipp.listings.description,
    shipp.listings.category,
    shipp.listings.condition,
    shipp.listings.location,
    shipp.listings.latitude,
    shipp.listings.longitude,
    shipp.listings.available_from,
    shipp.listings.available_until,
    shipp.listings.status,
    shipp.listings.updated_at
) IS DISTINCT FROM (
    EXCLUDED.donor_id,
    EXCLUDED.title,
    EXCLUDED.description,
    EXCLUDED.category,
    EXCLUDED.condition,
    EXCLUDED.location,
    EXCLUDED.latitude,
    EXCLUDED.longitude,
    EXCLUDED.available_from,
    EXCLUDED.available_until,
    EXCLUDED.status,
    EXCLUDED.updated_at
);

-- ----------------------------------------------------------------------------
-- 5. Demo request
-- ----------------------------------------------------------------------------
INSERT INTO shipp.requests (
    request_id,
    requester_id,
    request_text,
    category,
    location,
    latitude,
    longitude,
    need_by_date,
    status,
    created_at,
    updated_at
)
VALUES (
    'demo-request-001',
    'demo-requester-001',
    'Need a dining table for a new apartment before move-in.',
    'FURNITURE',
    'Al Maryah Island, Abu Dhabi',
    24.5014,
    54.3872,
    TIMESTAMP '2026-10-05 18:00:00',
    'OPEN',
    TIMESTAMP '2026-09-26 00:00:00',
    TIMESTAMP '2026-09-26 00:00:00'
)
ON CONFLICT (request_id) DO UPDATE
SET
    requester_id = EXCLUDED.requester_id,
    request_text = EXCLUDED.request_text,
    category = EXCLUDED.category,
    location = EXCLUDED.location,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    need_by_date = EXCLUDED.need_by_date,
    status = EXCLUDED.status,
    updated_at = EXCLUDED.updated_at
WHERE (
    shipp.requests.requester_id,
    shipp.requests.request_text,
    shipp.requests.category,
    shipp.requests.location,
    shipp.requests.latitude,
    shipp.requests.longitude,
    shipp.requests.need_by_date,
    shipp.requests.status,
    shipp.requests.updated_at
) IS DISTINCT FROM (
    EXCLUDED.requester_id,
    EXCLUDED.request_text,
    EXCLUDED.category,
    EXCLUDED.location,
    EXCLUDED.latitude,
    EXCLUDED.longitude,
    EXCLUDED.need_by_date,
    EXCLUDED.status,
    EXCLUDED.updated_at
);

-- ----------------------------------------------------------------------------
-- 6. Reset only the P0 demo save state.
--    This intentionally removes prior save actions for the deterministic demo
--    pair so the agent can demonstrate save_item() from a clean starting state.
-- ----------------------------------------------------------------------------
DELETE FROM shipp.saved_items
WHERE request_id = 'demo-request-001'
  AND listing_id IN ('demo-listing-001', 'demo-listing-002');

COMMIT;

-- ----------------------------------------------------------------------------
-- Quick verification
-- ----------------------------------------------------------------------------
SELECT user_id, name, current_city, is_active
FROM shipp.users
WHERE user_id IN ('demo-donor-001', 'demo-requester-001')
ORDER BY user_id;

SELECT
    listing_id,
    donor_id,
    title,
    category,
    status,
    latitude,
    longitude,
    available_from,
    available_until
FROM shipp.listings
WHERE listing_id IN ('demo-listing-001', 'demo-listing-002')
ORDER BY listing_id;

SELECT
    request_id,
    requester_id,
    request_text,
    category,
    status,
    latitude,
    longitude,
    need_by_date
FROM shipp.requests
WHERE request_id = 'demo-request-001';

SELECT COUNT(*) AS demo_saved_item_count
FROM shipp.saved_items
WHERE request_id = 'demo-request-001'
  AND listing_id IN ('demo-listing-001', 'demo-listing-002');

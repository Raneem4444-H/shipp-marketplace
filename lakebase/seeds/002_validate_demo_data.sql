-- ============================================================================
-- SHIPP P0 demo seed validation
-- File: lakebase/seeds/002_validate_demo_data.sql
-- Purpose:
--   Prove the deterministic demo dataset is ready for downstream CDF,
--   Bronze, Silver, ORS, Gold, Agent, and App integration.
-- ============================================================================

SET search_path TO shipp;

-- 1. Expected users: exactly 2.
SELECT COUNT(*) AS demo_user_count
FROM shipp.users
WHERE user_id IN ('demo-donor-001', 'demo-requester-001');

-- 2. Expected listings: exactly 2 and both AVAILABLE.
SELECT
    listing_id,
    donor_id,
    category,
    status,
    latitude,
    longitude,
    available_from,
    available_until
FROM shipp.listings
WHERE listing_id IN ('demo-listing-001', 'demo-listing-002')
ORDER BY listing_id;

-- 3. Expected request: exactly 1 and OPEN.
SELECT
    request_id,
    requester_id,
    category,
    status,
    latitude,
    longitude,
    need_by_date
FROM shipp.requests
WHERE request_id = 'demo-request-001';

-- 4. Category contract: request and listings must share FURNITURE.
SELECT
    r.request_id,
    r.category AS request_category,
    l.listing_id,
    l.category AS listing_category,
    (r.category = l.category) AS category_compatible
FROM shipp.requests r
CROSS JOIN shipp.listings l
WHERE r.request_id = 'demo-request-001'
  AND l.listing_id IN ('demo-listing-001', 'demo-listing-002')
ORDER BY l.listing_id;

-- 5. Coordinate contract: values must fall inside valid latitude/longitude ranges.
SELECT
    listing_id AS entity_id,
    'listing' AS entity_type,
    latitude,
    longitude,
    (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180) AS coordinates_valid
FROM shipp.listings
WHERE listing_id IN ('demo-listing-001', 'demo-listing-002')

UNION ALL

SELECT
    request_id AS entity_id,
    'request' AS entity_type,
    latitude,
    longitude,
    (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180) AS coordinates_valid
FROM shipp.requests
WHERE request_id = 'demo-request-001';

-- 6. Availability contract: each listing must be available by the request need date.
SELECT
    l.listing_id,
    l.status,
    l.available_from,
    l.available_until,
    r.need_by_date,
    (
        l.status = 'AVAILABLE'
        AND l.available_from <= r.need_by_date
        AND l.available_until >= r.need_by_date
    ) AS availability_compatible
FROM shipp.listings l
JOIN shipp.requests r
  ON r.request_id = 'demo-request-001'
WHERE l.listing_id IN ('demo-listing-001', 'demo-listing-002')
ORDER BY l.listing_id;

-- 7. Clean starting point for the save_item() demo: expected count = 0.
SELECT COUNT(*) AS demo_saved_item_count
FROM shipp.saved_items
WHERE request_id = 'demo-request-001'
  AND listing_id IN ('demo-listing-001', 'demo-listing-002');

-- 8. Compact acceptance-gate summary.
WITH counts AS (
    SELECT
        (SELECT COUNT(*)
         FROM shipp.users
         WHERE user_id IN ('demo-donor-001', 'demo-requester-001')) AS user_count,

        (SELECT COUNT(*)
         FROM shipp.listings
         WHERE listing_id IN ('demo-listing-001', 'demo-listing-002')
           AND status = 'AVAILABLE') AS available_listing_count,

        (SELECT COUNT(*)
         FROM shipp.requests
         WHERE request_id = 'demo-request-001'
           AND status = 'OPEN') AS open_request_count,

        (SELECT COUNT(*)
         FROM shipp.saved_items
         WHERE request_id = 'demo-request-001'
           AND listing_id IN ('demo-listing-001', 'demo-listing-002')) AS saved_item_count
)
SELECT
    user_count,
    available_listing_count,
    open_request_count,
    saved_item_count,
    (
        user_count = 2
        AND available_listing_count = 2
        AND open_request_count = 1
        AND saved_item_count = 0
    ) AS demo_seed_ready
FROM counts;

-- ============================================================================
-- Seed: 003_demo_listing_files.sql
-- Purpose: link each demo Listing to one real image in the Unity Catalog Volume
--          bootcamp_students.shipp_bronze.listing_images (spec §6.2).
--          Lakebase stores ONLY the path; the image itself lives in the Volume.
-- Depends on: 001_demo_data.sql (demo-listing-001, demo-listing-002 must exist)
-- Idempotent: rerunning changes nothing unless a value actually differs, so it
--             does not create fake CDC update events.
-- Platform: Databricks Lakebase (PostgreSQL) — run in the Lakebase query editor.
-- ============================================================================
BEGIN;
SET search_path TO shipp;
INSERT INTO shipp.listing_files (
        listing_file_id,
        listing_id,
        file_path,
        file_type,
        file_size,
        uploaded_at
    )
VALUES (
        'demo-file-001',
        'demo-listing-001',
        '/Volumes/bootcamp_students/shipp_bronze/listing_images/demo-listing-001/cover.jpg',
        'image/jpeg',
        NULL,
        CURRENT_TIMESTAMP
    ),
    (
        'demo-file-002',
        'demo-listing-002',
        '/Volumes/bootcamp_students/shipp_bronze/listing_images/demo-listing-002/cover.jpg',
        'image/jpeg',
        NULL,
        CURRENT_TIMESTAMP
    ) ON CONFLICT (listing_file_id) DO
UPDATE
SET listing_id = EXCLUDED.listing_id,
    file_path = EXCLUDED.file_path,
    file_type = EXCLUDED.file_type
WHERE (
        shipp.listing_files.listing_id,
        shipp.listing_files.file_path,
        shipp.listing_files.file_type
    ) IS DISTINCT
FROM (
        EXCLUDED.listing_id,
        EXCLUDED.file_path,
        EXCLUDED.file_type
    );
COMMIT;
-- Verification: expect 2 rows, both paths under /Volumes/bootcamp_students/shipp_bronze/listing_images/
SELECT lf.listing_file_id,
    lf.listing_id,
    l.title,
    lf.file_path,
    lf.file_type
FROM shipp.listing_files lf
    JOIN shipp.listings l ON l.listing_id = lf.listing_id
WHERE lf.listing_id LIKE 'demo-%'
ORDER BY lf.listing_file_id;
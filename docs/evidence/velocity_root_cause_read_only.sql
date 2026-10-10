-- SHIPP: READ-ONLY grading / Velocity root-cause diagnostics.
-- Source: existing SHIPP Delta pipeline tables in the course Databricks workspace.
-- Run as separate statements in Databricks SQL; do not change source records.
-- DO NOT modify the < 60s threshold, delete misses, or manually insert PASS rows.
-- A historical latency measurement is not evidence of current runtime performance.
--
-- Observed supplied snapshot, 2026-10-10:
-- Task 92: 39/39 PASS, 78 Gold matches, 38 searchable documents.
-- Task 93: 26/27 PASS; only velocity_under_60_seconds FAIL.
-- Recorded best latency: 279783.489914 s (~77.7 h).
-- This is event-to-retrieval elapsed time, not necessarily Spark execution time.

-- 1. All real measurements: keep FAIL rows and inspect entity event freshness.
SELECT entity_type, entity_id, operational_change_at, silver_at, gold_at,
       retrieval_available_at, latency_seconds, slo_met,
       timestampdiff(SECOND, silver_at, gold_at) AS silver_to_gold_seconds,
       timestampdiff(SECOND, operational_change_at, silver_at) AS event_to_silver_seconds
FROM bootcamp_students.shipp_gold.velocity_measurements
ORDER BY operational_change_at DESC
LIMIT 50;

-- 2. Pipeline stage execution history. Do not infer per-entity lineage from timestamps alone.
SELECT run_id, stage, started_at, ended_at, seconds, status, summary
FROM bootcamp_students.shipp_gold.pipeline_run_log
ORDER BY started_at DESC
LIMIT 100;

-- 3. Which stages dominate wall time in recent successful runs?
SELECT stage, count(*) AS run_count,
       round(percentile_approx(seconds, 0.5), 2) AS median_stage_seconds,
       round(max(seconds), 2) AS slowest_stage_seconds,
       round(avg(seconds), 2) AS mean_stage_seconds
FROM bootcamp_students.shipp_gold.pipeline_run_log
WHERE status = 'PASS'
  AND started_at >= current_timestamp() - INTERVAL 7 DAYS
GROUP BY stage
ORDER BY median_stage_seconds DESC, stage;

-- 4. Relate the latest recorded entity event to subsequent pipeline starts.
-- These are temporally adjacent candidates, NOT proof the stage processed that entity.
WITH last_event AS (
  SELECT entity_type, entity_id, operational_change_at,
         retrieval_available_at, latency_seconds, slo_met,
         row_number() OVER (
           ORDER BY operational_change_at DESC, retrieval_available_at DESC
         ) AS rn
  FROM bootcamp_students.shipp_gold.velocity_measurements
)
SELECT e.entity_type, e.entity_id, e.operational_change_at,
       e.retrieval_available_at, e.latency_seconds, e.slo_met,
       p.run_id, p.stage, p.started_at, p.ended_at, p.seconds, p.status,
       timestampdiff(SECOND, e.operational_change_at, p.started_at)
         AS seconds_event_to_stage_start
FROM last_event e
LEFT JOIN bootcamp_students.shipp_gold.pipeline_run_log p
  ON p.started_at >= e.operational_change_at
 AND p.started_at <= e.retrieval_available_at
WHERE e.rn = 1
ORDER BY p.started_at DESC
LIMIT 80;

-- 5. Judge the two-V claim honestly: these counts show SHIPP DATA,
-- not >1 million rows processed in one meaningful workload.
SELECT 'silver_listings' AS dataset, count(*) AS row_count
FROM bootcamp_students.shipp_silver.silver_listings
UNION ALL
SELECT 'silver_requests', count(*)
FROM bootcamp_students.shipp_silver.silver_requests
UNION ALL
SELECT 'gold_candidate_matches', count(*)
FROM bootcamp_students.shipp_gold.gold_candidate_matches
UNION ALL
SELECT 'gold_listing_search_docs', count(*)
FROM bootcamp_students.shipp_gold.gold_listing_search_docs
UNION ALL
SELECT 'bronze_vision_responses', count(*)
FROM bootcamp_students.shipp_bronze.vision_responses;

-- 6. Show current validated release runs: run-level, not all-time sums.
SELECT validation_run_id, max(checked_at) AS checked_at,
       sum(CASE WHEN check_status = 'PASS' THEN 1 ELSE 0 END) AS pass_count,
       sum(CASE WHEN check_status = 'FAIL' THEN 1 ELSE 0 END) AS fail_count
FROM bootcamp_students.shipp_gold.release_validation_log
GROUP BY validation_run_id
ORDER BY checked_at DESC
LIMIT 8;

SELECT validation_run_id, max(checked_at) AS checked_at,
       sum(CASE WHEN check_status = 'PASS' THEN 1 ELSE 0 END) AS pass_count,
       sum(CASE WHEN check_status = 'FAIL' THEN 1 ELSE 0 END) AS fail_count
FROM bootcamp_students.shipp_gold.deployed_e2e_validation_log
GROUP BY validation_run_id
ORDER BY checked_at DESC
LIMIT 8;

-- ACCEPTANCE:
-- (a) Create a NEW eligible Listing or Request in verified DEV, note its ID.
-- (b) Run the approved incremental processing and any required AI Search sync.
-- (c) Use notebooks/validation/09_validate_velocity.ipynb for THIS fresh ID.
-- (d) Capture operational_change_at, silver_at, gold_at,
--     retrieval_available_at, latency_seconds, slo_met, stage run IDs.
-- (e) If SLO fails, keep FAIL and compare source wait vs Spark work vs index sync.
--     Optimize only the bottleneck observed; DO NOT alter thresholds or fabricate scale.

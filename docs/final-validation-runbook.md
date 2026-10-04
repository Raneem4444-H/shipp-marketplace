# SHIPP Final Validation Runbook

This runbook closes the remaining P0 evidence without rebuilding validated components.

## 1. Deployment

1. Verify the Databricks App source points to the repository root.
2. Deploy the latest `main`.
3. Confirm the App is RUNNING and the URL opens.
4. Confirm the App service principal can access:
   - model serving endpoint;
   - SQL Warehouse;
   - `gold_candidate_matches`;
   - AI Search index;
   - Lakebase endpoint/schema/tables.

## 2. Agent READ evidence

Use a real `user_id` and `request_id`.

Expected tool path:

```text
Gold candidate matches
→ AI Search listing context
→ Lakebase current listing status
→ grounded recommendation
```

Capture the tool trace and the final real `listing_id`.

## 3. Final deployed save

Use a valid request/listing pair that has not already been saved for the same user/request/listing combination.

Record:

```text
user_id
request_id
listing_id
saved_item_id
save timestamp
```

## 4. Lakebase confirmation

Run against Lakebase PostgreSQL:

```sql
SELECT
    saved_item_id,
    user_id,
    request_id,
    listing_id,
    saved_at
FROM shipp.saved_items
WHERE saved_item_id = '<FINAL_SAVED_ITEM_ID>';
```

PASS: exactly one row with the expected IDs.

Audit:

```sql
SELECT
    activity_id,
    user_id,
    tool_name,
    entity_id,
    action_status,
    created_at
FROM shipp.agent_activity
WHERE entity_id = '<FINAL_LISTING_ID>'
ORDER BY created_at DESC;
```

PASS: the final action contains `tool_name = 'save_item'` and `action_status = 'SUCCESS'`.

## 5. CDC confirmation

Run in Databricks SQL / notebook:

```sql
SELECT *
FROM bootcamp_students.shipp_bronze.lb_saved_items_history
WHERE saved_item_id = '<FINAL_SAVED_ITEM_ID>'
ORDER BY _pg_lsn DESC, _sort_by DESC;
```

For Agent Activity, filter the final action by the known listing/entity ID and timestamp:

```sql
SELECT *
FROM bootcamp_students.shipp_bronze.lb_agent_activity_history
WHERE entity_id = '<FINAL_LISTING_ID>'
ORDER BY _pg_lsn DESC, _sort_by DESC;
```

Capture `_pg_change_type`, `_pg_lsn`, and `_sort_by`.

## 6. Analytics

Use only:

```text
notebooks/development/60_gold_marketplace_metrics.ipynb
```

Then query:

```sql
SELECT
    metric_key,
    saved_items_count,
    saved_requests_count,
    candidate_match_count,
    requests_with_matches,
    agent_action_count,
    agent_success_count,
    agent_rejected_duplicate_count,
    agent_rejected_unavailable_count,
    agent_success_rate,
    latest_operational_event_at
FROM bootcamp_students.shipp_gold.gold_marketplace_metrics
WHERE metric_key = 'marketplace_current';
```

Capture before/after and confirm a rerun does not double-count.

## 7. AI Search

Run one final semantic query and capture:

- query text;
- index name/status;
- returned `listing_id`;
- title;
- result score/context;
- expected listing match.

## 8. ORS failure evidence

Execute one controlled failing ORS case through the existing implementation.

Capture the Bronze row showing the final failed/error response. Confirm that downstream normalized route logic does not invent `distance_km` or `duration_min` for a failed/no-route result.

Do not weaken assertions and do not replace the existing ORS implementation.

## 9. Security

Run:

```text
notebooks/validation/16_validate_security.ipynb
```

PASS requires expected downstream tables to be checked and zero prohibited sensitive columns.

## 10. Velocity

Make one controlled eligible operational change, run the required pipeline, then run:

```text
notebooks/validation/09_validate_velocity.ipynb
```

Record:

```text
operational_change_at
silver_at
gold_at
retrieval_available_at
latency_seconds
slo_met
```

Keep SLO misses as evidence. Do not fabricate a sub-60-second result.

## 11. Evidence freeze

Capture screenshots/logs for:

1. deployment;
2. App permissions;
3. Agent READ trace;
4. AI Search;
5. deployed save;
6. Lakebase `saved_items`;
7. `agent_activity`;
8. Saved Items CDC;
9. Agent Activity CDC;
10. Analytics before/after;
11. ORS success/failure;
12. Vision/search content;
13. Velocity;
14. Security;
15. final commit SHA;
16. final CI result.

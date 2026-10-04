# SHIPP Task 92 — Release Validation

Task 92 is the final read-only gate after the existing Task 90 core pipeline and Task 91 RAG/Search pipeline.

## Job flow

```text
90 Core Pipeline
      ↓
91 RAG / Search Pipeline
      ↓
92 Release Validation
```

Task 92 does not rebuild Silver, Gold, RAG, requests, or categories.

## What it validates

- Silver listings and requests exist and are non-empty.
- Request IDs are unique and request categories are present.
- Gold request IDs trace back to Silver requests.
- Gold category matches the trusted request category.
- Route distance and duration are non-negative.
- Gold has no pending routes.
- Match scores are within 0–1.
- Gold request/listing pairs are unique.
- Search documents retain a unique `listing_id` and non-null `search_text`.
- Marketplace metrics and RAG evaluation evidence exist.
- Every expected Task 90/91 stage has a latest PASS result.

## Evidence log

Task 92 appends one row per check to:

```text
bootcamp_students.shipp_gold.release_validation_log
```

The log also records the current Silver request count and distinct request/listing categories.

The canonical request product remains:

```text
bootcamp_students.shipp_silver.silver_requests
```

Do not create a second request/category business table. Stage 11 already persists requests and category as part of the trusted Silver contract.

## Security

Do not store passwords, API keys, OAuth tokens, database passwords, or other credentials in Git or in the validation log.

## Databricks Job wiring

```text
Task name: 92-release-validation
Notebook: notebooks/pipeline/92_release_validation
Depends on: 91-pipeline
Compute: same Serverless configuration as 90/91
```

PASS means the notebook exits with:

```text
PASS — SHIPP release validation completed.
```

## Useful queries

```sql
SELECT *
FROM bootcamp_students.shipp_gold.release_validation_log
ORDER BY checked_at DESC, check_status, check_name;
```

```sql
SELECT request_id, requester_id, category, status, updated_at
FROM bootcamp_students.shipp_silver.silver_requests
ORDER BY updated_at DESC;
```

```sql
SELECT category, count(*) AS request_count
FROM bootcamp_students.shipp_silver.silver_requests
GROUP BY category
ORDER BY request_count DESC, category;
```

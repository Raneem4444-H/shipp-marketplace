# SHIPP RAG stage — images + text → AI Search → Agent READ tool

This folder turns every Listing's text and photo into trusted, searchable content, indexes it in
Databricks AI Search (Vector Search), and gives the Agent one read tool: `search_listing_context()`.
It covers runbook Stages 8 and 9 and the retrieval evaluation from spec §11.3.

```text
Lakebase listings + listing_files          image files in the UC Volume
        │ (CDC sync)                                │
        ▼                                           ▼
lb_listings_history, lb_listing_files_history ──► 50 silver_listing_files   (delete-aware + real file facts)
                                                    │
                                                    ▼
                                    51 vision endpoint ──► bronze vision_responses (raw JSON, append-only)
                                                    │
silver_listings ────────────────────────────────► 52 silver_listing_content (clean text + vision, PII redacted)
                                                    │
                                                    ▼
                                    53 gold_listing_search_docs (MERGE, CDF on, AVAILABLE only)
                                                    │
                                                    ▼
                                    54 AI Search Delta Sync index ──► search_listing_context()  → Agent
                                                    │                         │
                                                    ▼                         ▼
                                    55 retrieval eval (hit@K, MRR)   56 silver_semantic_scores → Gold v2
```

## Layout

| Path | What it is |
|---|---|
| `rag/text.py` | PII redaction + text cleaning, Python and Spark versions of the same regexes |
| `rag/vision.py` | Vision endpoint client (never raises, raw body kept, retry rules), prompt, output parser |
| `rag/content.py` | `silver_listing_files` and `silver_listing_content` transforms |
| `rag/search_docs.py` | `gold_listing_search_docs` transform + MERGE SQL |
| `rag/index.py` | Vector Search endpoint / Delta Sync index create-if-missing, sync, wait |
| `rag/retrieval.py` | **`search_listing_context()` — the Agent's READ tool** |
| `rag/semantic.py` | semantic score rows for Gold scoring v2 |
| `rag/evaluation.py`, `rag/eval/eval_set.json` | hit@K / MRR metrics and the labeled query set |
| `notebooks/rag/50–56` | the only writers of the RAG tables (thin orchestrators) |
| `notebooks/pipeline/91_run_rag_pipeline` | runs 50→56 and logs timings to `pipeline_run_log` |
| `tests/unit/test_rag_*.py` | unit tests (run in CI) |

Same rules as the rest of the repo: logic lives in `.py` files with tests, notebooks only orchestrate,
names come from `config/tables.py`, settings from `config/settings.py`, one writer per table.

## Contracts

| Table | Source | Grain / key | Writer | Consumer |
|---|---|---|---|---|
| `shipp_bronze.lb_listing_files_history` | Lakebase CDC sync | one CDC event | Lakebase sync | 50 |
| `shipp_silver.silver_listing_files` | files history + Volume | one current `listing_file_id` | 50 | 51, 52 |
| `shipp_bronze.vision_responses` | vision endpoint | one call (append-only) | 51 | 52 |
| `shipp_silver.silver_listing_content` | listings + files + vision | one current `listing_id` | 52 | 53 |
| `shipp_gold.gold_listing_search_docs` | listing content | one AVAILABLE `listing_id` | 53 (MERGE) | AI Search index |
| `shipp_gold.listing_search_index` | search docs (Delta Sync) | `listing_id` | 54 | Agent, 55, 56 |
| `shipp_gold.rag_eval_results` | eval runs | one case per run (append) | 55 | evidence |
| `shipp_silver.silver_semantic_scores` | index queries | (`request_id`, `listing_id`) | 56 | Gold v2 |

`vision_status` in Silver content: `OK` · `FAILED` · `PENDING` (not processed yet) · `NO_IMAGE` · `FILE_MISSING`.
Image description and labels are present **only** for `OK`. A listing without a usable image is still
searchable through its title, category, condition and description.

## Decisions (answers the proposal's "finalize the vision approach" revision)

- **Vision model:** one Databricks Model Serving chat endpoint with image input, set in `VISION_ENDPOINT`.
  Record the endpoint that actually ran in your README/demo — do not claim a model that did not run.
- **Output schema:** `{"image_description": str (≤ 60 words), "detected_labels": [3–10 lowercase str]}`.
  Anything else (prose, missing description, bad JSON) is stored as a FAILED row with the raw body kept.
- **Prompt versioning:** changing the prompt means bumping `VISION_PROMPT_VERSION`; every image is then reprocessed
  once, and old results stay in Bronze for comparison.
- **One primary image per listing** (existing file first, earliest upload, smallest id) — keeps quota and latency low.
- **Embeddings:** Databricks-managed, `EMBEDDING_ENDPOINT`, computed by the Delta Sync index from `search_text`.
- **Index:** Delta Sync, TRIGGERED. The source table is written with MERGE on a content hash, so a rerun with no
  changes re-embeds nothing, and deletes/unavailable listings leave the index.
- **Privacy (spec §9.1):** emails and phone numbers are redacted from titles, descriptions, vision output and
  queries. No coordinates, file paths or user fields enter Gold or the index.

## Setup — once, in this order

1. **Lakebase:** run `lakebase/seeds/003_demo_listing_files.sql` in the Lakebase query editor.
   It links `demo-listing-001/002` to `/Volumes/bootcamp_students/shipp_bronze/listing_images/<listing_id>/cover.jpg`.
2. **CDC sync for `shipp.listing_files`:** create it the same way you created `lb_listings_history`, with the
   target name exactly `bootcamp_students.shipp_bronze.lb_listing_files_history`. (Migration 008 already set
   `REPLICA IDENTITY FULL` on `listing_files`.) Confirm the new row appears there before continuing.
3. **Images:** run `notebooks/rag/50_silver_listing_files` once (it creates the Volume), then in Catalog →
   `bootcamp_students` → `shipp_bronze` → Volumes → `listing_images`, create folders `demo-listing-001` and
   `demo-listing-002` and upload one photo named `cover.jpg` into each. The path must match the seed exactly.
4. **Endpoints:** run `validation/04_platform_preflight`, then set in `config/settings.py`:
   `VISION_ENDPOINT` (a chat model that accepts images), `EMBEDDING_ENDPOINT` (an embedding model),
   `VS_ENDPOINT_NAME` (an existing Vector Search endpoint if the workspace does not let you create one).
5. **Commit** the settings change before running anything.

## Run order and pass conditions

Run `pipeline/90_run_pipeline` first so Silver listings are current. Then either run
`pipeline/91_run_rag_pipeline`, or the notebooks one by one (Clear state and outputs → Run all):

| # | Notebook | PASS |
|---|---|---|
| 50 | `rag/50_silver_listing_files` | gate PASS, `8A.2 PASS`, rerun identical |
| 51 | `rag/51_vision_enrichment` | ≥ 1 call OK; parsed example printed |
| 52 | `rag/52_silver_listing_content` | gate PASS; demo listings show `vision_status = OK` |
| 53 | `rag/53_gold_listing_search_docs` | gate PASS, CDF on, second MERGE changes 0 rows |
| 54 | `rag/54_ai_search_index` | index synced, probe query (not a title) returns `demo-listing-001` |
| 55 | `rag/55_rag_retrieval_eval` | hit@3 ≥ `RAG_EVAL_MIN_HIT_RATE` |
| 56 | `rag/56_silver_semantic_scores` | gate PASS, one row per retrieved (request, listing) |

**Evidence to save** (Stage 17 Variety proof): the Volume file listing (50), one raw vision JSON + its parsed
result (51), the `vision_status` counts (52), the MERGE metrics of both runs (53), the probe output with
scores and `sync_seconds` (54), the eval summary (55).

## Velocity note

Notebook 54 prints `sync_seconds` — the time from triggering the index sync to the index holding the new Gold
state. That is one hop of the Velocity trace (`gold_available_at → search_available_at`), not the whole SLO.
The end-to-end measurement (Lakebase change → retrieval) belongs to Stage 17 and must use real timestamps.

## Using it from the Agent

```python
from rag.retrieval import search_listing_context

context = search_listing_context("small table for a studio apartment", k=5, category="FURNITURE")
# [{"listing_id": ..., "title": ..., "snippet": ..., "score": ...}, ...]  — [] when nothing matches
```

The Agent must still call `get_listing_status(listing_id)` against Lakebase before recommending or saving:
the index can be a few seconds behind operational truth.

## Switching Gold to scoring v2 (after 56 passes)

1. `config/settings.py → SCORING`: set `"version": "v2-semantic"` and
   `"weights": {"distance": 0.35, "semantic": 0.35, "timing": 0.20, "condition": 0.10}`.
2. `data_pipeline/gold/scoring.py → match_score`: add a `semantic` argument and its weighted term; add a unit test.
3. `notebooks/development/40_gold_candidate_matches`: left-join `SILVER_SEMANTIC_SCORES` on
   (`request_id`, `listing_id`), `semantic_score = coalesce(semantic_score, 0)`, add the column to
   `EXPECTED_COLUMNS`, pass it to `match_score`.
4. Rerun 40 and compare the ranking with v1 for `demo-request-001` — keep that screenshot as evidence.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| 50: `lb_listing_files_history does not exist` | Setup step 2 not done |
| 50: `8A.2 NOT MET` | no image in the Volume, or path/filename differs from the seed |
| 51: endpoint not found | set `VISION_ENDPOINT` to a name from the printed list |
| 51: every call `non-retryable HTTP 400` | the endpoint does not accept images — choose a vision-capable one |
| 51: `model reported no identifiable item` | the photo does not show an item; replace it, bump the prompt version |
| 52: listing stays `PENDING` | 51 has not processed that file yet (or the call cap was hit) — rerun 51 |
| 54: endpoint not ONLINE / creation forbidden | reuse an existing endpoint name from 04 in `VS_ENDPOINT_NAME` |
| 54: timeout waiting for sync | check the index page in Catalog; the first sync of a new index takes longest |
| 55: eval references listings not in Gold | the seed changed — update `rag/eval/eval_set.json` in the same PR |

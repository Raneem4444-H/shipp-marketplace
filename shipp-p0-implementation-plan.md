# Shipp P0 Implementation Plan

**Source:** Shipp — Expat Household Marketplace Specification v2.0  
**Objective:** Demonstrate one complete, measurable workflow:

```text
Create Listing / Request
        ↓
Lakebase operational state
        ↓
Incremental ingestion
        ↓
Spark Bronze → Silver → Gold
        ↓
Candidate matches + searchable listing content
        ↓
AI Agent recommendation
        ↓
User-approved save_item()
        ↓
Lakebase + audit event
        ↓
Incremental analytics
```

## 1. P0 Scope and non-goals

### In scope

1. A user can create a household-item Listing with one or more images.
2. A user can create a single-item Request.
3. An incremental Spark pipeline produces trusted candidate matches.
4. OpenRouteService enriches eligible listing/request pairs with route distance and duration.
5. Listing descriptions and image-derived text are indexed in Databricks AI Search.
6. An AI Agent retrieves structured matches, semantic listing context, and current listing status.
7. After approval, `save_item()` validates current state, writes to Lakebase, and records `agent_activity`.
8. A Streamlit Databricks App demonstrates the complete flow.
9. Lakebase changes feed incremental analytics and freshness metrics.
10. The demo measures the target of less than 60 seconds from eligible operational change to retrieval availability.

### Explicitly out of scope

- Payments, escrow, refunds, settlement, and partner payouts
- Shipment execution, inspection, disputes, and full tracking
- Bundle optimization and multi-item requests
- Shipping-partner portal
- Notifications, ratings, identity verification, and admin console
- Production-scale volume claims
- A separate Donor and Requester user model

## 2. Recommended implementation decisions

| Decision | Recommendation | Reason |
|---|---|---|
| Frontend | Streamlit deployed as a Databricks App | It is named in the specification and is sufficient for the P0 workflow |
| Operational store | Lakebase PostgreSQL tables | Lakebase is the source of truth for current application state |
| Data products | Delta tables in Unity Catalog | Keeps Bronze/Silver/Gold separate from operational state |
| File storage | Unity Catalog Volume | Preserves original images for reprocessing and audit |
| Ingestion | Lakebase CDF where available; a timestamped change-feed fallback for local development | Makes the dependency explicit without blocking all development |
| Pipeline orchestration | Lakeflow Jobs / Databricks Workflows with incremental checkpoints | Supports retries, observability, and the velocity measurement |
| Vision | Use the first workspace-supported vision endpoint; default schema is structured JSON | Avoids hard-coupling the project to a model that may not be enabled |
| Search | Databricks AI Search over `gold_listing_search_docs` | Provides semantic retrieval with `listing_id` traceability |
| Agent | Databricks Agent / model-serving endpoint with typed tools | Separates retrieval from the controlled Lakebase write |
| External route API | OpenRouteService with secrets, retry/backoff, raw response capture, and cache | Satisfies the enrichment requirement without making route calls part of user interaction |
| Identity | Use the Databricks App identity for the capstone; keep `user_id` explicit in the data model | Keeps authorization demonstrable while avoiding an unnecessary auth subsystem |

## 3. Architecture and repository layout

```text
shipp/
├── app/
│   ├── streamlit_app.py
│   ├── lakebase_repo.py
│   ├── agent_client.py
│   └── ui_components.py
├── agent/
│   ├── instructions.md
│   ├── tools.py
│   ├── schemas.py
│   └── policy.py
├── pipeline/
│   ├── bronze_ingest.py
│   ├── silver_transform.py
│   ├── route_enrichment.py
│   ├── match_scoring.py
│   ├── search_documents.py
│   └── analytics.py
├── sql/
│   ├── lakebase_schema.sql
│   ├── constraints.sql
│   └── seed_demo_data.sql
├── resources/
│   ├── app.yaml
│   ├── jobs.yml
│   └── ai_search_index.yml
├── tests/
│   ├── test_validation.py
│   ├── test_match_scoring.py
│   ├── test_save_item.py
│   └── test_pipeline_freshness.py
├── docs/
│   ├── platform-gates.md
│   ├── data-contracts.md
│   └── demo-runbook.md
└── README.md
```

The exact Databricks resource configuration can vary by workspace. The logical boundaries above should remain stable.

## 4. Delivery sequence

### Phase 0 — Platform proof and project skeleton

**Goal:** Resolve platform risks before building downstream logic.

Tasks:

- Confirm Lakebase instance access and PostgreSQL connectivity.
- Confirm whether Lakebase CDF is available in the workspace.
- Confirm Unity Catalog Volume creation and file access.
- Confirm Spark / Lakeflow job execution and checkpoint storage.
- Confirm the selected Vision endpoint and its authentication method.
- Confirm Databricks AI Search index creation and refresh behavior.
- Confirm Databricks App deployment with a minimal Streamlit health page.
- Create a secrets/resource checklist for OpenRouteService and the Vision endpoint.
- Add a tiny synthetic dataset and a local configuration profile.

**Exit gate:** A smoke run can insert one Listing and one Request, run a Spark job, write one Delta table, and show a healthy Streamlit page. If any preview feature is unavailable, document the fallback before proceeding.

### Phase 1 — Operational model and CRUD

**Goal:** Establish Lakebase as operational truth.

Create:

- `users`
- `roles`
- `user_roles`
- `listings`
- `requests`
- `listing_files`
- `saved_items`
- `agent_activity`

Required constraints:

- Stable UUID primary keys.
- Foreign keys for user, request, listing, and file relationships.
- Enumerated or checked values for Listing status, Request status, category, condition, and action status.
- Unique constraint on `(user_id, request_id, listing_id)` in `saved_items`.
- `updated_at` on mutable operational tables.
- `created_at` on all auditable entities.
- Indexes on Listing status/category/availability, Request status/category/need-by date, and saved-item lookup fields.

Implement repository methods:

```text
create_listing()
update_listing()
attach_listing_file()
create_request()
get_request()
get_listing_status()
create_saved_item_if_absent()
record_agent_activity()
```

The App should support Listing and Request creation before any AI functionality is added.

**Exit gate:** A user can create an Available Listing, attach an image reference, create an Open Request, and see both records after a page refresh.

### Phase 2 — Bronze ingestion

**Goal:** Preserve every source event and file without losing raw evidence.

Bronze outputs:

- `bronze_listing_changes`
- `bronze_request_changes`
- `bronze_listing_files`
- `bronze_external_listings` (optional seed source for variety)
- `bronze_route_responses`
- `bronze_vision_responses`

Every Bronze record should carry:

```text
source_system
source_record_id
operation
source_updated_at
ingested_at
batch_id
raw_payload
schema_version
ingestion_status
error_message
```

Implementation rules:

- Use CDF for Lakebase changes if the platform gate passes.
- Use Auto Loader for image and external-file inputs.
- Preserve failed route and Vision responses or failure envelopes.
- Use checkpoints and deterministic source identifiers.
- Make reprocessing idempotent.

**Exit gate:** Updating a Listing creates a new Bronze event without duplicating the prior event, and the original image remains available in the Volume.

### Phase 3 — Silver cleaning, privacy, and enrichment

**Goal:** Produce validated, normalized, privacy-safe records.

Silver outputs:

- `silver_listings`
- `silver_requests`
- `silver_routes`
- `silver_listing_content`

Validation:

- Required identifiers present.
- Category, condition, and status values valid.
- Latitude and longitude within valid ranges.
- Availability dates parse correctly and have valid ordering.
- Duplicate source events removed deterministically.
- Listing and Request text normalized for search.
- Exact contact details and unnecessary exact-address data removed from downstream fields.

Route enrichment:

1. Build eligible Listing/Request pairs using status, category, and date checks.
2. Normalize coordinates and construct a stable route-cache key.
3. Read the route cache before calling OpenRouteService.
4. Call OpenRouteService only for cache misses.
5. Retry transient failures with bounded exponential backoff.
6. Respect rate-limit responses and record failure status.
7. Store raw responses in Bronze and normalized distance/duration in Silver.
8. Never substitute invented distance or duration values.

Vision enrichment:

Use one documented JSON contract:

```json
{
  "listing_id": "uuid",
  "source_file": "string",
  "detected_text": "string|null",
  "visual_attributes": ["string"],
  "image_summary": "string|null",
  "model_name": "string",
  "model_version": "string",
  "processed_at": "timestamp",
  "status": "success|failed",
  "error_message": "string|null"
}
```

If Vision fails, preserve the file, log the failure, and continue with text-only search content.

**Exit gate:** A valid Listing/Request pair produces normalized Silver records, route values when available, and privacy-safe search content. Failed enrichment is visible and does not erase raw inputs.

### Phase 4 — Gold candidate matching

**Goal:** Produce a trusted, explainable candidate-match data product.

Gold output:

```text
gold_candidate_matches
```

Recommended record shape:

```text
match_id
request_id
listing_id
category_compatible
availability_compatible
distance_km
duration_min
semantic_score
category_score
availability_score
distance_score
match_score
rank
match_reasons
computed_at
pipeline_run_id
source_updated_at
```

Eligibility:

- Listing status is `Available`.
- Request status is `Open` or `MatchesAvailable`.
- Categories are compatible.
- Listing availability overlaps the Request need-by date.
- Coordinates are present for distance scoring; if route enrichment is unavailable, retain the candidate only if the fallback policy is explicitly configured and label the route fields as unavailable.

Initial scoring contract:

```text
match_score =
    0.35 × semantic_score
  + 0.25 × category_score
  + 0.20 × availability_score
  + 0.20 × distance_score
```

Recommended normalization:

- `semantic_score`: 0–1 from the selected embedding/search similarity.
- `category_score`: 1 for exact/approved compatible category, 0 otherwise.
- `availability_score`: 1 when the Listing covers the need-by date, otherwise 0.
- `distance_score`: `max(0, 1 - distance_km / distance_cap_km)`, with the cap configured in a parameter table.

Keep component scores and reasons; do not expose only a single opaque score.

**Exit gate:** Given a seeded Request and several Listings, the Gold table returns deterministic ranked candidates and excludes unavailable, incompatible, or expired Listings.

### Phase 5 — Search documents and AI Search

**Goal:** Make listing context semantically retrievable with traceability.

Gold output:

```text
gold_listing_search_docs
```

Document fields:

```text
doc_id
listing_id
title
description
category
condition
city_or_area
availability_summary
image_summary
visual_attributes
search_text
updated_at
source_version
```

Rules:

- Keep `listing_id` in every document and result.
- Exclude phone numbers, emails, and unnecessary exact addresses.
- Rebuild or update documents incrementally from changed Listings and enrichment results.
- Store enough metadata to explain why a result was retrieved.
- Test both exact terms and natural-language queries.

**Exit gate:** A labeled query set retrieves the expected Listing in the top results and every result can be traced back to `listing_id`.

### Phase 6 — Agent tools and controlled write

**Goal:** Make recommendations grounded in Gold/Search evidence and make saving safe.

Tool contracts:

```text
get_candidate_matches(
  request_id: string,
  limit: integer = 5
) -> CandidateMatch[]

search_listing_context(
  query: string,
  request_id: string|null,
  limit: integer = 5
) -> SearchResult[]

get_listing_status(
  listing_id: string
) -> ListingStatus

save_item(
  user_id: string,
  request_id: string,
  listing_id: string
) -> SaveResult
```

`save_item()` policy:

1. Confirm the user explicitly selected or approved the Listing.
2. Read current Listing state from Lakebase.
3. Reject anything not currently `Available`.
4. Check for an existing `(user_id, request_id, listing_id)` record.
5. Insert the Saved Item transactionally if absent.
6. Record success or rejection in `agent_activity`.
7. Return the updated saved state.

The Agent must:

- Prefer `gold_candidate_matches` for structured ranking.
- Use AI Search to support contextual explanation, not to replace Gold eligibility.
- Never invent Listing facts, distance, duration, or availability.
- State clearly when no candidate exists or enrichment is unavailable.
- Never write to Gold or bypass the save policy.

**Exit gate:** The Agent recommends a real candidate with evidence, rejects unavailable Listings, prevents duplicate saves, and records every retrieval/write outcome.

### Phase 7 — Streamlit Databricks App

**Goal:** Expose the P0 workflow in a small, testable interface.

Screens or sections:

1. **Create Listing**
   - title, description, category, condition, location, coordinates, availability, image upload
2. **Create / Select Request**
   - request text, category, destination, coordinates, need-by date
3. **Candidate Matches**
   - rank, title, category, condition, distance, duration, score, reasons, freshness
4. **Ask Agent**
   - recommendation, evidence, caveats, and selected Listing
5. **Save Item**
   - explicit approval button, result state, duplicate/unavailable error state
6. **Activity / Metrics**
   - optional P0 demo panel showing saved state, agent activity, match count, and pipeline freshness

App behavior:

- Show a clear pipeline freshness timestamp.
- Disable or explain actions when upstream data is not ready.
- Refresh Lakebase state after a successful save.
- Avoid embedding secrets in source code.
- Keep the interface usable with seeded demo data if external enrichment is unavailable.

**Exit gate:** A new user can complete Listing/Request → match → recommendation → save without leaving the App.

### Phase 8 — Incremental analytics and evaluation

**Goal:** Prove business usefulness and technical quality.

Gold output:

```text
gold_marketplace_metrics
```

Track:

- records ingested
- accepted/rejected Silver records
- duplicates removed
- route and Vision failures
- candidate matches produced
- Requests with at least one match
- save rate
- Agent retrieval success/failure
- `save_item()` success/failure
- duplicate-save prevention
- operational change timestamp
- retrieval-available timestamp
- freshness latency

Required calculations:

```text
Candidate Match Rate =
  Requests with at least one eligible match / eligible Requests

Time to Match =
  first retrieval_available_at - operational_change_at

Velocity SLO =
  retrieval_available_at - operational_change_at < 60 seconds
```

Evaluation set:

- 5–10 representative Requests.
- Expected Listing IDs for each Request.
- At least one no-match case.
- At least one unavailable-after-recommendation case.
- At least one duplicate-save attempt.
- At least one Vision or route failure case.

Measure:

- correct Listing in top results
- retrieval relevance
- grounded answer correctness
- Listing/source traceability
- retrieval latency
- Agent tool success/failure
- invalid-action rejection

## 5. Lakebase schema contract

The operational schema should remain small enough to explain in the demo:

```sql
users (
  user_id uuid primary key,
  name text not null,
  current_city text,
  created_at timestamptz not null
)

listings (
  listing_id uuid primary key,
  donor_id uuid not null references users(user_id),
  title text not null,
  description text not null,
  category text not null,
  condition text not null,
  location text not null,
  latitude numeric,
  longitude numeric,
  available_from date,
  available_until date,
  status text not null,
  created_at timestamptz not null,
  updated_at timestamptz not null
)

requests (
  request_id uuid primary key,
  requester_id uuid not null references users(user_id),
  request_text text not null,
  category text not null,
  location text not null,
  latitude numeric,
  longitude numeric,
  need_by_date date,
  status text not null,
  created_at timestamptz not null,
  updated_at timestamptz not null
)

listing_files (
  listing_file_id uuid primary key,
  listing_id uuid not null references listings(listing_id),
  file_path text not null,
  file_type text not null,
  created_at timestamptz not null
)

saved_items (
  saved_item_id uuid primary key,
  user_id uuid not null references users(user_id),
  request_id uuid not null references requests(request_id),
  listing_id uuid not null references listings(listing_id),
  saved_at timestamptz not null,
  unique (user_id, request_id, listing_id)
)

agent_activity (
  activity_id uuid primary key,
  user_id uuid references users(user_id),
  tool_name text not null,
  entity_id uuid,
  action_status text not null,
  request_id uuid,
  listing_id uuid,
  error_code text,
  metadata jsonb,
  created_at timestamptz not null
)
```

Use the exact workspace-supported PostgreSQL types and constraint syntax during implementation. The important contract is the relationship and uniqueness behavior, not a specific UUID implementation.

## 6. Platform gates and fallback policy

Resolve these before committing to the full build:

| Gate | Required proof | Fallback if unavailable |
|---|---|---|
| Lakebase CDF | A Listing update appears as an incremental source event | Use an append-only operational change table with `updated_at` watermarking, documented as a capstone fallback |
| Unity Catalog Volume | App-uploaded image can be read by the pipeline | Use a workspace-managed file landing path temporarily, then migrate before final demo |
| Vision endpoint | One image produces the documented JSON response | Use text-only content plus a recorded failed Vision event; do not fabricate attributes |
| OpenRouteService | A route call returns distance/duration | Use seeded route fixtures for deterministic demo runs, while preserving failure handling |
| AI Search | Index refreshes after a changed search document | Use a deterministic keyword retrieval fallback only for local development, not as the final P0 claim |
| Databricks App | Streamlit health page deploys | Run the same App locally while platform setup is repaired; deployment remains part of final DoD |

Fallbacks must be visible in metadata and demo narration. They must not silently change the technical claim.

## 7. Test strategy

### Unit tests

- status/category/date validation
- PII minimization
- route-cache key generation
- retry classification
- match-score normalization
- deterministic ranking and tie-breaking
- duplicate-save policy
- unavailable-listing rejection

### Integration tests

- Lakebase CRUD and constraints
- CDF or watermark ingestion
- Volume file discovery
- OpenRouteService mock responses and rate limits
- Vision success/failure envelopes
- Gold table refresh
- AI Search result traceability
- Agent tool calls against seeded data

### End-to-end demo test

1. Create a Listing with an image.
2. Create a Request.
3. Trigger or wait for the incremental pipeline.
4. Confirm Gold candidate rows.
5. Confirm AI Search content.
6. Ask the Agent for a recommendation.
7. Approve and save a Listing.
8. Attempt the same save again.
9. Mark the Listing unavailable and attempt a save.
10. Confirm `agent_activity`, CDF-derived analytics, and App state.
11. Record freshness latency.

## 8. Suggested execution order for a small team

Parallelize after Phase 0:

- **Data track:** Lakebase schema, CDF ingestion, Bronze/Silver/Gold tables.
- **Enrichment track:** OpenRouteService client, route cache, Vision contract, failure handling.
- **Agent track:** Gold/search retrieval tools, agent instructions, `save_item()` policy.
- **App track:** Streamlit forms, candidate display, save-state refresh.
- **Evaluation track:** seeded data, labeled queries, metrics, demo runbook.

Integrate at the end of each phase using the exit gate, not only at the final demo.

## 9. Definition of done

The P0 implementation is complete only when all of the following are demonstrated:

- A new Listing and Request are stored in Lakebase.
- The change is ingested incrementally without duplicate processing.
- Bronze preserves raw source evidence.
- Silver validates, normalizes, and minimizes downstream data.
- OpenRouteService enrichment includes secure authentication, caching, retries, raw-response preservation, and failure logging.
- Gold contains explainable ranked candidate matches.
- AI Search returns traceable Listing context.
- The Agent grounds its recommendation in Gold and Search evidence.
- `save_item()` validates current Listing state and prevents duplicate Saved Items.
- `agent_activity` captures retrieval and write outcomes.
- The Streamlit Databricks App shows the changed saved state.
- Analytics captures match, save, Agent, and freshness metrics.
- The demo records whether the less-than-60-second target was met.
- At least one no-match, unavailable-listing, duplicate-save, and enrichment-failure case is shown.
- No payment, shipment, inspection, or volume claim is required to pass P0.

## 10. First implementation sprint

The first sprint should deliver a vertical slice, not a broad scaffold:

1. Complete the Phase 0 platform gates.
2. Create the Lakebase schema and seed one Donor/Requester user.
3. Build Listing and Request CRUD.
4. Land one image in the Volume and link it with `listing_files`.
5. Run a Spark job that produces Bronze and Silver for the seeded records.
6. Produce a first `gold_candidate_matches` table using deterministic category, date, and distance logic.
7. Show the candidate in a minimal Streamlit page.
8. Add `save_item()` with status validation and duplicate protection.
9. Capture the first freshness measurement.

At the end of this sprint, the team should already be able to demonstrate:

```text
Listing + Request
    → Lakebase
    → Spark
    → Candidate Match
    → Save Item
```

Then add Vision, AI Search, Agent explanation, and analytics depth without changing the operational contract.
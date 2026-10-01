# `shipp.agent`: the Shipp AI Agent

Spec coverage: §5.6 (retrieval + write), §6.5 (read/write ownership), §9.1–9.5 (privacy, security, reliability, audit), §10.1–10.3 (no match, unavailable listing, duplicate save).

## What it does

For one user and one request, the agent:

1. reads scored candidate matches from Gold,
2. pulls semantic context for those candidates from AI Search,
3. checks live availability in Lakebase,
4. explains a recommendation, and
5. proposes a save.

The save only happens when the user confirms in the app.

```
App session (user_id, request_id)
        │
        ▼
ShippAgent.chat() ──► authorize request owner (Lakebase)
        │
        ▼
  model ⇄ tools (max N rounds)
   ├─ get_candidate_matches   → Gold   gold_candidate_matches
   ├─ search_listing_context  → AI Search, filtered to candidate listing_ids
   ├─ get_listing_status      → Lakebase listings
   └─ propose_save            → returns SaveProposal (no write)
        │
        ▼
AgentTurn(reply, pending_save)  ──► App shows "Confirm save"
        │ user clicks
        ▼
ShippAgent.confirm_save() → is_candidate (Gold) → LakebaseRepo.save_item()
                                                   one transaction:
                                                   saved_items + agent_activity
```

## Design decisions

**The model never writes.** Spec §4 step 9 says "after user approval". If the model called `save_item` directly, approval would be a sentence in a prompt. Here approval is a button click. `confirm_save` re-checks everything (candidate membership, request ownership, listing status and window) because time passes between the proposal and the click.

**`user_id` and `request_id` are not tool arguments.** They come from the authenticated app session. The model can only pass a `listing_id`, and only one that is already a Gold candidate for this request. A hallucinated or injected ID is rejected and logged.

**AI Search is filtered to candidates.** Search adds context. It cannot add listings that failed the pipeline's eligibility filters, so the agent never recommends something the matching engine excluded.

**`FOR SHARE` on the listing read.** A donor withdrawing the item at the same moment has to wait for the save transaction, so we cannot save a listing that was withdrawn between the check and the insert.

**Every tool call is audited.** `agent_activity` gets one row per call with `success | rejected | duplicate | failed`. This feeds the Agent success rate KPI (§5.8).

**Framework-free loop.** The loop is about 60 lines, fully testable with fakes, and has no dependency on agent-framework APIs that shift between releases. If you later want MLflow tracing or Model Serving deployment, wrap `ShippAgent`; don't rewrite it.

## Deployment choice

The agent runs **inline inside the Databricks App process**. It is not a separate Model Serving endpoint. The only served model is the LLM (`SHIPP_LLM_ENDPOINT`).

For P0 this means one deployable, one service principal, and one set of grants. It also settles the Apps vs Model Serving ownership question: whoever owns the App owns the agent runtime.

## Contracts this module depends on

Everything below is enforced in `contracts.py`. If upstream changes, update that file first.

### `gold_candidate_matches`

One row per eligible `(request_id, listing_id)` pair:

| column | type | note |
|---|---|---|
| request_id, listing_id | STRING | grain key |
| title, category, condition | STRING | denormalized so the agent needs no joins |
| area | STRING | coarse location only; never an exact address (§6.4) |
| match_score | DOUBLE | 0–1, from the finalized scoring formula |
| distance_km, duration_min | DOUBLE | NULL when routing failed; the agent says "unknown" |
| available_until, computed_at | TIMESTAMP | |

### `gold_listing_search_docs`

Columns: `listing_id, title, category, condition, search_text`. The AI Search index is built on `search_text`.

### Lakebase

- Status values `available` and `closed` must match the enum vocabulary chosen for issues #6/#12.
- `saved_items` needs a UNIQUE `(user_id, request_id, listing_id)` constraint. See `sql/agent_prereqs.sql`.

## Configuration

| env var | required | default |
|---|---|---|
| SHIPP_LLM_ENDPOINT | yes | — |
| SHIPP_SQL_WAREHOUSE_ID | yes | — |
| SHIPP_CANDIDATE_MATCHES_TABLE | no | shipp.gold.gold_candidate_matches |
| SHIPP_SEARCH_INDEX | no | shipp.gold.gold_listing_search_docs_index |
| SHIPP_LAKEBASE_SCHEMA | no | bootcamp_shipp |
| SHIPP_LAKEBASE_INSTANCE | in App | — (local dev can use PGPASSWORD) |
| PGHOST, PGPORT, PGDATABASE, PGUSER | yes | injected by the App's Lakebase resource |
| SHIPP_AGENT_MAX_MATCHES / _MAX_SEARCH_RESULTS / _MAX_TOOL_ROUNDS / _MIN_MATCH_SCORE | no | 5 / 5 / 6 / 0.0 |

### `app.yaml` excerpt

```yaml
command: ["streamlit", "run", "app.py"]
env:
  - name: SHIPP_LLM_ENDPOINT
    valueFrom: llm-endpoint        # app resource: serving endpoint, CAN_QUERY
  - name: SHIPP_SQL_WAREHOUSE_ID
    valueFrom: sql-warehouse       # app resource: SQL warehouse, CAN_USE
  - name: SHIPP_LAKEBASE_INSTANCE
    value: "shipp-lakebase"
```

Attach the Lakebase database as an app resource so the `PG*` variables are injected.

### Unity Catalog grants for the app's service principal

- `USE CATALOG` on `shipp`
- `USE SCHEMA` on `shipp.gold`
- `SELECT` on both Gold tables
- `SELECT` on the search index

## Using it from Streamlit

```python
from shipp.agent import ShippAgent

agent = st.cache_resource(ShippAgent.from_env)()
user_id = current_user_id()          # from the app's auth headers, never a text box

turn = agent.chat(user_id=user_id, request_id=req_id,
                  user_message=prompt, history=st.session_state.history)
st.write(turn.reply)
if turn.pending_save and st.button(f"Save {turn.pending_save.title}"):
    result = agent.confirm_save(user_id=user_id, request_id=req_id,
                                listing_id=turn.pending_save.listing_id)
    st.success(result.message) if result.ok else st.warning(result.message)
```

The card-level **Save Match** button in the Find Items screen can call `confirm_save` directly. It goes through the same validation and the same audit trail.

## Tests

- `pytest tests/unit/agent`: no workspace needed. Covers rules, parsing, the tool guardrails, the loop, and `save_item`'s transaction paths.
- `tests/integration/agent`: skipped until `SHIPP_RUN_INTEGRATION=1`. Turn it on only after Gold passes its DoD.

## New dependencies (`requirements.in`)

```
databricks-sdk        # already present
psycopg[binary]>=3.2
openai                # used by WorkspaceClient.serving_endpoints.get_open_ai_client()
```

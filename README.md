# shipp-marketplace
Databricks AI Data Engineering Capstone — multi-sided marketplace with data pipelines, RAG, AI agents, and a Databricks App.
-----------------------------------------------

## SHIPP Data Architecture

```text
Donor / Requester
        ↓
Databricks App
        ↓
Lakebase
(listings, requests, saved_items, agent_activity)
        ↓
CDF + Auto Loader
        ↓
Bronze
(raw changes, images, API responses)
        ↓
Silver
(clean listings, requests, image-derived content, routes)
        ↓
Eligible Listing–Request pairs
        ↓
POST /v2/matrix/driving-car
        ↓
gold_candidate_matches + gold_listing_search_docs
        ↓
AI Search + AI Agent
        ↓
Recommendation
        ↓
User approves save_item()
        ↓
Lakebase → CDF → gold_marketplace_metrics
        ↓
Databricks App shows “Saved”
```

# Landing Page Overview

![Landing Page Overview](./workFlow/LandPage.png)

# Login/signup Page

![Login/signup Page](./workFlow/loginSignpage.png)

# Posting Page

![Posting Page](./workFlow/postingitemPage.png)

# Review Page

![Review Page](./workFlow/Review_your_item_request.png)

-----------------------------------------------



## Matching Logic

```text
                    ELIGIBILITY (hard filters, Stage 6 — data_pipeline/silver/pairs.py)

Listing AVAILABLE, not expired        Request OPEN / MATCHES_AVAILABLE, need_by in future
Same category (normalised)            Listing available on/before need_by
Donor ≠ requester                     Straight-line distance ≤ 100 km
        ↓
POST /v2/matrix/driving-car  (Stage 7 — cached, rate-limited, raw JSON kept in Bronze)
        ↓
                    MATCH SCORE v1 (Stage 8 — data_pipeline/gold/scoring.py)

Route distance        × 50%     max(0, 1 − km / 50); 0 if no route (never invented)
Timing slack          × 30%     min(1, days between availability and need_by / 7)
Item condition        × 20%     NEW 1.0 · LIKE_NEW 0.9 · GOOD 0.75 · FAIR 0.5 · other 0.3
        ↓
gold_candidate_matches (top 10 per request)  →  AI Agent

v2 (after AI Search): distance 35% · semantic 35% · timing 20% · condition 10%
Weights live in one place: config/settings.py → SCORING
```

## Example Routing Enrichment Flow

```text
Lakebase
Listings + Requests
        ↓
CDF
        ↓
bronze_listing_changes + bronze_request_changes
        ↓
silver_listings + silver_requests
        ↓
Eligible Listing–Request pairs
        ↓
POST /v2/matrix/driving-car
        ↓
bronze_route_responses
(raw API JSON)
        ↓
silver_routes
(distance_km, duration_min)
        ↓
gold_candidate_matches
        ↓
AI Agent
```

## Repository Structure

```text
shipp-marketplace/
├── config/
│   ├── tables.py              ← every Unity Catalog table name (single registry)
│   └── settings.py            ← statuses, ORS settings, scoring weights
├── data_pipeline/             ← reusable, unit-tested functions; never writes tables
│   ├── common/                   geo.py, spark_io.py
│   ├── silver/                   current_state.py (delete-aware CDC), pairs.py, routes.py
│   ├── gold/                     scoring.py
│   ├── ingestion/                ors_client.py
│   └── quality/                  data_quality.py
├── notebooks/                 ← the ONLY writers of tables (one writer per table)
│   ├── common/shipp_silver_lib   bootstrap: sys.path + module reload + helpers
│   ├── validation/               00–04 checks
│   ├── development/              10, 11 Silver · 20 ORS smoke · 30 pairs · 31 ORS · 32 routes · 40 Gold
│   ├── delete/                   live CDC delete test
│   ├── pipeline/                 90 end-to-end runner
│   └── README_START_HERE.md      run order + rules
├── lakebase/                  ← operational DB: migrations 001–009, seeds, README
├── tests/unit/                ← pytest (local Spark) — runs in CI
├── .github/workflows/ci.yml   ← secret scan + ruff + pytest
├── rag/                       ← Stage 8–9: vision, search docs, AI Search, retrieval tool (see rag/README.md)
├── agent/                     ← next stage (not built yet)
├── workFlow/                  ← spec, diagrams, UI mocks
└── requirements.txt, requirements-dev.txt
```

**Rules:** secrets only in the Databricks secret scope `shipp` · no table name or weight hardcoded in a notebook ·
one writer per table · CDC logic changes only in `data_pipeline/silver/current_state.py` + its tests.


-----
### Repository Architecture

The diagram below maps the SHIPP end-to-end architecture to the implementation files in this repository.

```mermaid
flowchart TD

subgraph group_pipeline["Matching Pipeline"]
  node_bronze[("Bronze History<br/>config/tables.py")]
  node_silver["Silver Current State<br/>current_state.py"]
  node_pairs["Eligible Candidate Pairs<br/>pairs.py"]
  node_routes_api["ORS Route Enrichment<br/>ors_client.py"]
  node_silver_routes["Silver Routes<br/>routes.py"]
  node_scoring["Gold Match Scoring<br/>scoring.py"]
  node_gold_matches[("Gold Candidate Matches<br/>config/tables.py")]
end

subgraph group_search["Search & Unstructured Enrichment"]
  node_content["Listing Content<br/>content.py"]
  node_vision["Image / Vision Enrichment<br/>vision.py"]
  node_search_docs["Gold Search Documents<br/>search_docs.py"]
  node_index[("Databricks AI Search<br/>index.py")]
  node_retrieval["Semantic Retrieval<br/>retrieval.py"]
end

subgraph group_agent["AI Agent Workflow"]
  node_agent["SHIPP Agent<br/>agent.py"]
  node_model["Chat Model<br/>llm.py"]
  node_toolbox["Agent Tools<br/>tools.py"]
  node_gold_reader["Gold Candidate Reader<br/>gold.py"]
  node_listing_search["AI Search Client<br/>search.py"]
  node_lakebase_repo["Lakebase Repository<br/>lakebase.py"]
end

subgraph group_shared["Shared Contracts & Configuration"]
  node_rules["Save Validation Rules<br/>rules.py"]
  node_contracts["Agent Contracts<br/>contracts.py"]
  node_settings["Pipeline Settings<br/>settings.py"]
  node_tables["Table Registry<br/>tables.py"]
  node_geo["Geospatial Utilities<br/>geo.py"]
end

node_people(("Donor / Requester"))
node_app["Databricks Marketplace App"]
node_lakebase[("Lakebase<br/>Operational Truth")]
node_ors["OpenRouteService"]

node_people -->|"uses"| node_app

node_app -->|"operational reads / writes"| node_lakebase

node_lakebase -->|"CDC"| node_bronze

node_bronze -->|"reconstruct current state"| node_silver

node_silver -->|"forms eligible pairs"| node_pairs

node_pairs -->|"requests route enrichment"| node_routes_api

node_routes_api -->|"POST matrix API"| node_ors

node_routes_api -->|"persists raw JSON"| node_bronze

node_bronze -->|"raw ORS responses"| node_silver_routes

node_silver_routes -->|"normalized distance + duration"| node_scoring

node_scoring -->|"scores and ranks"| node_gold_matches


node_content -->|"adds image-derived context"| node_vision

node_vision -->|"enriched listing content"| node_search_docs

node_gold_matches -->|"listing / candidate metadata"| node_search_docs

node_search_docs -->|"indexes documents"| node_index

node_index -->|"serves semantic queries"| node_retrieval


node_app -->|"asks for recommendation"| node_agent

node_agent -->|"requests completions"| node_model

node_agent -->|"dispatches read tools"| node_toolbox

node_agent -->|"reads candidate matches"| node_gold_reader

node_agent -->|"builds search client"| node_listing_search

node_listing_search -->|"semantic search"| node_retrieval

node_agent -->|"validates / confirms save"| node_lakebase_repo

node_lakebase_repo -->|"reads + writes"| node_lakebase

node_lakebase_repo -->|"validates save"| node_rules

node_agent -->|"uses contracts"| node_contracts


node_pairs -->|"geospatial checks"| node_geo

node_pairs -->|"eligibility settings"| node_settings

node_scoring -->|"scoring weights"| node_settings

node_silver -->|"table names"| node_tables

node_gold_matches -->|"table name"| node_tables


click node_bronze "https://github.com/raneem4444-h/shipp-marketplace/blob/main/config/tables.py"
click node_silver "https://github.com/raneem4444-h/shipp-marketplace/blob/main/data_pipeline/silver/current_state.py"
click node_pairs "https://github.com/raneem4444-h/shipp-marketplace/blob/main/data_pipeline/silver/pairs.py"
click node_routes_api "https://github.com/raneem4444-h/shipp-marketplace/blob/main/data_pipeline/ingestion/ors_client.py"
click node_silver_routes "https://github.com/raneem4444-h/shipp-marketplace/blob/main/data_pipeline/silver/routes.py"
click node_scoring "https://github.com/raneem4444-h/shipp-marketplace/blob/main/data_pipeline/gold/scoring.py"
click node_gold_matches "https://github.com/raneem4444-h/shipp-marketplace/blob/main/config/tables.py"

click node_content "https://github.com/raneem4444-h/shipp-marketplace/blob/main/rag/content.py"
click node_vision "https://github.com/raneem4444-h/shipp-marketplace/blob/main/rag/vision.py"
click node_search_docs "https://github.com/raneem4444-h/shipp-marketplace/blob/main/rag/search_docs.py"
click node_index "https://github.com/raneem4444-h/shipp-marketplace/blob/main/rag/index.py"
click node_retrieval "https://github.com/raneem4444-h/shipp-marketplace/blob/main/rag/retrieval.py"

click node_agent "https://github.com/raneem4444-h/shipp-marketplace/blob/main/agent/agent_ship/src/shipp/agent/agent.py"
click node_model "https://github.com/raneem4444-h/shipp-marketplace/blob/main/agent/agent_ship/src/shipp/agent/llm.py"
click node_toolbox "https://github.com/raneem4444-h/shipp-marketplace/blob/main/agent/agent_ship/src/tools.py"
click node_gold_reader "https://github.com/raneem4444-h/shipp-marketplace/blob/main/agent/agent_ship/src/shipp/agent/gold.py"
click node_listing_search "https://github.com/raneem4444-h/shipp-marketplace/blob/main/agent/agent_ship/src/shipp/agent/search.py"
click node_lakebase_repo "https://github.com/raneem4444-h/shipp-marketplace/blob/main/agent/agent_ship/src/shipp/agent/lakebase.py"

click node_rules "https://github.com/raneem4444-h/shipp-marketplace/blob/main/agent/agent_ship/src/shipp/agent/rules.py"
click node_contracts "https://github.com/raneem4444-h/shipp-marketplace/blob/main/agent/agent_ship/src/shipp/agent/contracts.py"
click node_settings "https://github.com/raneem4444-h/shipp-marketplace/blob/main/config/settings.py"
click node_tables "https://github.com/raneem4444-h/shipp-marketplace/blob/main/config/tables.py"
click node_geo "https://github.com/raneem4444-h/shipp-marketplace/blob/main/data_pipeline/common/geo.py"


classDef pipeline fill:#dbeafe,stroke:#2563eb,stroke-width:1.5px,color:#172554
classDef search fill:#fef3c7,stroke:#d97706,stroke-width:1.5px,color:#78350f
classDef agent fill:#dcfce7,stroke:#16a34a,stroke-width:1.5px,color:#14532d
classDef shared fill:#ffe4e6,stroke:#e11d48,stroke-width:1.5px,color:#881337
classDef app fill:#e0e7ff,stroke:#4f46e5,stroke-width:1.5px,color:#312e81

class node_bronze,node_silver,node_pairs,node_routes_api,node_silver_routes,node_scoring,node_gold_matches pipeline
class node_content,node_vision,node_search_docs,node_index,node_retrieval search
class node_agent,node_model,node_toolbox,node_gold_reader,node_listing_search,node_lakebase_repo,node_people,node_ors agent
class node_rules,node_contracts,node_settings,node_tables,node_geo shared
class node_app,node_lakebase app
```


# shipp-marketplace
Databricks AI Data Engineering Capstone — multi-sided marketplace with data pipelines, RAG, AI agents, and a Databricks App.
-----------------------------------------------
3

## SHIPP Data Architecture

```text
                         SHIPP PLATFORM DATA
                ┌─────────────────────────────┐
                │          LAKEBASE           │
                │                             │
Donor ─────────→│ Listings                    │
Requester ─────→│ Requests                    │
Partner ───────→│ Partner Schedule            │
Inspector ─────→│ Inspections                 │
                └──────────────┬──────────────┘
                               │
                               ↓
                    Candidate Match Generation
                               │
                               ↓
                     Third-Party Data Sources
                ┌──────────────┼──────────────┐
                │              │              │
                ↓              ↓              ↓
          Furniture        ItemFits      openrouteservice
           Dataset         Dimensions       / HeiGIT API
                │              │              │
                └──────────────┴───────┬──────┘
                                       │
                                       ↓
                                   Raw Data
                                       │
                                       ↓
                                SPARK PIPELINE
                                       │
                                       ↓
                         ┌─────────────────────┐
                         │       BRONZE        │
                         │                     │
                         │ Raw source records  │
                         │ Raw API responses   │
                         │ Ingestion metadata  │
                         └──────────┬──────────┘
                                    │
                                    ↓
                         ┌─────────────────────┐
                         │       SILVER        │
                         │                     │
                         │ Clean listings      │
                         │ Clean requests      │
                         │ distance_km         │
                         │ duration_min        │
                         │ coordinates         │
                         │ route_feasible      │
                         └──────────┬──────────┘
                                    │
                                    ↓
                         ┌─────────────────────┐
                         │        GOLD         │
                         │                     │
                         │ match_candidates    │
                         │ logistics_score     │
                         │ ranked_matches      │
                         └──────────┬──────────┘
                                    │
                                    ↓
                                  AGENT
                                    │
                                    ↓
                       Recommendation + Action
```

## Matching Logic

```text
                         MATCH SCORE

                    ┌─────────────────┐
Listing ───────────→│ Item Fit        │
                    │                 │
Request ───────────→│ Date Fit        │
                    │                 │
ORS API ───────────→│ Distance        │
                    │                 │
Partner ───────────→│ Capacity        │
                    │                 │
Vehicle ───────────→│ Feasibility     │
                    └────────┬────────┘
                             │
                             ↓
                       Ranked Matches
                             │
                             ↓
                           Agent
                             │
                             ↓
                  "Best match is ..."
```

## Example Routing Enrichment Flow

```text
                    LAKEBASE

          Listings              Requests
     ┌────────────────┐    ┌────────────────┐
     │ origin         │    │ destination    │
     │ availability   │    │ need_by        │
     └───────┬────────┘    └────────┬───────┘
             │                      │
             └──────────┬───────────┘
                        │
                        ↓
                Candidate Matches
                        │
                        ↓
             openrouteservice API
                        │
                        ↓
                    Raw JSON
                        │
                        ↓
                 Spark Pipeline
                        │
                        ↓
              Bronze → Silver → Gold
                        │
                        ↓
                      Agent
                        │
                        ↓
              "Best match is ..."
```

## Repository Structure

```text
shipp-marketplace/
│
├── README.md
├── .gitignore
│
├── data_pipeline/
│   ├── ingestion/
│   ├── bronze/
│   ├── silver/
│   ├── gold/
│   └── quality/
│
├── rag/
├── agent/
├── app/
└── docs/
```

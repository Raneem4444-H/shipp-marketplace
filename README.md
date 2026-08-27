# shipp-marketplace
Databricks AI Data Engineering Capstone — multi-sided marketplace with data pipelines, RAG, AI agents, and a Databricks App.
-----------------------------------------------

                    SHIPP DATA
             ┌────────────────────┐
Donor ──────→│ Listings           │
Requester ──→│ Requests           │
Partner ────→│ Partner Schedule   │
Inspector ──→│ Inspections        │
             └─────────┬──────────┘
                       │
                       │
           EXTERNAL FREE SOURCES
                       │
     ┌─────────────────┼─────────────────┐
     ↓                 ↓                 ↓
Furniture          ItemFits       openrouteservice
dataset           dimensions        API
     │                 │                 │
     └─────────────────┴─────────────────┘
                       ↓
                 Spark Pipeline
                       ↓
              Bronze → Silver → Gold





shipp-marketplace/
│
├── README.md
├── .gitignore
│
├── data_pipeline/
├── rag/
├── agent/
├── app/
└── docs/



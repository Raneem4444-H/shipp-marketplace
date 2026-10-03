"""Canonical Unity Catalog object names for SHIPP.

This module defines the shared names of SHIPP Lakehouse data products and
Databricks-managed data resources.

Architectural boundaries
------------------------
Lakebase
    Operational application state and transactional source of truth.

Delta / Unity Catalog
    Bronze, Silver, and Gold analytical data products.

Unity Catalog Volumes
    Unstructured source files such as listing images.

Databricks AI Search
    Semantic retrieval index built from Gold search documents.

Important
---------
This module defines object names only.

An object being registered here does NOT mean that it has been:
    - created,
    - populated,
    - tested,
    - validated,
    - or deployed.

Do not place Lakebase PostgreSQL operational table names in this registry.
Those belong to the operational / Agent database layer.

Runtime behavior, thresholds, model endpoints, API settings, scoring weights,
timeouts, and other tunable configuration belong in `config/settings.py`.
"""


# =============================================================================
# Unity Catalog namespaces
# =============================================================================

CATALOG = "bootcamp_students"

BRONZE_SCHEMA = "shipp_bronze"
SILVER_SCHEMA = "shipp_silver"
GOLD_SCHEMA = "shipp_gold"


# =============================================================================
# Bronze
# =============================================================================
#
# Bronze preserves raw history and raw enrichment responses.
#
# It should remain as close as practical to source-system truth so downstream
# transformations can be reproduced, debugged, and audited.
# =============================================================================


# -----------------------------------------------------------------------------
# Lakebase CDC history
# -----------------------------------------------------------------------------

# Raw Listing change history captured incrementally from Lakebase.
BRONZE_LISTINGS_HISTORY = (
    f"{CATALOG}.{BRONZE_SCHEMA}.lb_listings_history"
)

# Raw Request change history captured incrementally from Lakebase.
BRONZE_REQUESTS_HISTORY = (
    f"{CATALOG}.{BRONZE_SCHEMA}.lb_requests_history"
)

# Raw Listing-file metadata history captured incrementally from Lakebase.
BRONZE_LISTING_FILES_HISTORY = (
    f"{CATALOG}.{BRONZE_SCHEMA}.lb_listing_files_history"
)


# -----------------------------------------------------------------------------
# Third-party API enrichment
# -----------------------------------------------------------------------------

# Raw OpenRouteService Matrix request / response evidence.
#
# Canonical producer:
#   notebooks/development/31_ors_route_enrichment.ipynb
#
# Canonical consumer:
#   notebooks/development/32_silver_routes.ipynb
#
# The normalized route product belongs in SILVER_ROUTES.
BRONZE_ROUTE_RESPONSES = (
    f"{CATALOG}.{BRONZE_SCHEMA}.ors_route_responses"
)


# -----------------------------------------------------------------------------
# Vision / unstructured enrichment
# -----------------------------------------------------------------------------

# Raw Vision model responses.
#
# Canonical producer:
#   notebooks/rag/51_vision_enrichment.ipynb
#
# Canonical consumer:
#   notebooks/rag/52_silver_listing_content.ipynb
#
# Bronze retains the raw model response so Vision processing remains auditable.
BRONZE_VISION_RESPONSES = (
    f"{CATALOG}.{BRONZE_SCHEMA}.vision_responses"
)


# =============================================================================
# Unity Catalog Volume — unstructured listing images
# =============================================================================

# Three-part Unity Catalog Volume name.
#
# Use when interacting with Unity Catalog metadata.
LISTING_IMAGES_VOLUME_NAME = (
    f"{CATALOG}.{BRONZE_SCHEMA}.listing_images"
)

# Databricks filesystem path to the same Volume.
#
# Use when Spark / Python code needs to read the actual image files.
LISTING_IMAGES_VOLUME = (
    f"/Volumes/{CATALOG}/{BRONZE_SCHEMA}/listing_images"
)


# =============================================================================
# Silver
# =============================================================================
#
# Silver contains trusted, normalized products used by downstream business
# logic. Current-state tables are reconstructed from Bronze CDC using SHIPP's
# delete-aware event ordering contract.
# =============================================================================


# -----------------------------------------------------------------------------
# Trusted operational current state
# -----------------------------------------------------------------------------

# Trusted current Listing state reconstructed from Bronze Listing CDC.
SILVER_LISTINGS = (
    f"{CATALOG}.{SILVER_SCHEMA}.silver_listings"
)

# Trusted current Request state reconstructed from Bronze Request CDC.
SILVER_REQUESTS = (
    f"{CATALOG}.{SILVER_SCHEMA}.silver_requests"
)


# -----------------------------------------------------------------------------
# Matching preparation
# -----------------------------------------------------------------------------

# Eligible Request / Listing pairs before third-party routing enrichment.
SILVER_CANDIDATE_PAIRS = (
    f"{CATALOG}.{SILVER_SCHEMA}.silver_candidate_pairs"
)

# Normalized route distance and duration by canonical route key.
#
# Source:
#   BRONZE_ROUTE_RESPONSES
#
# Consumer:
#   GOLD_CANDIDATE_MATCHES
SILVER_ROUTES = (
    f"{CATALOG}.{SILVER_SCHEMA}.silver_routes"
)


# -----------------------------------------------------------------------------
# Unstructured / RAG preparation
# -----------------------------------------------------------------------------

# Current Listing-file metadata reconciled against real files in the Volume.
#
# Canonical producer:
#   notebooks/rag/50_silver_listing_files.ipynb
SILVER_LISTING_FILES = (
    f"{CATALOG}.{SILVER_SCHEMA}.silver_listing_files"
)

# Trusted Listing content combining structured Listing text and optional
# image-derived enrichment.
#
# Canonical producer:
#   notebooks/rag/52_silver_listing_content.ipynb
#
# Canonical consumer:
#   notebooks/rag/53_gold_listing_search_docs.ipynb
SILVER_LISTING_CONTENT = (
    f"{CATALOG}.{SILVER_SCHEMA}.silver_listing_content"
)

# Semantic retrieval scores produced by Notebook 56.
#
# This table belongs to the optional / future Gold v2 semantic-scoring path.
# Current validated Gold v1 does NOT depend on this table.
SILVER_SEMANTIC_SCORES = (
    f"{CATALOG}.{SILVER_SCHEMA}.silver_semantic_scores"
)


# =============================================================================
# Gold
# =============================================================================
#
# Gold contains business-facing data products consumed by applications,
# analytics, retrieval, and the Agent.
# =============================================================================


# -----------------------------------------------------------------------------
# Marketplace matching
# -----------------------------------------------------------------------------

# Trusted ranked candidate matches.
#
# Consumers include:
#   - SHIPP Agent
#   - SHIPP application
#   - validation / analytics
GOLD_CANDIDATE_MATCHES = (
    f"{CATALOG}.{GOLD_SCHEMA}.gold_candidate_matches"
)


# -----------------------------------------------------------------------------
# AI Search source documents
# -----------------------------------------------------------------------------

# Search-ready Listing documents.
#
# Canonical producer:
#   notebooks/rag/53_gold_listing_search_docs.ipynb
#
# Canonical consumer:
#   Databricks AI Search Delta Sync index
GOLD_LISTING_SEARCH_DOCS = (
    f"{CATALOG}.{GOLD_SCHEMA}.gold_listing_search_docs"
)


# -----------------------------------------------------------------------------
# Analytics
# -----------------------------------------------------------------------------

# Stage 13 marketplace analytics product.
#
# Registration here defines the canonical target name only.
#
# It does NOT imply that the table has already been:
#   - implemented,
#   - populated,
#   - tested,
#   - or validated.
GOLD_MARKETPLACE_METRICS = (
    f"{CATALOG}.{GOLD_SCHEMA}.gold_marketplace_metrics"
)


# -----------------------------------------------------------------------------
# RAG evaluation
# -----------------------------------------------------------------------------

# Retrieval-evaluation evidence written by Notebook 55.
#
# Includes metrics such as Hit@K, reciprocal rank, and retrieval latency.
RAG_EVAL_RESULTS = (
    f"{CATALOG}.{GOLD_SCHEMA}.rag_eval_results"
)


# -----------------------------------------------------------------------------
# Pipeline observability
# -----------------------------------------------------------------------------

# Shared pipeline-run and observability log.
#
# Used for pipeline execution evidence and timing / status tracking.
PIPELINE_RUN_LOG = (
    f"{CATALOG}.{GOLD_SCHEMA}.pipeline_run_log"
)


# =============================================================================
# Databricks AI Search
# =============================================================================

# Delta Sync AI Search index built from GOLD_LISTING_SEARCH_DOCS.
#
# This is a Databricks AI Search resource, NOT a Delta table.
VS_INDEX_NAME = (
    f"{CATALOG}.{GOLD_SCHEMA}.gold_listing_search_docs_index"
)


# =============================================================================
# Convenience registry — Delta tables only
# =============================================================================
#
# This registry intentionally contains only Delta table products.
#
# Unity Catalog Volumes and Databricks AI Search indexes are excluded because
# they are different resource types and should not be treated as Delta tables.
# =============================================================================

TABLES = {
    # -------------------------------------------------------------------------
    # Bronze
    # -------------------------------------------------------------------------
    "bronze_listings_history": BRONZE_LISTINGS_HISTORY,
    "bronze_requests_history": BRONZE_REQUESTS_HISTORY,
    "bronze_listing_files_history": BRONZE_LISTING_FILES_HISTORY,
    "bronze_route_responses": BRONZE_ROUTE_RESPONSES,
    "bronze_vision_responses": BRONZE_VISION_RESPONSES,

    # -------------------------------------------------------------------------
    # Silver
    # -------------------------------------------------------------------------
    "silver_listings": SILVER_LISTINGS,
    "silver_requests": SILVER_REQUESTS,
    "silver_candidate_pairs": SILVER_CANDIDATE_PAIRS,
    "silver_routes": SILVER_ROUTES,
    "silver_listing_files": SILVER_LISTING_FILES,
    "silver_listing_content": SILVER_LISTING_CONTENT,
    "silver_semantic_scores": SILVER_SEMANTIC_SCORES,

    # -------------------------------------------------------------------------
    # Gold
    # -------------------------------------------------------------------------
    "gold_candidate_matches": GOLD_CANDIDATE_MATCHES,
    "gold_listing_search_docs": GOLD_LISTING_SEARCH_DOCS,
    "gold_marketplace_metrics": GOLD_MARKETPLACE_METRICS,
    "rag_eval_results": RAG_EVAL_RESULTS,

    # -------------------------------------------------------------------------
    # Observability
    # -------------------------------------------------------------------------
    "pipeline_run_log": PIPELINE_RUN_LOG,
}
CATALOG = "bootcamp_students"

BRONZE_SCHEMA = "shipp_bronze"
SILVER_SCHEMA = "shipp_silver"
GOLD_SCHEMA = "shipp_gold"


# =============================================================================
# Bronze
# =============================================================================

# Structured CDC history from Lakebase.
BRONZE_LISTINGS_HISTORY = (
    f"{CATALOG}.{BRONZE_SCHEMA}.lb_listings_history"
)

BRONZE_REQUESTS_HISTORY = (
    f"{CATALOG}.{BRONZE_SCHEMA}.lb_requests_history"
)

# Listing-file metadata CDC from Lakebase.
BRONZE_LISTING_FILES_HISTORY = (
    f"{CATALOG}.{BRONZE_SCHEMA}.lb_listing_files_history"
)

# Third-party API enrichment:
# OpenRouteService is configured in config/settings.py.
# Raw request/response payloads are preserved here as semi-structured JSON.
BRONZE_ROUTE_RESPONSES = (
    f"{CATALOG}.{BRONZE_SCHEMA}.ors_route_responses"
)

# Raw Vision model responses.
BRONZE_VISION_RESPONSES = (
    f"{CATALOG}.{BRONZE_SCHEMA}.vision_responses"
)


# =============================================================================
# Unity Catalog Volume — unstructured images
# =============================================================================

LISTING_IMAGES_VOLUME_NAME = (
    f"{CATALOG}.{BRONZE_SCHEMA}.listing_images"
)

LISTING_IMAGES_VOLUME = (
    f"/Volumes/{CATALOG}/{BRONZE_SCHEMA}/listing_images"
)


# =============================================================================
# Silver
# =============================================================================

SILVER_LISTINGS = (
    f"{CATALOG}.{SILVER_SCHEMA}.silver_listings"
)

SILVER_REQUESTS = (
    f"{CATALOG}.{SILVER_SCHEMA}.silver_requests"
)

SILVER_CANDIDATE_PAIRS = (
    f"{CATALOG}.{SILVER_SCHEMA}.silver_candidate_pairs"
)

SILVER_ROUTES = (
    f"{CATALOG}.{SILVER_SCHEMA}.silver_routes"
)

# Current listing-file metadata reconciled with real files in the Volume.
SILVER_LISTING_FILES = (
    f"{CATALOG}.{SILVER_SCHEMA}.silver_listing_files"
)

# Trusted listing text + image-derived content.
SILVER_LISTING_CONTENT = (
    f"{CATALOG}.{SILVER_SCHEMA}.silver_listing_content"
)

# Semantic retrieval scores used only by future Gold v2.
SILVER_SEMANTIC_SCORES = (
    f"{CATALOG}.{SILVER_SCHEMA}.silver_semantic_scores"
)


# =============================================================================
# Gold
# =============================================================================

GOLD_CANDIDATE_MATCHES = (
    f"{CATALOG}.{GOLD_SCHEMA}.gold_candidate_matches"
)

GOLD_LISTING_SEARCH_DOCS = (
    f"{CATALOG}.{GOLD_SCHEMA}.gold_listing_search_docs"
)

GOLD_MARKETPLACE_METRICS = (
    f"{CATALOG}.{GOLD_SCHEMA}.gold_marketplace_metrics"
)

RAG_EVAL_RESULTS = (
    f"{CATALOG}.{GOLD_SCHEMA}.rag_eval_results"
)

PIPELINE_RUN_LOG = (
    f"{CATALOG}.{GOLD_SCHEMA}.pipeline_run_log"
)


# =============================================================================
# Databricks AI Search
# =============================================================================

VS_INDEX_NAME = (
    f"{CATALOG}.{GOLD_SCHEMA}.gold_listing_search_docs_index"
)


# =============================================================================
# Convenience registry
# =============================================================================

TABLES = {
    # Bronze
    "bronze_listings_history": BRONZE_LISTINGS_HISTORY,
    "bronze_requests_history": BRONZE_REQUESTS_HISTORY,
    "bronze_listing_files_history": BRONZE_LISTING_FILES_HISTORY,
    "bronze_route_responses": BRONZE_ROUTE_RESPONSES,
    "bronze_vision_responses": BRONZE_VISION_RESPONSES,

    # Silver
    "silver_listings": SILVER_LISTINGS,
    "silver_requests": SILVER_REQUESTS,
    "silver_candidate_pairs": SILVER_CANDIDATE_PAIRS,
    "silver_routes": SILVER_ROUTES,
    "silver_listing_files": SILVER_LISTING_FILES,
    "silver_listing_content": SILVER_LISTING_CONTENT,
    "silver_semantic_scores": SILVER_SEMANTIC_SCORES,

    # Gold
    "gold_candidate_matches": GOLD_CANDIDATE_MATCHES,
    "gold_listing_search_docs": GOLD_LISTING_SEARCH_DOCS,
    "gold_marketplace_metrics": GOLD_MARKETPLACE_METRICS,
    "rag_eval_results": RAG_EVAL_RESULTS,

    # Observability
    "pipeline_run_log": PIPELINE_RUN_LOG,
}

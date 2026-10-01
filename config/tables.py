CATALOG = "bootcamp_students"

BRONZE_SCHEMA = "shipp_bronze"
SILVER_SCHEMA = "shipp_silver"
GOLD_SCHEMA = "shipp_gold"


# -------------------------------------------------------------------
# Bronze
# -------------------------------------------------------------------

BRONZE_LISTINGS_HISTORY = (
    f"{CATALOG}.{BRONZE_SCHEMA}.lb_listings_history"
)

BRONZE_REQUESTS_HISTORY = (
    f"{CATALOG}.{BRONZE_SCHEMA}.lb_requests_history"
)

BRONZE_ROUTE_RESPONSES = (
    f"{CATALOG}.{BRONZE_SCHEMA}.ors_route_responses"
)


# -------------------------------------------------------------------
# Silver
# -------------------------------------------------------------------

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


# -------------------------------------------------------------------
# Gold
# -------------------------------------------------------------------

GOLD_CANDIDATE_MATCHES = (
    f"{CATALOG}.{GOLD_SCHEMA}.gold_candidate_matches"
)

GOLD_LISTING_SEARCH_DOCS = (
    f"{CATALOG}.{GOLD_SCHEMA}.gold_listing_search_docs"
)

GOLD_MARKETPLACE_METRICS = (
    f"{CATALOG}.{GOLD_SCHEMA}.gold_marketplace_metrics"
)

PIPELINE_RUN_LOG = (
    f"{CATALOG}.{GOLD_SCHEMA}.pipeline_run_log"
)


# -------------------------------------------------------------------
# Convenience registry
# -------------------------------------------------------------------

TABLES = {
    "bronze_listings_history": BRONZE_LISTINGS_HISTORY,
    "bronze_requests_history": BRONZE_REQUESTS_HISTORY,
    "bronze_route_responses": BRONZE_ROUTE_RESPONSES,

    "silver_listings": SILVER_LISTINGS,
    "silver_requests": SILVER_REQUESTS,
    "silver_candidate_pairs": SILVER_CANDIDATE_PAIRS,
    "silver_routes": SILVER_ROUTES,

    "gold_candidate_matches": GOLD_CANDIDATE_MATCHES,
    "gold_listing_search_docs": GOLD_LISTING_SEARCH_DOCS,
    "gold_marketplace_metrics": GOLD_MARKETPLACE_METRICS,

    "pipeline_run_log": PIPELINE_RUN_LOG,
}

# CATALOG = "bootcamp_students"

# BRONZE_SCHEMA = "shipp_bronze"
# SILVER_SCHEMA = "shipp_silver"
# GOLD_SCHEMA = "shipp_gold"

# # Bronze history
# BRONZE_LISTINGS_HISTORY = f"{CATALOG}.{BRONZE_SCHEMA}.lb_listings_history"
# BRONZE_REQUESTS_HISTORY = f"{CATALOG}.{BRONZE_SCHEMA}.lb_requests_history"

# # Silver current state
# SILVER_LISTINGS = f"{CATALOG}.{SILVER_SCHEMA}.silver_listings"
# SILVER_REQUESTS = f"{CATALOG}.{SILVER_SCHEMA}.silver_requests"
# SILVER_ROUTES = f"{CATALOG}.{SILVER_SCHEMA}.silver_routes"

# # Gold
# GOLD_CANDIDATE_MATCHES = f"{CATALOG}.{GOLD_SCHEMA}.gold_candidate_matches"
# GOLD_LISTING_SEARCH_DOCS = f"{CATALOG}.{GOLD_SCHEMA}.gold_listing_search_docs"
# GOLD_MARKETPLACE_METRICS = f"{CATALOG}.{GOLD_SCHEMA}.gold_marketplace_metrics"
# AI Search
VS_INDEX_NAME = f"{CATALOG}.{GOLD_SCHEMA}.gold_listing_search_docs_index"

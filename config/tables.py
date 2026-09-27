CATALOG = "bootcamp_students"

BRONZE_SCHEMA = "shipp_bronze"
SILVER_SCHEMA = "shipp_silver"
GOLD_SCHEMA = "shipp_gold"

# Bronze history
BRONZE_LISTINGS_HISTORY = f"{CATALOG}.{BRONZE_SCHEMA}.lb_listings_history"
BRONZE_REQUESTS_HISTORY = f"{CATALOG}.{BRONZE_SCHEMA}.lb_requests_history"

# Silver current state
SILVER_LISTINGS = f"{CATALOG}.{SILVER_SCHEMA}.silver_listings"
SILVER_REQUESTS = f"{CATALOG}.{SILVER_SCHEMA}.silver_requests"
SILVER_ROUTES = f"{CATALOG}.{SILVER_SCHEMA}.silver_routes"

# Gold
GOLD_CANDIDATE_MATCHES = f"{CATALOG}.{GOLD_SCHEMA}.gold_candidate_matches"
GOLD_LISTING_SEARCH_DOCS = f"{CATALOG}.{GOLD_SCHEMA}.gold_listing_search_docs"
GOLD_MARKETPLACE_METRICS = f"{CATALOG}.{GOLD_SCHEMA}.gold_marketplace_metrics"

"""Tunable settings for the SHIPP pipeline. Change values here, never inside notebooks.

Status vocabularies mirror the Lakebase CHECK constraints set by
lakebase/migrations/002 (listings) and 003 (requests). If a migration changes them,
change them here in the same pull request.
"""

# --- Lakebase status vocabularies -------------------------------------------------
LISTING_STATUSES = ["DRAFT", "AVAILABLE", "UNAVAILABLE", "WITHDRAWN", "EXPIRED"]
REQUEST_STATUSES = ["OPEN", "MATCHES_AVAILABLE", "ITEM_SAVED", "CLOSED"]

ELIGIBLE_LISTING_STATUSES = ["AVAILABLE"]
ELIGIBLE_REQUEST_STATUSES = ["OPEN", "MATCHES_AVAILABLE"]

# --- Candidate pairs (Stage 6) ------------------------------------------------------
MAX_STRAIGHT_LINE_KM = 100.0   # haversine pre-filter; protects the ORS quota

# --- OpenRouteService (Stage 7) -----------------------------------------------------
ORS_SECRET_SCOPE = "shipp"
ORS_SECRET_KEY = "ors-api-key"
# Endpoint the team tested. Documented public alternative: https://api.openrouteservice.org/v2/matrix/
ORS_MATRIX_BASE = "https://api.heigit.org/openrouteservice/v2/matrix/"
ORS_PROFILE = "driving-car"
ORS_MAX_SOURCES_PER_CALL = 50
ORS_MAX_CALLS_PER_RUN = 100          # check the real daily quota in the ORS dashboard
ORS_MIN_SECONDS_BETWEEN_CALLS = 1.6  # < 40 requests / minute
ORS_MAX_RETRIES = 4
ORS_BACKOFF_BASE_SECONDS = 2.0       # 2 s, 4 s, 8 s, 16 s
ORS_TIMEOUT_SECONDS = 20
ORS_RETRYABLE_STATUS = (429, 500, 502, 503, 504)

ROUTE_KEY_DECIMALS = 4               # route cache key precision (~11 m)

# --- Gold scoring (Stage 8) ---------------------------------------------------------
# One scoring contract for the whole repo. README and implementation plan point here.
SCORING = {
    "version": "v1-structured",
    "weights": {"distance": 0.50, "timing": 0.30, "condition": 0.20},
    # v2, once AI Search exists: distance 0.35, semantic 0.35, timing 0.20, condition 0.10
    "max_route_km": 50.0,
    "timing_full_score_days": 7,
    "condition_scores": {"NEW": 1.0, "LIKE_NEW": 0.9, "GOOD": 0.75, "FAIR": 0.5},
    "condition_default": 0.3,
    "top_n_per_request": 10,
}

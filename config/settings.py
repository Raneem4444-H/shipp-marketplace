"""Tunable settings for the SHIPP pipeline.

Shared configuration for Silver, candidate pairs, ORS, Gold scoring,
unstructured content, Vision, retrieval, and AI Search.

Change values here rather than hardcoding them inside notebooks.
"""


# =============================================================================
# Lakebase status vocabularies
# =============================================================================

LISTING_STATUSES = [
    "DRAFT",
    "AVAILABLE",
    "UNAVAILABLE",
    "WITHDRAWN",
    "EXPIRED",
]

REQUEST_STATUSES = [
    "OPEN",
    "MATCHES_AVAILABLE",
    "ITEM_SAVED",
    "CLOSED",
]

ELIGIBLE_LISTING_STATUSES = [
    "AVAILABLE",
]

ELIGIBLE_REQUEST_STATUSES = [
    "OPEN",
    "MATCHES_AVAILABLE",
]


# =============================================================================
# Candidate pairs
# =============================================================================

# Haversine pre-filter before ORS.
# Prevents obviously distant candidates from consuming ORS quota.
MAX_STRAIGHT_LINE_KM = 100.0


# =============================================================================
# OpenRouteService
# =============================================================================

ORS_SECRET_SCOPE = "shipp"
ORS_SECRET_KEY = "ors-api-key"

# Endpoint already used by SHIPP.
ORS_MATRIX_BASE = "https://api.heigit.org/openrouteservice/v2/matrix/"

ORS_PROFILE = "driving-car"

# Request / quota controls.
ORS_MAX_SOURCES_PER_CALL = 50
ORS_MAX_CALLS_PER_RUN = 100
ORS_MIN_SECONDS_BETWEEN_CALLS = 1.6

# Retry / failure policy.
ORS_MAX_RETRIES = 4
ORS_BACKOFF_BASE_SECONDS = 2.0
ORS_TIMEOUT_SECONDS = 20

ORS_RETRYABLE_STATUS = (
    429,
    500,
    502,
    503,
    504,
)

# Coordinate precision used for route cache keys.
ROUTE_KEY_DECIMALS = 4


# =============================================================================
# Gold scoring — current validated v1 contract
# =============================================================================

SCORING = {
    "version": "v1-structured",

    "weights": {
        "distance": 0.50,
        "timing": 0.30,
        "condition": 0.20,
    },

    "max_route_km": 50.0,

    "timing_full_score_days": 7,

    "condition_scores": {
        "NEW": 1.0,
        "LIKE_NEW": 0.9,
        "GOOD": 0.75,
        "FAIR": 0.5,
    },

    "condition_default": 0.3,

    "top_n_per_request": 10,
}


# =============================================================================
# Listing images / unstructured content
# =============================================================================

# IMPORTANT:
# This must remain a dictionary.
# rag/vision.py uses IMAGE_MIME_TYPES.get(extension).
IMAGE_MIME_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


# =============================================================================
# Text normalization
# =============================================================================

TEXT_MAX_TITLE_CHARS = 200
TEXT_MAX_DESCRIPTION_CHARS = 2000


# =============================================================================
# Vision enrichment — v3
# =============================================================================

VISION_PROMPT_VERSION = "v3"

VISION_ENDPOINT = "databricks-gemini-3-5-flash"

# Per-run quota / throttling.
VISION_MAX_CALLS_PER_RUN = 10
VISION_MIN_SECONDS_BETWEEN_CALLS = 1.0

# Input/output limits.
VISION_MAX_IMAGE_BYTES = 5 * 1024 * 1024
VISION_MAX_DESCRIPTION_CHARS = 600
VISION_MAX_LABELS = 10
VISION_MAX_TOKENS = 600

# HTTP behavior.
VISION_TIMEOUT_SECONDS = 30

VISION_MAX_RETRIES = 3
VISION_BACKOFF_BASE_SECONDS = 2.0

VISION_RETRYABLE_STATUS = (
    429,
    500,
    502,
    503,
    504,
)

# silver_listing_content vocabulary.
VISION_STATUSES = (
    "OK",
    "FAILED",
    "PENDING",
    "NO_IMAGE",
    "FILE_MISSING",
)


# =============================================================================
# Search / retrieval
# =============================================================================

SEARCH_DEFAULT_K = 5
SEARCH_MAX_K = 10

SEARCH_MAX_QUERY_CHARS = 500
SEARCH_SNIPPET_CHARS = 400

SEARCH_TEXT_COLUMN = "search_text"

SEARCH_RETURN_COLUMNS = [
    "listing_id",
    "title",
    "category",
    "condition",
    "status",
    "search_text",
]


# =============================================================================
# Databricks AI Search index synchronization
# =============================================================================

# Poll frequency while waiting for a triggered Delta Sync.
INDEX_SYNC_POLL_SECONDS = 10

# Maximum wait for the Vector Search index to become ready.
INDEX_SYNC_TIMEOUT_SECONDS = 900
# -----------------------------------------------------------------------------
# Text normalization
# -----------------------------------------------------------------------------

TEXT_MAX_TITLE_CHARS = 200
TEXT_MAX_DESCRIPTION_CHARS = 2000


# -----------------------------------------------------------------------------
# Vision enrichment
# -----------------------------------------------------------------------------

VISION_PROMPT_VERSION = "v3"

VISION_ENDPOINT = "databricks-gemini-3-5-flash"
VISION_MAX_CALLS_PER_RUN = 10
VISION_MIN_SECONDS_BETWEEN_CALLS = 1.0

VISION_MAX_IMAGE_BYTES = 5 * 1024 * 1024
VISION_MAX_DESCRIPTION_CHARS = 600
VISION_MAX_LABELS = 10
VISION_MAX_TOKENS = 600

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


# -----------------------------------------------------------------------------
# Search / retrieval
# -----------------------------------------------------------------------------

SEARCH_DEFAULT_K = 5
SEARCH_MAX_K = 10
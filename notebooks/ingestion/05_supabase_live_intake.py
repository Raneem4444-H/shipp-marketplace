# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# ============================================================
# SHIPP — LIVE SUPABASE DONOR / REQUESTER INGESTION
#
# SOURCE:
#   Supabase REST API (PostgREST) over HTTPS
#
# PROCESSING:
#   Paged API read -> PySpark DataFrames
#   -> PySpark normalization
#   -> PySpark data quality
#   -> PySpark deduplication
#
# TARGET:
#   bootcamp_students.shipp_bronze.supabase_donor_intake
#   bootcamp_students.shipp_bronze.supabase_requester_intake
#
# IMPORTANT:
#   This notebook DOES NOT replace:
#   - Lakebase
#   - Lakebase CDC
#   - existing Bronze CDC tables
#   - Silver
#   - Gold
#   - ORS
#   - AI Search
#   - Agent
# ============================================================


# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import AclPermission
from databricks.sdk.errors import ResourceAlreadyExists

w = WorkspaceClient()

try:
    w.secrets.create_scope(scope="shipp_supabase")
except ResourceAlreadyExists:
    pass  # scope already exists

w.secrets.put_secret(
    scope="shipp_supabase",
    key="supabase_secret_key",
    string_value="PASTE_SB_SECRET_KEY_HERE",
)

# Let your teammate and scheduled jobs read it (read only).
w.secrets.put_acl(
    scope="shipp_supabase",
    principal="users",
    permission=AclPermission.READ,
)

print(sorted(s.key for s in dbutils.secrets.list("shipp_supabase")))
"""/*['supabase_secret_key'] */
Let me analyze the error in Cell 2:

Error: ResourceAlreadyExists: Scope shipp_supabase already exists!

The cell tries to create a secret scope shipp_supabase with w.secrets.create_scope(scope="shipp_supabase"), but it already exists. This is a straightforward fix - wrap the create_scope call in a try/except to handle the case where the scope already exists.

Looking at the cell more carefully:

It creates a scope shipp_supabase Then puts a secret supabase_secret_key into it Sets ACL permissions and lists the keys
The fix should be minimal - just catch the ResourceAlreadyExists exception when creating the scope, and let the rest of the operations proceed normally. I also notice Cell 4 uses a different scope name ("shipp" instead of "shipp_supabase"), but I'll focus on fixing the immediate error in Cell 2.

I'll wrap the scope creation in a try/except block to handle the exception gracefully.

The error is ResourceAlreadyExists: Scope shipp_supabase already exists! — the scope was already created in a prior run, and create_scope doesn't support "if not exists" semantics. The minimal fix is to catch that specific exception and continue.

Now let me verify the edit was applied and run the cell.

Edit confirmed. Running the cell now.

The edit is applied. The fix wraps create_scope in a try/except ResourceAlreadyExists block so it gracefully handles the case where the scope already exists from a prior run, while still proceeding to put_secret, put_acl, and the key listing.

Please run the cell manually to confirm it succeeds.



Run Cell 2

"""


# COMMAND ----------

# ============================================================
# GATE 0 — IMPORTS / PYSPARK
# ============================================================

import json
import time
from datetime import date, datetime
from typing import Any

import requests

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T


print("==============================================")
print("SHIPP — LIVE SUPABASE INTAKE (REST API)")
print("==============================================")
print("requests version:", requests.__version__)
print("Spark version:", spark.version)

print()
print("PASS Gate 0 — PYSPARK runtime ready")

"""==============================================
SHIPP — LIVE SUPABASE INTAKE (REST API)
==============================================
requests version: 2.32.5
Spark version: 4.2.0

PASS Gate 0 — PYSPARK runtime ready"""


# COMMAND ----------

# ============================================================
# GATE 1 — CONFIGURATION
# ============================================================

SECRET_SCOPE = "shipp_supabase"
SUPABASE_KEY_SECRET = "supabase_secret_key"

# Project URL is not a secret. The API key is, and is read from the scope.
SUPABASE_URL = "https://lwsotpufqjovxotlqdqj.supabase.co"

# Table names as exposed by the Supabase Data API (public schema).
DONOR_SOURCE_TABLE = "donor_intake"
REQUESTER_SOURCE_TABLE = "requester_intake"

PAGE_SIZE = 1000
HTTP_TIMEOUT_SECONDS = 30
MAX_RETRIES = 4
BACKOFF_SECONDS = 2
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

DONOR_BRONZE = (
    "bootcamp_students.shipp_bronze.supabase_donor_intake"
)

REQUESTER_BRONZE = (
    "bootcamp_students.shipp_bronze.supabase_requester_intake"
)


try:
    SUPABASE_API_KEY = dbutils.secrets.get(
        scope=SECRET_SCOPE,
        key=SUPABASE_KEY_SECRET,
    ).strip()
except Exception as exc:
    # Names only. Secret values are never printed.
    available = sorted(
        s.key for s in dbutils.secrets.list(SECRET_SCOPE)
    )
    raise AssertionError(
        f"BLOCKED — secret '{SECRET_SCOPE}/{SUPABASE_KEY_SECRET}' "
        f"not readable ({type(exc).__name__}). "
        f"Keys in scope '{SECRET_SCOPE}': {available}"
    )


assert SUPABASE_API_KEY, (
    f"BLOCKED — Databricks secret "
    f"'{SECRET_SCOPE}/{SUPABASE_KEY_SECRET}' is empty."
)


print("Supabase API base      :", f"{SUPABASE_URL}/rest/v1")
print("Source donor table     :", DONOR_SOURCE_TABLE)
print("Source requester table :", REQUESTER_SOURCE_TABLE)

print("Target donor Bronze    :", DONOR_BRONZE)
print("Target requester Bronze:", REQUESTER_BRONZE)

print()
print(
    "PASS Gate 1 — Supabase API key loaded securely "
    "(secret value not printed)"
)
"""Supabase API base      : https://lwsotpufqjovxotlqdqj.supabase.co/rest/v1
Source donor table     : donor_intake
Source requester table : requester_intake
Target donor Bronze    : bootcamp_students.shipp_bronze.supabase_donor_intake
Target requester Bronze: bootcamp_students.shipp_bronze.supabase_requester_intake

PASS Gate 1 — Supabase API key loaded securely (secret value not printed)"""

# COMMAND ----------

from databricks.sdk import WorkspaceClient

WorkspaceClient().secrets.put_secret(
    scope="shipp_supabase",
    key="supabase_secret_key",
    string_value="sb_secret_AbC123xyzExample",
)

print("saved")

# COMMAND ----------

print("length            :", len(SUPABASE_API_KEY))
print("starts sb_secret_ :", SUPABASE_API_KEY.startswith("sb_secret_"))
print("is placeholder    :", SUPABASE_API_KEY == "PASTE_SB_SECRET_KEY_HERE")
print("has dots (masked) :", "•" in SUPABASE_API_KEY or "..." in SUPABASE_API_KEY)

"""length            : 24
starts sb_secret_ : False
is placeholder    : True
has dots (masked) : False"""

# COMMAND ----------

# ============================================================
# GATE 2 — READ LIVE SUPABASE REST API
# ============================================================

ALLOWED_SOURCE_TABLES = {
    DONOR_SOURCE_TABLE,
    REQUESTER_SOURCE_TABLE,
}


def api_get(
    url: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """One GET with retry/backoff. Raises with a readable reason."""

    last_error = "no attempt made"

    for attempt in range(1, MAX_RETRIES + 1):

        try:
            response = requests.get(
                url,
                params=params,
                headers={
                    "apikey": SUPABASE_API_KEY,
                    "Accept": "application/json",
                },
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            status = response.status_code
            body = response.text

        except requests.RequestException as exc:
            status = -1
            body = type(exc).__name__

        if status == 200:
            return response.json()

        last_error = f"HTTP {status}: {body[:300]}"

        retryable = status == -1 or status in RETRYABLE_STATUS

        if retryable and attempt < MAX_RETRIES:
            wait = BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(
                f"  GET {url} -> {status}, "
                f"retry {attempt}/{MAX_RETRIES} in {wait}s"
            )
            time.sleep(wait)
            continue

        break

    raise RuntimeError(
        f"FAIL — Supabase API call to {url} failed. {last_error}\n"
        "401/403 -> wrong API key in the secret scope.\n"
        "404     -> table missing, or not exposed in the public schema."
    )


def fetch_supabase_table(
    table_name: str,
) -> list[dict[str, Any]]:

    if table_name not in ALLOWED_SOURCE_TABLES:
        raise ValueError(
            f"Unexpected source table: {table_name}"
        )

    url = f"{SUPABASE_URL}/rest/v1/{table_name}"

    rows: list[dict[str, Any]] = []
    offset = 0

    while True:

        page = api_get(
            url,
            {
                "select": "*",
                "order": "created_at.asc",
                "limit": PAGE_SIZE,
                "offset": offset,
            },
        )

        rows.extend(page)

        if len(page) < PAGE_SIZE:
            return rows

        offset += PAGE_SIZE


donor_rows = fetch_supabase_table(
    DONOR_SOURCE_TABLE
)

requester_rows = fetch_supabase_table(
    REQUESTER_SOURCE_TABLE
)


print(
    "Live donor rows:",
    len(donor_rows),
)

print(
    "Live requester rows:",
    len(requester_rows),
)


assert donor_rows, (
    "FAIL — Supabase donor_intake returned zero rows."
)

assert requester_rows, (
    "FAIL — Supabase requester_intake returned zero rows."
)


print()
print(
    "PASS Gate 2 — live Supabase donor/requester "
    "data received over the REST API"
)


# COMMAND ----------

# ============================================================
# GATE 3 — EXPLICIT PYSPARK SCHEMAS
# ============================================================

DONOR_SCHEMA = T.StructType(
    [
        T.StructField(
            "external_listing_id",
            T.StringType(),
            False,
        ),
        T.StructField(
            "donor_id",
            T.StringType(),
            False,
        ),
        T.StructField(
            "title",
            T.StringType(),
            False,
        ),
        T.StructField(
            "description",
            T.StringType(),
            True,
        ),
        T.StructField(
            "category",
            T.StringType(),
            False,
        ),
        T.StructField(
            "condition",
            T.StringType(),
            False,
        ),
        T.StructField(
            "location",
            T.StringType(),
            False,
        ),
        T.StructField(
            "latitude",
            T.DoubleType(),
            False,
        ),
        T.StructField(
            "longitude",
            T.DoubleType(),
            False,
        ),
        T.StructField(
            "available_until",
            T.StringType(),
            False,
        ),
        T.StructField(
            "created_at",
            T.StringType(),
            True,
        ),
    ]
)


REQUESTER_SCHEMA = T.StructType(
    [
        T.StructField(
            "external_request_id",
            T.StringType(),
            False,
        ),
        T.StructField(
            "requester_id",
            T.StringType(),
            False,
        ),
        T.StructField(
            "request_text",
            T.StringType(),
            False,
        ),
        T.StructField(
            "category",
            T.StringType(),
            False,
        ),
        T.StructField(
            "location",
            T.StringType(),
            False,
        ),
        T.StructField(
            "latitude",
            T.DoubleType(),
            False,
        ),
        T.StructField(
            "longitude",
            T.DoubleType(),
            False,
        ),
        T.StructField(
            "need_by_date",
            T.StringType(),
            False,
        ),
        T.StructField(
            "created_at",
            T.StringType(),
            True,
        ),
    ]
)


def serialize_values(
    rows: list[dict[str, Any]],
    schema: T.StructType,
) -> list[dict[str, Any]]:
    """Shape API rows to the Spark schema.

    - keeps only the columns named in the schema (the API may return more)
    - JSON whole numbers such as 25 arrive as int; DoubleType needs float
    - date/datetime objects become ISO strings
    Bad values are left as they are so Gate 5 rejects them; nothing is invented.
    """

    output = []

    for row in rows:

        clean_row = {}

        for field in schema.fields:

            value = row.get(field.name)

            if isinstance(value, (datetime, date)):
                value = value.isoformat()

            elif (
                isinstance(field.dataType, T.DoubleType)
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                value = float(value)

            elif (
                isinstance(field.dataType, T.StringType)
                and value is not None
                and not isinstance(value, str)
            ):
                value = str(value)

            clean_row[field.name] = value

        output.append(
            clean_row
        )

    return output


donor_df = spark.createDataFrame(
    serialize_values(donor_rows, DONOR_SCHEMA),
    schema=DONOR_SCHEMA,
)

requester_df = spark.createDataFrame(
    serialize_values(requester_rows, REQUESTER_SCHEMA),
    schema=REQUESTER_SCHEMA,
)


print(
    "PySpark donor rows:",
    donor_df.count(),
)

print(
    "PySpark requester rows:",
    requester_df.count(),
)


print()
print("DONOR PYSPARK SCHEMA")
donor_df.printSchema()

print()
print("REQUESTER PYSPARK SCHEMA")
requester_df.printSchema()


display(
    donor_df
)

display(
    requester_df
)


print()
print(
    "PASS Gate 3 — Supabase API rows converted "
    "to explicit PYSPARK DataFrames"
)


# COMMAND ----------

# ============================================================
# GATE 4 — PYSPARK NORMALIZATION
# ============================================================

donor_clean = (
    donor_df

    .select(

        F.trim(
            F.col("external_listing_id")
        ).alias(
            "external_listing_id"
        ),

        F.trim(
            F.col("donor_id")
        ).alias(
            "donor_id"
        ),

        F.trim(
            F.col("title")
        ).alias(
            "title"
        ),

        F.trim(
            F.col("description")
        ).alias(
            "description"
        ),

        F.upper(
            F.trim(
                F.col("category")
            )
        ).alias(
            "category"
        ),

        F.upper(
            F.trim(
                F.col("condition")
            )
        ).alias(
            "condition"
        ),

        F.trim(
            F.col("location")
        ).alias(
            "location"
        ),

        F.col(
            "latitude"
        ).cast(
            "double"
        ).alias(
            "latitude"
        ),

        F.col(
            "longitude"
        ).cast(
            "double"
        ).alias(
            "longitude"
        ),

        F.to_date(
            F.col("available_until")
        ).alias(
            "available_until"
        ),

        F.to_timestamp(
            F.col("created_at")
        ).alias(
            "source_created_at"
        ),
    )

    .dropDuplicates(
        [
            "external_listing_id"
        ]
    )
)


requester_clean = (
    requester_df

    .select(

        F.trim(
            F.col("external_request_id")
        ).alias(
            "external_request_id"
        ),

        F.trim(
            F.col("requester_id")
        ).alias(
            "requester_id"
        ),

        F.trim(
            F.col("request_text")
        ).alias(
            "request_text"
        ),

        F.upper(
            F.trim(
                F.col("category")
            )
        ).alias(
            "category"
        ),

        F.trim(
            F.col("location")
        ).alias(
            "location"
        ),

        F.col(
            "latitude"
        ).cast(
            "double"
        ).alias(
            "latitude"
        ),

        F.col(
            "longitude"
        ).cast(
            "double"
        ).alias(
            "longitude"
        ),

        F.to_date(
            F.col("need_by_date")
        ).alias(
            "need_by_date"
        ),

        F.to_timestamp(
            F.col("created_at")
        ).alias(
            "source_created_at"
        ),
    )

    .dropDuplicates(
        [
            "external_request_id"
        ]
    )
)


print(
    "Normalized donor rows:",
    donor_clean.count(),
)

print(
    "Normalized requester rows:",
    requester_clean.count(),
)


print()
print(
    "PASS Gate 4 — PYSPARK normalization "
    "and deduplication completed"
)


# COMMAND ----------

# ============================================================
# GATE 5 — PYSPARK DATA QUALITY
# ============================================================

VALID_CATEGORIES = [
    "FURNITURE",
    "KITCHEN",
    "ELECTRONICS",
    "BOOKS",
    "CLOTHING",
    "OTHER",
]


VALID_CONDITIONS = [
    "NEW",
    "LIKE_NEW",
    "GOOD",
    "FAIR",
    "USED",
]


bad_donors = (
    donor_clean

    .filter(

        F.col(
            "external_listing_id"
        ).isNull()

        |

        (
            F.length(
                F.col(
                    "external_listing_id"
                )
            )
            == 0
        )

        |

        F.col(
            "donor_id"
        ).isNull()

        |

        F.col(
            "title"
        ).isNull()

        |

        ~F.col(
            "category"
        ).isin(
            VALID_CATEGORIES
        )

        |

        ~F.col(
            "condition"
        ).isin(
            VALID_CONDITIONS
        )

        |

        F.col(
            "latitude"
        ).isNull()

        |

        F.col(
            "longitude"
        ).isNull()

        |

        ~F.col(
            "latitude"
        ).between(
            -90.0,
            90.0,
        )

        |

        ~F.col(
            "longitude"
        ).between(
            -180.0,
            180.0,
        )

        |

        F.col(
            "available_until"
        ).isNull()
    )
)


bad_requests = (
    requester_clean

    .filter(

        F.col(
            "external_request_id"
        ).isNull()

        |

        (
            F.length(
                F.col(
                    "external_request_id"
                )
            )
            == 0
        )

        |

        F.col(
            "requester_id"
        ).isNull()

        |

        F.col(
            "request_text"
        ).isNull()

        |

        ~F.col(
            "category"
        ).isin(
            VALID_CATEGORIES
        )

        |

        F.col(
            "latitude"
        ).isNull()

        |

        F.col(
            "longitude"
        ).isNull()

        |

        ~F.col(
            "latitude"
        ).between(
            -90.0,
            90.0,
        )

        |

        ~F.col(
            "longitude"
        ).between(
            -180.0,
            180.0,
        )

        |

        F.col(
            "need_by_date"
        ).isNull()
    )
)


bad_donor_count = (
    bad_donors.count()
)

bad_request_count = (
    bad_requests.count()
)


print(
    "Invalid donor rows:",
    bad_donor_count,
)

print(
    "Invalid requester rows:",
    bad_request_count,
)


if bad_donor_count > 0:
    display(
        bad_donors
    )


if bad_request_count > 0:
    display(
        bad_requests
    )


assert bad_donor_count == 0, (
    "FAIL — invalid donor records found."
)


assert bad_request_count == 0, (
    "FAIL — invalid requester records found."
)


print()
print(
    "PASS Gate 5 — PYSPARK data-quality "
    "validation passed"
)


# COMMAND ----------

# ============================================================
# GATE 6 — ADD INGESTION METADATA WITH PYSPARK
# ============================================================

donor_output = (
    donor_clean

    .withColumn(
        "source_system",
        F.lit(
            "supabase"
        ),
    )

    .withColumn(
        "source_table",
        F.lit(
            f"public.{DONOR_SOURCE_TABLE}"
        ),
    )

    .withColumn(
        "ingested_at",
        F.current_timestamp(),
    )
)


requester_output = (
    requester_clean

    .withColumn(
        "source_system",
        F.lit(
            "supabase"
        ),
    )

    .withColumn(
        "source_table",
        F.lit(
            f"public.{REQUESTER_SOURCE_TABLE}"
        ),
    )

    .withColumn(
        "ingested_at",
        F.current_timestamp(),
    )
)


print(
    "PASS Gate 6 — PYSPARK ingestion "
    "metadata added"
)


# COMMAND ----------

# ============================================================
# GATE 7 — CREATE EXISTING SHIPP BRONZE SCHEMA IF NEEDED
# ============================================================

spark.sql(
    """
    CREATE SCHEMA IF NOT EXISTS
    bootcamp_students.shipp_bronze
    """
)


print(
    "PASS Gate 7 — SHIPP Bronze schema available"
)


# COMMAND ----------

# ============================================================
# GATE 8 — IDEMPOTENT PYSPARK / DELTA UPSERT
# ============================================================

def upsert_delta(
    source_df: DataFrame,
    target_table: str,
    business_key: str,
    temp_view: str,
) -> None:

    target_exists = (
        spark.catalog.tableExists(
            target_table
        )
    )


    print(
        "Target:",
        target_table,
    )

    print(
        "Exists before write:",
        target_exists,
    )


    if not target_exists:

        (
            source_df
            .write
            .format(
                "delta"
            )
            .mode(
                "overwrite"
            )
            .saveAsTable(
                target_table
            )
        )

        print(
            "Created:",
            target_table,
        )

        return


    source_df.createOrReplaceTempView(
        temp_view
    )


    spark.sql(
        f"""
        MERGE INTO {target_table} AS target

        USING {temp_view} AS source

        ON target.{business_key}
           = source.{business_key}

        WHEN MATCHED THEN
          UPDATE SET *

        WHEN NOT MATCHED THEN
          INSERT *
        """
    )


    print(
        "MERGE completed:",
        target_table,
    )


upsert_delta(
    donor_output,
    DONOR_BRONZE,
    "external_listing_id",
    "shipp_supabase_donor_stage",
)


upsert_delta(
    requester_output,
    REQUESTER_BRONZE,
    "external_request_id",
    "shipp_supabase_requester_stage",
)


print()
print(
    "PASS Gate 8 — PYSPARK data persisted "
    "idempotently to Delta Bronze"
)


# COMMAND ----------

# ============================================================
# GATE 9 — FINAL PYSPARK VALIDATION
# ============================================================

donor_check = spark.table(
    DONOR_BRONZE
)

requester_check = spark.table(
    REQUESTER_BRONZE
)


donor_count = (
    donor_check.count()
)

requester_count = (
    requester_check.count()
)


live_listing_count = (
    donor_check

    .filter(
        F.col(
            "external_listing_id"
        )
        ==
        "live-listing-001"
    )

    .count()
)


live_request_count = (
    requester_check

    .filter(
        F.col(
            "external_request_id"
        )
        ==
        "live-request-001"
    )

    .count()
)


print()
print(
    "=============================================="
)
print(
    "SHIPP LIVE SUPABASE → PYSPARK → BRONZE"
)
print(
    "=============================================="
)

print(
    "donor_bronze_rows      =",
    donor_count,
)

print(
    "requester_bronze_rows  =",
    requester_count,
)

print(
    "live-listing-001 rows  =",
    live_listing_count,
)

print(
    "live-request-001 rows  =",
    live_request_count,
)


assert live_listing_count == 1, (
    "FAIL — live-listing-001 is missing "
    "or duplicated."
)


assert live_request_count == 1, (
    "FAIL — live-request-001 is missing "
    "or duplicated."
)


print()
print(
    "DONOR BRONZE OUTPUT"
)

display(
    donor_check
    .orderBy(
        F.col(
            "ingested_at"
        ).desc()
    )
)


print()
print(
    "REQUESTER BRONZE OUTPUT"
)

display(
    requester_check
    .orderBy(
        F.col(
            "ingested_at"
        ).desc()
    )
)


print()
print(
    "PASS Gate 9 — LIVE SUPABASE "
    "→ PYSPARK → BRONZE VALIDATED"
)


summary = {
    "source": "supabase_rest_api",
    "processing_engine": "pyspark",
    "donor_target": DONOR_BRONZE,
    "requester_target": REQUESTER_BRONZE,
    "donor_rows": donor_count,
    "requester_rows": requester_count,
    "live_listing_rows": live_listing_count,
    "live_request_rows": live_request_count,
    "status": "PASS",
}


print()
print(
    json.dumps(
        summary,
        indent=2,
        default=str,
    )
)


dbutils.notebook.exit(
    json.dumps(
        summary,
        default=str,
    )
)
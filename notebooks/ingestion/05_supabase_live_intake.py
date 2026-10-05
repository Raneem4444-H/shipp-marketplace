# Databricks notebook source

# ============================================================
# SHIPP — LIVE SUPABASE DONOR / REQUESTER INGESTION
#
# SOURCE:
#   Supabase PostgreSQL
#
# PROCESSING:
#   Python DB read -> PySpark DataFrames
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

# ============================================================
# GATE 0 — IMPORTS / PYSPARK
# ============================================================

import json
from datetime import date, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T
import json
from datetime import date, datetime
from typing import Any



print("psycopg version:", psycopg.__version__)
print("Spark version:", spark.version)

print("PASS — psycopg + PYSPARK available")

print("==============================================")
print("SHIPP — LIVE SUPABASE INTAKE")
print("==============================================")
print("Spark version:", spark.version)
print("PySpark functions loaded:", F is not None)
print("PySpark types loaded:", T is not None)

print()
print("PASS Gate 0 — PYSPARK runtime ready")


# COMMAND ----------

# ============================================================
# GATE 1 — CONFIGURATION
# ============================================================

SECRET_SCOPE = "shipp"
SUPABASE_DB_SECRET = "supabase-db-url"

DONOR_SOURCE_TABLE = "public.donor_intake"
REQUESTER_SOURCE_TABLE = "public.requester_intake"

DONOR_BRONZE = (
    "bootcamp_students.shipp_bronze.supabase_donor_intake"
)

REQUESTER_BRONZE = (
    "bootcamp_students.shipp_bronze.supabase_requester_intake"
)


SUPABASE_DB_URL = dbutils.secrets.get(
    scope=SECRET_SCOPE,
    key=SUPABASE_DB_SECRET,
).strip()


assert SUPABASE_DB_URL, (
    "BLOCKED — Databricks secret "
    "'shipp/supabase-db-url' is empty."
)


print("Source donor table     :", DONOR_SOURCE_TABLE)
print("Source requester table :", REQUESTER_SOURCE_TABLE)

print("Target donor Bronze    :", DONOR_BRONZE)
print("Target requester Bronze:", REQUESTER_BRONZE)

print()
print(
    "PASS Gate 1 — Supabase connection loaded securely "
    "(secret value not printed)"
)


# COMMAND ----------

# ============================================================
# GATE 2 — READ LIVE SUPABASE DATABASE
# ============================================================

ALLOWED_SOURCE_TABLES = {
    DONOR_SOURCE_TABLE,
    REQUESTER_SOURCE_TABLE,
}


def fetch_supabase_table(
    table_name: str,
) -> list[dict[str, Any]]:

    if table_name not in ALLOWED_SOURCE_TABLES:
        raise ValueError(
            f"Unexpected source table: {table_name}"
        )

    with psycopg.connect(
        SUPABASE_DB_URL,
        connect_timeout=15,
        row_factory=dict_row,
    ) as conn:

        with conn.cursor() as cur:

            cur.execute(
                f"""
                SELECT *
                FROM {table_name}
                ORDER BY created_at ASC
                """
            )

            rows = cur.fetchall()

    return [
        dict(row)
        for row in rows
    ]


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
    "data received"
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
) -> list[dict[str, Any]]:

    output = []

    for row in rows:

        clean_row = {}

        for key, value in row.items():

            if isinstance(
                value,
                (datetime, date),
            ):
                clean_row[key] = (
                    value.isoformat()
                )

            else:
                clean_row[key] = value

        output.append(
            clean_row
        )

    return output


donor_df = spark.createDataFrame(
    serialize_values(donor_rows),
    schema=DONOR_SCHEMA,
)

requester_df = spark.createDataFrame(
    serialize_values(requester_rows),
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
    "PASS Gate 3 — Supabase rows converted "
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
            DONOR_SOURCE_TABLE
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
            REQUESTER_SOURCE_TABLE
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
    "source": "supabase_postgresql",
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
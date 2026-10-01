"""Delete-aware current-state reconstruction from Lakebase CDC history.

Bronze rows carry:
- _pg_change_type: insert / update_preimage / update_postimage / delete
- _pg_lsn: commit order
- _sort_by: order inside one transaction

Correct rule:
    1. Ignore update_preimage.
    2. Rank remaining CDC events newest-first per business key.
    3. Select rank 1.
    4. If the newest event is DELETE, the entity no longer exists.

IMPORTANT:
Never filter DELETE events before ranking.
Doing so can resurrect deleted records in Silver.
"""

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window


CURRENT_STATE_CHANGE_TYPES = [
    "insert",
    "update_postimage",
    "delete",
]

# IMPORTANT:
# Do not use this list to filter Bronze before current-state ranking,
# because DELETE events must participate in reconstruction.
SILVER_SOURCE_CHANGE_TYPES = [
    "insert",
    "update_postimage",
]


def cdc_newest_first():
    """Return CDC ordering columns from newest to oldest."""
    return [
        F.col("_pg_lsn").desc(),
        F.col("_sort_by").desc(),
    ]


def reconstruct_current_state(
    bronze_df: DataFrame,
    key: str,
):
    """Reconstruct current entity state from Bronze CDC history.

    Returns:
        latest_events_df:
            Latest CDC event for every business key, including DELETE.

        current_rows_df:
            Latest non-deleted rows representing current operational state.

        deleted_keys_df:
            Keys whose latest CDC event is DELETE.
    """
    window = (
        Window
        .partitionBy(key)
        .orderBy(*cdc_newest_first())
    )

    latest_events_df = (
        bronze_df
        .filter(
            F.col("_pg_change_type").isin(
                CURRENT_STATE_CHANGE_TYPES
            )
        )
        .withColumn(
            "_current_rn",
            F.row_number().over(window),
        )
        .filter(
            F.col("_current_rn") == 1
        )
        .drop("_current_rn")
    )

    deleted_keys_df = (
        latest_events_df
        .filter(
            F.col("_pg_change_type") == "delete"
        )
        .select(key)
    )

    current_rows_df = (
        latest_events_df
        .filter(
            F.col("_pg_change_type") != "delete"
        )
    )

    return (
        latest_events_df,
        current_rows_df,
        deleted_keys_df,
    )


def independent_current_keys(
    bronze_df: DataFrame,
    key: str,
) -> set:
    """Independently recompute current keys using max_by.

    This gives a second validation method that does not reuse
    the window implementation from reconstruct_current_state().
    """
    rows = (
        bronze_df
        .filter(
            F.col("_pg_change_type") != "update_preimage"
        )
        .groupBy(key)
        .agg(
            F.expr(
                "max_by("
                "_pg_change_type, "
                "struct(_pg_lsn, _sort_by)"
                ")"
            ).alias("last_change")
        )
        .filter(
            F.col("last_change") != "delete"
        )
        .select(key)
        .collect()
    )

    return {
        row[key]
        for row in rows
    }


def normalize_code(
    col_name: str,
):
    """Normalize category / condition values.

    Example:
        '  Like New ' -> 'LIKE_NEW'
    """
    return F.regexp_replace(
        F.upper(
            F.trim(
                F.col(col_name)
            )
        ),
        r"[\s\-]+",
        "_",
    )


def assert_silver_matches_bronze(
    spark: SparkSession,
    silver_table: str,
    bronze_df: DataFrame,
    current_rows_df: DataFrame,
    deleted_keys_df: DataFrame,
    key: str,
) -> None:
    """Validate Silver against reconstructed Bronze current state.

    Checks:
    - no duplicate business keys
    - deleted entities are not resurrected
    - no current Bronze rows are missing
    - no extra Silver rows exist
    - Silver source trace columns match latest Bronze events
    - independent max_by reconstruction agrees with Silver
    """
    silver = spark.table(silver_table)

    # 1. Duplicate business keys
    duplicates = (
        silver
        .groupBy(key)
        .count()
        .filter(
            F.col("count") > 1
        )
        .count()
    )

    # 2. Deleted records must not exist in Silver
    resurrected = (
        silver
        .join(
            deleted_keys_df,
            key,
            "inner",
        )
        .count()
    )

    # 3. Every current Bronze key must exist in Silver
    missing = (
        current_rows_df
        .select(key)
        .join(
            silver.select(key),
            key,
            "left_anti",
        )
        .count()
    )

    # 4. Silver must not contain keys outside current Bronze state
    extra = (
        silver
        .select(key)
        .join(
            current_rows_df.select(key),
            key,
            "left_anti",
        )
        .count()
    )

    # 5. Silver lineage must trace to the newest Bronze event.
    #
    # eqNullSafe() is required here.
    # Normal != comparisons can silently miss mismatches involving NULL.
    trace_mismatches = (
        silver.alias("s")
        .join(
            current_rows_df.alias("b"),
            key,
            "inner",
        )
        .filter(
            ~F.col("s.source_pg_lsn").eqNullSafe(
                F.col("b._pg_lsn")
            )
            | ~F.col("s.source_sort_by").eqNullSafe(
                F.col("b._sort_by")
            )
            | ~F.col("s.source_change_type").eqNullSafe(
                F.col("b._pg_change_type")
            )
        )
        .count()
    )

    # 6. Independent reconstruction check
    silver_keys = {
        row[key]
        for row in silver.select(key).collect()
    }

    independent_keys = independent_current_keys(
        bronze_df=bronze_df,
        key=key,
    )

    print(
        f"Duplicate {key}:                "
        f"{duplicates}"
    )
    print(
        "Resurrected deleted keys:        "
        f"{resurrected}"
    )
    print(
        "Missing current keys:            "
        f"{missing}"
    )
    print(
        "Extra keys not in Bronze state:  "
        f"{extra}"
    )
    print(
        "Traceability mismatches:         "
        f"{trace_mismatches}"
    )
    print(
        "Silver keys:      "
        f"{sorted(silver_keys)}"
    )
    print(
        "Independent keys: "
        f"{sorted(independent_keys)}"
    )

    assert duplicates == 0, (
        f"FAILED: duplicate {key} "
        f"in {silver_table}"
    )

    assert resurrected == 0, (
        f"FAILED: deleted keys present "
        f"in {silver_table}"
    )

    assert missing == 0 and extra == 0, (
        f"FAILED: {silver_table} key set "
        f"!= current Bronze state"
    )

    assert trace_mismatches == 0, (
        f"FAILED: {silver_table} rows do not "
        f"trace to the newest Bronze event"
    )

    assert silver_keys == independent_keys, (
        f"FAILED: {silver_table} disagrees "
        f"with the independent max_by recomputation"
    )

    print(
        f"PASS — {silver_table} matches current "
        f"Bronze state (two independent methods)."
    )
"""Delete-aware current-state reconstruction from Lakebase CDC history.

Bronze rows carry _pg_change_type (insert / update_preimage / update_postimage / delete),
_pg_lsn (commit order) and _sort_by (order inside one transaction).

Correct rule (the bug this module exists to prevent):
    1. drop update_preimage (old row image, never the current state)
    2. rank the remaining events newest-first per key
    3. take rank 1
    4. if that newest event is a delete, the key does not exist any more
Filtering deletes out BEFORE ranking resurrects deleted rows.
"""

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

CURRENT_STATE_CHANGE_TYPES = ["insert", "update_postimage", "delete"]
SILVER_SOURCE_CHANGE_TYPES = ["insert", "update_postimage"]


def cdc_newest_first():
    return [F.col("_pg_lsn").desc(), F.col("_sort_by").desc()]


def reconstruct_current_state(bronze_df: DataFrame, key: str):
    """Return (latest_events_df, current_rows_df, deleted_keys_df)."""
    window = Window.partitionBy(key).orderBy(*cdc_newest_first())
    latest_events_df = (
        bronze_df
        .filter(F.col("_pg_change_type").isin(CURRENT_STATE_CHANGE_TYPES))
        .withColumn("_current_rn", F.row_number().over(window))
        .filter(F.col("_current_rn") == 1)
        .drop("_current_rn")
    )
    deleted_keys_df = latest_events_df.filter(F.col("_pg_change_type") == "delete").select(key)
    current_rows_df = latest_events_df.filter(F.col("_pg_change_type") != "delete")
    return latest_events_df, current_rows_df, deleted_keys_df


def independent_current_keys(bronze_df: DataFrame, key: str) -> set:
    """Same answer via max_by instead of a window function — an independent cross-check."""
    rows = (
        bronze_df
        .filter(F.col("_pg_change_type") != "update_preimage")
        .groupBy(key)
        .agg(F.expr("max_by(_pg_change_type, struct(_pg_lsn, _sort_by))").alias("last_change"))
        .filter(F.col("last_change") != "delete")
        .select(key)
        .collect()
    )
    return {r[key] for r in rows}


def normalize_code(col_name: str):
    """'  Like New ' -> 'LIKE_NEW'. Used for category and condition so equality joins are reliable."""
    return F.regexp_replace(F.upper(F.trim(F.col(col_name))), r"[\s\-]+", "_")


def assert_silver_matches_bronze(spark: SparkSession, silver_table: str, bronze_df: DataFrame,
                                 current_rows_df: DataFrame, deleted_keys_df: DataFrame, key: str) -> None:
    """Post-write gate: Silver must equal the current state of Bronze, checked two independent ways."""
    silver = spark.table(silver_table)

    duplicates = silver.groupBy(key).count().filter(F.col("count") > 1).count()
    resurrected = silver.join(deleted_keys_df, key, "inner").count()
    missing = current_rows_df.join(silver, key, "left_anti").count()
    extra = silver.join(current_rows_df.select(key), key, "left_anti").count()
    trace_mismatches = (
        silver.alias("s")
        .join(current_rows_df.alias("b"), key, "inner")
        .filter(
            (F.col("s.source_pg_lsn") != F.col("b._pg_lsn"))
            | (F.col("s.source_sort_by") != F.col("b._sort_by"))
            | (F.col("s.source_change_type") != F.col("b._pg_change_type"))
        )
        .count()
    )
    silver_keys = {r[key] for r in silver.select(key).collect()}
    independent_keys = independent_current_keys(bronze_df, key)

    print(f"Duplicate {key}:                {duplicates}")
    print(f"Resurrected deleted keys:        {resurrected}")
    print(f"Missing current keys:            {missing}")
    print(f"Extra keys not in Bronze state:  {extra}")
    print(f"Traceability mismatches:         {trace_mismatches}")
    print(f"Silver keys:      {sorted(silver_keys)}")
    print(f"Independent keys: {sorted(independent_keys)}")

    assert duplicates == 0, f"FAILED: duplicate {key} in {silver_table}"
    assert resurrected == 0, f"FAILED: deleted keys present in {silver_table}"
    assert missing == 0 and extra == 0, f"FAILED: {silver_table} key set != current Bronze state"
    assert trace_mismatches == 0, f"FAILED: {silver_table} rows do not trace to the newest Bronze event"
    assert silver_keys == independent_keys, (
        f"FAILED: {silver_table} disagrees with the independent max_by recomputation"
    )
    print(f"PASS — {silver_table} matches current Bronze state (two independent methods).")

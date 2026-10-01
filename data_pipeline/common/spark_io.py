"""Table I/O helpers. Every function takes the SparkSession explicitly (testable, no globals)."""

from pyspark.sql import DataFrame, SparkSession


def table_exists(spark: SparkSession, name: str) -> bool:
    try:
        spark.table(name).columns
        return True
    except Exception:
        return False


def read_bronze_pinned(spark: SparkSession, table: str):
    """Return (df, version) read at one fixed Delta version; falls back to the live table."""
    try:
        version = spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").first()["version"]
        df = spark.sql(f"SELECT * FROM {table} VERSION AS OF {version}")
        _ = df.columns  # force analysis so a time-travel error surfaces here
        print(f"Bronze pinned: {table} @ Delta version {version}")
        return df, version
    except Exception as e:
        print("WARNING — could not pin Bronze version; reading the live table instead.")
        print(f"          {type(e).__name__}: {str(e)[:300]}")
        return spark.table(table), None


def write_overwrite(spark: SparkSession, df: DataFrame, table: str) -> int:
    """Overwrite a Delta table and return the persisted row count.

    overwriteSchema stays on; schema drift is caught by assert_exact_schema right after the write.
    """
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(table)
    written = spark.table(table).count()
    print(f"Written {table}: {written} rows")
    return written


def assert_exact_schema(spark: SparkSession, table: str, expected_columns: list) -> None:
    actual = spark.table(table).columns
    assert actual == expected_columns, (
        f"SCHEMA VALIDATION FAILED for {table}\n expected={expected_columns}\n actual  ={actual}"
    )
    print(f"PASS — {table} schema matches the contract.")


def logical_snapshot(spark: SparkSession, table: str, key: str) -> list:
    """Table contents without processing timestamps, sorted by key — for idempotency checks."""
    cols = [c for c in spark.table(table).columns if not c.endswith("_processed_at")]
    return [r.asDict(recursive=True) for r in spark.table(table).select(*cols).orderBy(key).collect()]

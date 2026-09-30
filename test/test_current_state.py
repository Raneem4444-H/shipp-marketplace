"""Delete-aware reconstruction — the regression test for the resurrected-listing bug."""

from pyspark.sql import functions as F
from pyspark.sql.window import Window

from data_pipeline.silver.current_state import (
    independent_current_keys,
    normalize_code,
    reconstruct_current_state,
)

ROWS = [
    ("L1", "insert", 100, 8), ("L1", "delete", 101, 9), ("L1", "insert", 102, 10), ("L1", "delete", 103, 11),
    ("L2", "insert", 100, 0), ("L2", "update_preimage", 104, 4), ("L2", "update_postimage", 104, 5),
    ("L3", "insert", 100, 1), ("L3", "delete", 105, 12), ("L3", "insert", 106, 13),
    ("L4", "insert", 200, 20), ("L4", "update_preimage", 200, 21), ("L4", "update_postimage", 200, 22),
]
SCHEMA = "listing_id string, _pg_change_type string, _pg_lsn long, _sort_by long"


def test_current_state(spark):
    df = spark.createDataFrame(ROWS, SCHEMA)
    _, current, deleted = reconstruct_current_state(df, "listing_id")
    assert {r.listing_id: r._pg_change_type for r in current.collect()} == {
        "L2": "update_postimage", "L3": "insert", "L4": "update_postimage"}
    assert {r.listing_id for r in deleted.collect()} == {"L1"}


def test_independent_method_agrees(spark):
    df = spark.createDataFrame(ROWS, SCHEMA)
    _, current, _ = reconstruct_current_state(df, "listing_id")
    assert independent_current_keys(df, "listing_id") == {r.listing_id for r in current.collect()}


def test_fixture_detects_old_bug(spark):
    """Filtering deletes out before ranking must resurrect L1 — proves the fixture has teeth."""
    df = spark.createDataFrame(ROWS, SCHEMA)
    w = Window.partitionBy("listing_id").orderBy(F.col("_pg_lsn").desc(), F.col("_sort_by").desc())
    old = (df.filter(F.col("_pg_change_type").isin("insert", "update_postimage"))
             .withColumn("rn", F.row_number().over(w)).filter("rn = 1"))
    assert "L1" in {r.listing_id for r in old.collect()}


def test_normalize_code(spark):
    df = spark.createDataFrame([(" Like New ",), ("good",), ("like-new",)], "c string")
    assert [r.n for r in df.select(normalize_code("c").alias("n")).collect()] == ["LIKE_NEW", "GOOD", "LIKE_NEW"]

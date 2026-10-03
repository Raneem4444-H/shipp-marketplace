"""Ordering edge cases for current_state: text LSNs, and the same event ingested twice."""

from datetime import datetime

import pytest

pyspark = pytest.importorskip("pyspark")

from pyspark.sql import SparkSession  # noqa: E402

from data_pipeline.silver.current_state import (  # noqa: E402
    independent_current_keys,
    reconstruct_current_state,
)


@pytest.fixture(scope="module")
def spark():
    s = SparkSession.builder.master("local[1]").appName("current_state_ordering").getOrCreate()
    yield s
    s.stop()


def test_text_lsn_orders_numerically_not_alphabetically(spark):
    # As text, "0/9" sorts after "0/10". Numerically 0x10 (=16) is newer than 0x9.
    rows = [
        ("l1", "insert", "0/9", 1),
        ("l1", "delete", "0/10", 1),
    ]
    df = spark.createDataFrame(rows, "listing_id string, _pg_change_type string, _pg_lsn string, _sort_by int")
    _, current, deleted = reconstruct_current_state(df, "listing_id")
    assert current.count() == 0
    assert [r.listing_id for r in deleted.collect()] == ["l1"]
    assert independent_current_keys(df, "listing_id") == set()


def test_numeric_lsn_unchanged(spark):
    rows = [("l1", "insert", 9, 1), ("l1", "update_postimage", 10, 1)]
    df = spark.createDataFrame(rows, "listing_id string, _pg_change_type string, _pg_lsn long, _sort_by int")
    latest, current, _ = reconstruct_current_state(df, "listing_id")
    assert latest.collect()[0]._pg_lsn == 10
    assert current.count() == 1


def test_duplicate_ingestion_is_deterministic(spark):
    t1, t2 = datetime(2026, 10, 1, 9, 0), datetime(2026, 10, 1, 9, 5)
    rows = [
        ("l1", "update_postimage", 20, 1, t1, "first copy"),
        ("l1", "update_postimage", 20, 1, t2, "second copy"),
    ]
    df = spark.createDataFrame(
        rows,
        "listing_id string, _pg_change_type string, _pg_lsn long, _sort_by int, "
        "_ingested_at timestamp, title string",
    )
    for _ in range(3):
        latest, _, _ = reconstruct_current_state(df, "listing_id")
        assert latest.collect()[0].title == "second copy"

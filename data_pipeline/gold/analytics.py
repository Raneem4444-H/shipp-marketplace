"""Stage 13 — CDF-derived marketplace analytics.

Inputs are Lakebase CDF history Delta tables for saved_items and agent_activity.
The transform reconstructs current state by business key before aggregation, so
re-running the job cannot double-count the same operational rows.

Grain of gold_marketplace_metrics: exactly one current marketplace snapshot row.
"""

from __future__ import annotations

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from data_pipeline.silver.current_state import reconstruct_current_state

METRIC_KEY = "marketplace_current"

METRIC_COLUMNS = [
    "metric_key",
    "saved_item_count",
    "agent_action_count",
    "save_item_action_count",
    "agent_success_count",
    "agent_failure_count",
    "agent_rejected_count",
    "agent_duplicate_count",
    "source_saved_max_lsn",
    "source_activity_max_lsn",
    "computed_at",
]


def _zero_if_null(col: Column) -> Column:
    return F.coalesce(col, F.lit(0)).cast("long")


def build_marketplace_metrics(
    saved_items_history: DataFrame,
    agent_activity_history: DataFrame,
) -> DataFrame:
    """Build one idempotent Gold metrics snapshot from Lakebase CDF histories.

    DELETE is handled correctly because current state is reconstructed before
    aggregation. agent_activity is normally append-only, but the same rule keeps
    the result correct if an activity row is ever updated/deleted.

    Status matching is case-insensitive so analytics remains readable while the
    agent/database status vocabulary is finalized.
    """
    saved_latest, saved_current, _ = reconstruct_current_state(
        saved_items_history, "saved_item_id"
    )
    activity_latest, activity_current, _ = reconstruct_current_state(
        agent_activity_history, "activity_id"
    )

    saved_agg = saved_current.agg(
        F.count("*").cast("long").alias("saved_item_count"),
    )

    a = activity_current.withColumn(
        "_status_norm", F.upper(F.trim(F.col("action_status")))
    )

    activity_agg = a.agg(
        F.count("*").cast("long").alias("agent_action_count"),
        _zero_if_null(
            F.sum(F.when(F.lower(F.col("tool_name")) == "save_item", 1).otherwise(0))
        ).alias("save_item_action_count"),
        _zero_if_null(
            F.sum(F.when(F.col("_status_norm") == "SUCCESS", 1).otherwise(0))
        ).alias("agent_success_count"),
        _zero_if_null(
            F.sum(
                F.when(
                    F.col("_status_norm").isin("FAILURE", "FAILED", "ERROR"), 1
                ).otherwise(0)
            )
        ).alias("agent_failure_count"),
        _zero_if_null(
            F.sum(F.when(F.col("_status_norm") == "REJECTED", 1).otherwise(0))
        ).alias("agent_rejected_count"),
        _zero_if_null(
            F.sum(F.when(F.col("_status_norm") == "DUPLICATE", 1).otherwise(0))
        ).alias("agent_duplicate_count"),
    )

    saved_watermark = saved_latest.agg(
        F.max(F.col("_pg_lsn").cast("string")).alias("source_saved_max_lsn")
    )
    activity_watermark = activity_latest.agg(
        F.max(F.col("_pg_lsn").cast("string")).alias("source_activity_max_lsn")
    )

    return (
        saved_agg.crossJoin(activity_agg)
        .crossJoin(saved_watermark)
        .crossJoin(activity_watermark)
        .withColumn("metric_key", F.lit(METRIC_KEY))
        .withColumn("computed_at", F.current_timestamp())
        .select(*METRIC_COLUMNS)
    )

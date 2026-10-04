"""Final deployed E2E validation for SHIPP.

This module validates evidence produced by the real deployed workflow without
rebuilding pipeline outputs. It is intentionally read-only.

The App proves runtime identity/permissions and saved-state refresh directly.
This module proves the same App-created business IDs propagated through CDC,
Silver, Gold/Search, Agent audit, ORS evidence, and Velocity measurements.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from pyspark.sql import functions as F


@dataclass(frozen=True)
class ValidationCheck:
    check_name: str
    status: str
    observed_value: str
    detail: str


def _check(
    checks: list[ValidationCheck],
    name: str,
    ok: bool,
    value: Any,
    detail: str,
) -> None:
    checks.append(
        ValidationCheck(
            check_name=name,
            status="PASS" if ok else "FAIL",
            observed_value=str(value),
            detail=detail,
        )
    )


def _exists(spark: Any, table: str) -> bool:
    try:
        spark.sql(f"DESCRIBE TABLE {table}").limit(1).collect()
        return True
    except Exception:
        return False


def run_deployed_e2e_validation(
    spark: Any,
    tables: Mapping[str, str],
    *,
    listing_id: str,
    request_id: str,
    saved_item_id: str,
    unavailable_listing_id: str,
) -> tuple[dict[str, Any], list[ValidationCheck]]:
    """Validate one deployed SHIPP journey by concrete business IDs."""

    checks: list[ValidationCheck] = []

    required = (
        "bronze_listings_history",
        "bronze_requests_history",
        "bronze_saved_items_history",
        "bronze_agent_activity_history",
        "bronze_route_responses",
        "silver_listings",
        "silver_requests",
        "gold_candidate_matches",
        "gold_listing_search_docs",
        "velocity_measurements",
        "ors_failure_validation_log",
    )

    missing_names = [name for name in required if name not in tables]
    _check(
        checks,
        "table_contract",
        not missing_names,
        missing_names,
        "Every required deployed-E2E evidence table is configured.",
    )
    if missing_names:
        return _summary(checks), checks

    missing_tables = [name for name in required if not _exists(spark, tables[name])]
    for name in required:
        _check(
            checks,
            f"table_exists:{name}",
            name not in missing_tables,
            tables[name],
            "Required persisted evidence table exists.",
        )
    if missing_tables:
        return _summary(checks), checks

    bronze_listings = spark.table(tables["bronze_listings_history"])
    bronze_requests = spark.table(tables["bronze_requests_history"])
    bronze_saved = spark.table(tables["bronze_saved_items_history"])
    bronze_activity = spark.table(tables["bronze_agent_activity_history"])
    bronze_routes = spark.table(tables["bronze_route_responses"])
    silver_listings = spark.table(tables["silver_listings"])
    silver_requests = spark.table(tables["silver_requests"])
    gold = spark.table(tables["gold_candidate_matches"])
    search_docs = spark.table(tables["gold_listing_search_docs"])
    velocity = spark.table(tables["velocity_measurements"])

    # ------------------------------------------------------------------
    # App-created Listing: operational write -> CDC -> Silver -> Search
    # ------------------------------------------------------------------
    listing_cdc = bronze_listings.filter(F.col("listing_id") == listing_id).count()
    _check(
        checks,
        "app_listing_reached_bronze",
        listing_cdc > 0,
        listing_cdc,
        "The Listing ID created in the deployed App appears in Lakebase CDC history.",
    )

    listing_silver = silver_listings.filter(F.col("listing_id") == listing_id).count()
    _check(
        checks,
        "app_listing_reached_silver",
        listing_silver == 1,
        listing_silver,
        "The deployed-App Listing is present exactly once in trusted Silver current state.",
    )

    listing_search = search_docs.filter(F.col("listing_id") == listing_id).count()
    _check(
        checks,
        "app_listing_reached_search_docs",
        listing_search > 0,
        listing_search,
        "The deployed-App Listing produced searchable Gold content.",
    )

    # ------------------------------------------------------------------
    # App-created Request: operational write -> CDC -> Silver -> Gold
    # ------------------------------------------------------------------
    request_cdc = bronze_requests.filter(F.col("request_id") == request_id).count()
    _check(
        checks,
        "app_request_reached_bronze",
        request_cdc > 0,
        request_cdc,
        "The Request ID created in the deployed App appears in Lakebase CDC history.",
    )

    request_silver = silver_requests.filter(F.col("request_id") == request_id).count()
    _check(
        checks,
        "app_request_reached_silver",
        request_silver == 1,
        request_silver,
        "The deployed-App Request is present exactly once in trusted Silver current state.",
    )

    request_gold = gold.filter(F.col("request_id") == request_id).count()
    _check(
        checks,
        "app_request_has_gold_matches",
        request_gold > 0,
        request_gold,
        "The deployed-App Request has trusted Gold candidate matches.",
    )

    # ------------------------------------------------------------------
    # Agent READ evidence from the exact request/listing context
    # ------------------------------------------------------------------
    activity_current = bronze_activity.filter(
        F.lower(F.col("_pg_change_type")) != F.lit("delete")
    )
    activity_norm = activity_current.withColumn(
        "_status_norm", F.upper(F.trim(F.col("action_status")))
    )

    candidate_read = activity_norm.filter(
        (F.col("tool_name") == "get_candidate_matches")
        & (F.col("entity_id") == request_id)
        & (F.col("_status_norm").isin("SUCCESS", "NO_MATCH"))
    ).count()
    _check(
        checks,
        "agent_read_candidates",
        candidate_read > 0,
        candidate_read,
        "The Agent executed get_candidate_matches for the deployed-App request.",
    )

    semantic_read = activity_norm.filter(
        (F.col("tool_name") == "search_listing_context")
        & (F.col("entity_id") == request_id)
        & (F.col("_status_norm") == "SUCCESS")
    ).count()
    _check(
        checks,
        "agent_read_semantic_context",
        semantic_read > 0,
        semantic_read,
        "The Agent executed semantic listing retrieval for the deployed-App request.",
    )

    status_read = activity_norm.filter(
        (F.col("tool_name") == "get_listing_status")
        & (F.col("entity_id") == listing_id)
        & (F.col("_status_norm").isin("SUCCESS", "REJECTED_UNAVAILABLE"))
    ).count()
    _check(
        checks,
        "agent_read_current_listing_status",
        status_read > 0,
        status_read,
        "The Agent checked current Lakebase state for the selected Listing.",
    )

    # ------------------------------------------------------------------
    # Agent WRITE + duplicate + unavailable rejection evidence
    # ------------------------------------------------------------------
    saved_cdc = bronze_saved.filter(
        F.col("saved_item_id") == saved_item_id
    ).count()
    _check(
        checks,
        "agent_write_saved_item_reached_cdc",
        saved_cdc > 0,
        saved_cdc,
        "The saved_item_id returned by the deployed App exists in Lakebase CDC history.",
    )

    save_success = activity_norm.filter(
        (F.col("tool_name") == "save_item")
        & (F.col("entity_id") == listing_id)
        & (F.col("_status_norm") == "SUCCESS")
    ).count()
    _check(
        checks,
        "agent_write_success_audited",
        save_success > 0,
        save_success,
        "A successful save_item action for the deployed-App Listing is audited.",
    )

    duplicate = activity_norm.filter(
        (F.col("tool_name") == "save_item")
        & (F.col("entity_id") == listing_id)
        & (F.col("_status_norm") == "REJECTED_DUPLICATE")
    ).count()
    _check(
        checks,
        "duplicate_save_rejected",
        duplicate > 0,
        duplicate,
        "The final environment rejected and audited a duplicate save.",
    )

    unavailable = activity_norm.filter(
        (F.col("tool_name") == "save_item")
        & (F.col("entity_id") == unavailable_listing_id)
        & (F.col("_status_norm") == "REJECTED_UNAVAILABLE")
    ).count()
    _check(
        checks,
        "unavailable_listing_rejected",
        unavailable > 0,
        unavailable,
        "The final environment rejected and audited an unavailable Listing.",
    )

    # ------------------------------------------------------------------
    # ORS resilience evidence
    # ------------------------------------------------------------------
    retry_rows = bronze_routes.filter(F.col("attempts") > 1).count()
    failed_rows = bronze_routes.filter(
        F.col("error_message").isNotNull()
        | F.col("http_status").isNull()
        | (F.col("http_status") != 200)
    ).count()
    ors_validation = spark.table(tables["ors_failure_validation_log"])
    deterministic_passes = ors_validation.filter(
        F.upper(F.col("overall_status")) == "PASS"
    ).count()
    _check(
        checks,
        "ors_retry_failure_behavior",
        retry_rows > 0 or failed_rows > 0 or deterministic_passes > 0,
        {
            "bronze_retry_rows": retry_rows,
            "bronze_failed_rows": failed_rows,
            "deterministic_validation_passes": deterministic_passes,
        },
        "ORS resilience is proven by persisted runtime evidence or the deterministic retry/failure validation.",
    )

    # ------------------------------------------------------------------
    # Velocity evidence
    # ------------------------------------------------------------------
    relevant_velocity = velocity.filter(
        F.col("entity_id").isin(listing_id, request_id)
    )
    velocity_runs = relevant_velocity.count()
    velocity_passes = relevant_velocity.filter(F.col("slo_met") == True).count()
    best_latency = (
        relevant_velocity.agg(F.min("latency_seconds").alias("best")).first()["best"]
        if velocity_runs
        else None
    )
    _check(
        checks,
        "velocity_under_60_seconds",
        velocity_passes > 0,
        {
            "runs": velocity_runs,
            "slo_met_runs": velocity_passes,
            "best_latency_seconds": best_latency,
        },
        "At least one measured deployed business ID was retrievable in under 60 seconds.",
    )

    return _summary(checks), checks


def _summary(checks: list[ValidationCheck]) -> dict[str, Any]:
    failed = [check.check_name for check in checks if check.status == "FAIL"]
    return {
        "status": "PASS" if not failed else "FAIL",
        "total_checks": len(checks),
        "passed_checks": sum(check.status == "PASS" for check in checks),
        "failed_checks": failed,
    }

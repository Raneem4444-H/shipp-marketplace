"""Read-only release checks for SHIPP Tasks 90 and 91."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from pyspark.sql import functions as F
from pyspark.sql.window import Window


@dataclass(frozen=True)
class ValidationCheck:
    check_name: str
    status: str
    observed_value: str
    detail: str


EXPECTED_STAGES = (
    "10_silver_listings", "11_silver_requests", "30_candidate_pairs",
    "31_ors_enrichment", "32_silver_routes", "40_gold_matches",
    "60_marketplace_metrics", "50_silver_listing_files",
    "51_vision_enrichment", "52_silver_listing_content",
    "53_gold_search_docs", "54_ai_search_index", "55_rag_eval",
    "56_semantic_scores",
)


def _exists(spark: Any, table: str) -> bool:
    try:
        spark.sql(f"DESCRIBE TABLE {table}").limit(1).collect()
        return True
    except Exception:
        return False


def _check(out: list[ValidationCheck], name: str, ok: bool, value: Any, detail: str) -> None:
    out.append(ValidationCheck(name, "PASS" if ok else "FAIL", str(value), detail))


def run_release_validation(
    spark: Any,
    tables: Mapping[str, str],
) -> tuple[dict[str, Any], list[ValidationCheck]]:
    """Validate persisted P0 outputs without rewriting business tables."""

    checks: list[ValidationCheck] = []
    required = (
        "bronze_route_responses", "bronze_vision_responses",
        "silver_listings", "silver_requests", "silver_routes",
        "silver_listing_files", "silver_listing_content",
        "silver_semantic_scores", "gold_candidate_matches",
        "gold_listing_search_docs", "gold_marketplace_metrics",
        "rag_eval_results", "pipeline_run_log",
    )

    missing_names = [k for k in required if k not in tables]
    _check(checks, "validation_table_contract", not missing_names, missing_names,
           "Required canonical table names are supplied.")
    if missing_names:
        return _summary(checks), checks

    missing_tables = [k for k in required if not _exists(spark, tables[k])]
    for key in required:
        _check(checks, f"table_exists:{key}", key not in missing_tables,
               key not in missing_tables, tables[key])
    if missing_tables:
        return _summary(checks), checks

    frames = {k: spark.table(tables[k]) for k in required}
    counts = {k: frames[k].count() for k in required}
    for key, count in counts.items():
        _check(checks, f"non_empty:{key}", count > 0, count,
               "Persisted runtime evidence must be non-empty.")

    listings = frames["silver_listings"]
    requests = frames["silver_requests"]
    routes = frames["silver_routes"]
    gold = frames["gold_candidate_matches"]
    docs = frames["gold_listing_search_docs"]
    log = frames["pipeline_run_log"]

    dup_requests = requests.groupBy("request_id").count().filter("count > 1").count()
    _check(checks, "silver_requests_unique_request_id", dup_requests == 0,
           dup_requests, "One current row per request_id.")

    bad_request_fields = requests.filter(
        F.col("request_id").isNull() | F.col("category").isNull()
    ).count()
    _check(checks, "silver_requests_required_fields", bad_request_fields == 0,
           bad_request_fields, "Request id and category are required.")

    request_categories = [
        r["category"] for r in requests.select("category")
        .where(F.col("category").isNotNull()).distinct().orderBy("category").collect()
    ]
    listing_categories = [
        r["category"] for r in listings.select("category")
        .where(F.col("category").isNotNull()).distinct().orderBy("category").collect()
    ]
    _check(checks, "request_categories_present", bool(request_categories),
           request_categories, "Distinct request categories captured.")
    _check(checks, "listing_categories_present", bool(listing_categories),
           listing_categories, "Distinct listing categories captured.")

    orphan_requests = gold.select("request_id").distinct().join(
        requests.select("request_id").distinct(), "request_id", "left_anti"
    ).count()
    _check(checks, "gold_requests_exist_in_silver", orphan_requests == 0,
           orphan_requests, "Gold request ids trace to Silver.")

    category_mismatch = gold.alias("g").join(
        requests.select("request_id", "category").alias("r"),
        F.col("g.request_id") == F.col("r.request_id"), "left"
    ).filter(
        F.col("r.request_id").isNull() | (F.col("g.category") != F.col("r.category"))
    ).count()
    _check(checks, "gold_category_matches_request_category", category_mismatch == 0,
           category_mismatch, "Gold preserves trusted request category.")

    invalid_routes = routes.filter(
        (F.col("distance_km").isNotNull() & (F.col("distance_km") < 0))
        | (F.col("duration_min").isNotNull() & (F.col("duration_min") < 0))
    ).count()
    _check(checks, "silver_routes_non_negative", invalid_routes == 0,
           invalid_routes, "Route distance/duration cannot be negative.")

    pending = gold.filter(F.col("route_status") == "PENDING").count()
    _check(checks, "gold_has_no_pending_routes", pending == 0, pending,
           "Gold must not contain unresolved routes.")

    invalid_scores = gold.filter(
        F.col("match_score").isNull()
        | (F.col("match_score") < 0)
        | (F.col("match_score") > 1)
    ).count()
    _check(checks, "gold_match_score_bounds", invalid_scores == 0,
           invalid_scores, "match_score must be within [0,1].")

    dup_pairs = gold.groupBy("request_id", "listing_id").count().filter("count > 1").count()
    _check(checks, "gold_unique_request_listing_pair", dup_pairs == 0,
           dup_pairs, "One Gold row per request/listing pair.")

    bad_docs = docs.filter(
        F.col("listing_id").isNull() | F.col("search_text").isNull()
    ).count()
    _check(checks, "search_docs_required_fields", bad_docs == 0, bad_docs,
           "Search docs require listing_id and search_text.")

    latest = log.filter(F.col("stage").isin(list(EXPECTED_STAGES))).withColumn(
        "_rn",
        F.row_number().over(
            Window.partitionBy("stage").orderBy(
                F.col("ended_at").desc(), F.col("started_at").desc()
            )
        ),
    ).filter(F.col("_rn") == 1).select("stage", "status").collect()

    status_by_stage = {r["stage"]: r["status"] for r in latest}
    missing_stages = [s for s in EXPECTED_STAGES if s not in status_by_stage]
    failed_stages = [s for s in EXPECTED_STAGES if status_by_stage.get(s) not in (None, "PASS")]
    _check(checks, "latest_pipeline_stages_pass",
           not missing_stages and not failed_stages,
           {"missing": missing_stages, "failed": failed_stages},
           "Every expected 90/91 stage has a latest PASS.")

    summary = _summary(checks)
    summary.update(
        request_count=counts["silver_requests"],
        request_categories=request_categories,
        listing_categories=listing_categories,
        gold_match_count=counts["gold_candidate_matches"],
        search_doc_count=counts["gold_listing_search_docs"],
    )
    return summary, checks


def _summary(checks: list[ValidationCheck]) -> dict[str, Any]:
    failed = [c.check_name for c in checks if c.status == "FAIL"]
    return {
        "status": "PASS" if not failed else "FAIL",
        "request_count": 0,
        "request_categories": [],
        "listing_categories": [],
        "gold_match_count": 0,
        "search_doc_count": 0,
        "failed_checks": failed,
    }

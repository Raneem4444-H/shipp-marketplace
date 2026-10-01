"""Stage 8 — match scoring v1 (structured). The only scoring contract in the repo.

match_score = w_distance * distance_score + w_timing * timing_score + w_condition * condition_score
All components are in [0, 1]. Distance is never invented: no OK route -> distance_score = 0.
"""

from pyspark.sql import Column
from pyspark.sql import functions as F

from config.settings import SCORING


def condition_score(condition_col: Column) -> Column:
    expr = F.lit(SCORING["condition_default"])
    for code, score in SCORING["condition_scores"].items():
        expr = F.when(condition_col == code, F.lit(score)).otherwise(expr)
    return expr


def timing_score(available_from: Column, need_by_date: Column, now: Column) -> Column:
    """min(1, slack_days / N): how much time is left between availability and need-by."""
    available_at = F.greatest(F.coalesce(available_from, now), now)
    slack_days = F.datediff(need_by_date, available_at)
    score = F.least(F.lit(1.0), F.greatest(F.lit(0.0),
                    slack_days / F.lit(float(SCORING["timing_full_score_days"]))))
    return F.when(need_by_date.isNull(), F.lit(1.0)).otherwise(score)


def distance_score(route_status: Column, route_distance_km: Column) -> Column:
    return F.when(
        route_status == "OK",
        F.greatest(F.lit(0.0), F.lit(1.0) - route_distance_km / F.lit(float(SCORING["max_route_km"]))),
    ).otherwise(F.lit(0.0))


def match_score(distance: Column, timing: Column, condition: Column) -> Column:
    w = SCORING["weights"]
    return F.round(
        F.lit(w["distance"]) * distance + F.lit(w["timing"]) * timing + F.lit(w["condition"]) * condition, 4
    )


def assert_weights_valid() -> None:
    total = sum(SCORING["weights"].values())
    assert abs(total - 1.0) < 1e-9, f"Scoring weights must sum to 1.0 (got {total})."

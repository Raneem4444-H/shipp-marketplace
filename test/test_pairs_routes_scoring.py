import datetime as dt
import json

from pyspark.sql import functions as F

from data_pipeline.gold.scoring import assert_weights_valid, condition_score, distance_score
from data_pipeline.silver.pairs import build_candidate_pairs
from data_pipeline.silver.routes import BRONZE_ROUTE_SCHEMA, parse_route_responses

NOW = dt.datetime(2026, 9, 30, 12, 0)
LISTING_SCHEMA = ("listing_id string, donor_id string, category string, status string, latitude double, "
                  "longitude double, available_from timestamp_ntz, available_until timestamp_ntz")
REQUEST_SCHEMA = ("request_id string, requester_id string, category string, status string, latitude double, "
                  "longitude double, need_by_date timestamp_ntz")


def test_pairs_apply_every_eligibility_rule(spark):
    later = NOW + dt.timedelta(days=30)
    listings = spark.createDataFrame([
        ("ok", "d1", "FURNITURE", "AVAILABLE", 24.4976, 54.4075, NOW, later),
        ("wrong_cat", "d1", "BOOKS", "AVAILABLE", 24.4976, 54.4075, NOW, later),
        ("draft", "d1", "FURNITURE", "DRAFT", 24.4976, 54.4075, NOW, later),
        ("expired", "d1", "FURNITURE", "AVAILABLE", 24.4976, 54.4075, NOW, NOW - dt.timedelta(days=1)),
        ("doha", "d1", "FURNITURE", "AVAILABLE", 25.2854, 51.5310, NOW, later),
        ("self", "r1", "FURNITURE", "AVAILABLE", 24.4976, 54.4075, NOW, later),
    ], LISTING_SCHEMA)
    requests_df = spark.createDataFrame(
        [("req", "r1", "FURNITURE", "OPEN", 24.5014, 54.3872, later)], REQUEST_SCHEMA)
    pairs = build_candidate_pairs(listings, requests_df, F.lit(NOW).cast("timestamp_ntz")).collect()
    assert [p.listing_id for p in pairs] == ["ok"]
    assert pairs[0].origin_key == "24.4976,54.4075" and pairs[0].dest_key == "24.5014,54.3872"
    assert 1.5 < pairs[0].straight_line_km < 2.5


def test_routes_parse_ok_no_route_and_skip_failures(spark):
    body = json.dumps({"distances": [[6.4], [None]], "durations": [[840.0], [None]]})
    rows = [
        ("b1", NOW, "driving-car", "D", ["A", "B"], "{}", 200, body, None, 1, 100),
        ("b2", NOW, "driving-car", "D", ["C"], "{}", 429, "slow", "HTTP 429", 5, 100),
    ]
    routes = {r.origin_key: r for r in parse_route_responses(spark.createDataFrame(rows, BRONZE_ROUTE_SCHEMA)).collect()}
    assert set(routes) == {"A", "B"}
    assert routes["A"].route_status == "OK" and routes["A"].distance_km == 6.4 and routes["A"].duration_min == 14.0
    assert routes["B"].route_status == "NO_ROUTE" and routes["B"].distance_km is None


def test_scoring_components(spark):
    assert_weights_valid()
    df = spark.createDataFrame([("OK", 10.0, "GOOD"), ("PENDING", None, "BROKEN")],
                               "rs string, km double, cond string")
    out = df.select(distance_score(F.col("rs"), F.col("km")).alias("d"),
                    condition_score(F.col("cond")).alias("c")).collect()
    assert out[0].d == 0.8 and out[0].c == 0.75
    assert out[1].d == 0.0 and out[1].c == 0.3

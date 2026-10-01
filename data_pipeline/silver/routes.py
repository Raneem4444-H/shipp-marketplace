"""Stage 7B — parse raw ORS Matrix responses (Bronze) into one row per route key (Silver)."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window

BRONZE_ROUTE_SCHEMA = (
    "batch_id string, called_at timestamp, profile string, dest_key string, "
    "origin_keys array<string>, request_json string, http_status int, "
    "response_body string, error_message string, attempts int, latency_ms long"
)
RESPONSE_SCHEMA = "struct<distances: array<array<double>>, durations: array<array<double>>>"

ROUTE_COLUMNS = [
    "origin_key", "dest_key", "profile", "distance_km", "duration_min",
    "route_status", "source_batch_id", "fetched_at",
]


def parse_route_responses(bronze_routes: DataFrame) -> DataFrame:
    """Latest successful response per (origin_key, dest_key, profile).

    route_status = OK when ORS returned both numbers, NO_ROUTE when it answered with nulls.
    Failed calls (non-200 or error_message set) are excluded, so they are retried next run.
    """
    parsed = (
        bronze_routes
        .filter((F.col("http_status") == 200) & F.col("error_message").isNull())
        .withColumn("parsed", F.from_json("response_body", RESPONSE_SCHEMA))
        .select("batch_id", "called_at", "profile", "dest_key", "parsed",
                F.posexplode("origin_keys").alias("pos", "origin_key"))
        .select(
            "origin_key", "dest_key", "profile",
            F.element_at(F.element_at("parsed.distances", F.col("pos") + 1), 1).alias("distance_km"),
            (F.element_at(F.element_at("parsed.durations", F.col("pos") + 1), 1) / 60.0).alias("duration_min"),
            F.col("batch_id").alias("source_batch_id"),
            F.col("called_at").alias("fetched_at"),
        )
    )
    latest = Window.partitionBy("origin_key", "dest_key", "profile").orderBy(F.col("fetched_at").desc())
    return (
        parsed
        .withColumn("_rn", F.row_number().over(latest))
        .filter("_rn = 1")
        .drop("_rn")
        .withColumn("route_status",
                    F.when(F.col("distance_km").isNotNull() & F.col("duration_min").isNotNull(), "OK")
                     .otherwise("NO_ROUTE"))
        .withColumn("distance_km", F.when(F.col("route_status") == "OK", F.round("distance_km", 3)))
        .withColumn("duration_min", F.when(F.col("route_status") == "OK", F.round("duration_min", 1)))
        .select(*ROUTE_COLUMNS)
    )

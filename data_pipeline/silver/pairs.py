"""Stage 6 — eligible (listing, request) pairs. Pure transform: DataFrames in, DataFrame out."""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from config.settings import (
    ELIGIBLE_LISTING_STATUSES,
    ELIGIBLE_REQUEST_STATUSES,
    MAX_STRAIGHT_LINE_KM,
    ORS_PROFILE,
    ROUTE_KEY_DECIMALS,
)
from data_pipeline.common.geo import coord_key, haversine_km

PAIR_COLUMNS = [
    "pair_id", "listing_id", "request_id", "donor_id", "requester_id", "category",
    "origin_lat", "origin_lon", "dest_lat", "dest_lon",
    "origin_key", "dest_key", "profile", "straight_line_km",
]


def eligible_listings(listings: DataFrame, now: Column) -> DataFrame:
    return (
        listings
        .filter(F.col("status").isin(ELIGIBLE_LISTING_STATUSES))
        .filter(F.col("latitude").isNotNull() & F.col("longitude").isNotNull())
        .filter(F.col("available_until").isNull() | (F.col("available_until") >= now))
    )


def eligible_requests(requests_df: DataFrame, now: Column) -> DataFrame:
    return (
        requests_df
        .filter(F.col("status").isin(ELIGIBLE_REQUEST_STATUSES))
        .filter(F.col("latitude").isNotNull() & F.col("longitude").isNotNull())
        .filter(F.col("need_by_date").isNull() | (F.col("need_by_date") >= now))
    )


def build_candidate_pairs(listings: DataFrame, requests_df: DataFrame, now: Column,
                          max_straight_line_km: float = MAX_STRAIGHT_LINE_KM) -> DataFrame:
    l = eligible_listings(listings, now).alias("l")
    r = eligible_requests(requests_df, now).alias("r")
    return (
        l.join(r, F.col("l.category") == F.col("r.category"), "inner")
        .filter(F.col("l.donor_id") != F.col("r.requester_id"))
        .filter(F.col("l.available_from").isNull() | F.col("r.need_by_date").isNull()
                | (F.col("l.available_from") <= F.col("r.need_by_date")))
        .select(
            F.sha2(F.concat_ws("|", F.col("l.listing_id"), F.col("r.request_id")), 256).alias("pair_id"),
            F.col("l.listing_id"), F.col("r.request_id"),
            F.col("l.donor_id"), F.col("r.requester_id"),
            F.col("l.category").alias("category"),
            F.round(F.col("l.latitude"), ROUTE_KEY_DECIMALS).alias("origin_lat"),
            F.round(F.col("l.longitude"), ROUTE_KEY_DECIMALS).alias("origin_lon"),
            F.round(F.col("r.latitude"), ROUTE_KEY_DECIMALS).alias("dest_lat"),
            F.round(F.col("r.longitude"), ROUTE_KEY_DECIMALS).alias("dest_lon"),
        )
        .withColumn("origin_key", coord_key("origin_lat", "origin_lon"))
        .withColumn("dest_key", coord_key("dest_lat", "dest_lon"))
        .withColumn("profile", F.lit(ORS_PROFILE))
        .withColumn("straight_line_km", F.round(
            haversine_km(F.col("origin_lat"), F.col("origin_lon"), F.col("dest_lat"), F.col("dest_lon")), 3))
        .filter(F.col("straight_line_km") <= max_straight_line_km)
        .select(*PAIR_COLUMNS)
    )

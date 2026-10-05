# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
"""
Shipp - external seed pipeline (donors, requesters, listings, requests, routes)

Flow (one stage's output is the next stage's input):

    DummyJSON /users                -> bronze_external_users
    DummyJSON /products/category/*  -> bronze_external_listings
                                         |
                                         v
    silver_external_users     (donor / requester role, PII dropped)
    silver_external_listings  (one row = one listing)
    silver_external_requests  (one row = one request, SYNTHETIC - see note)
                                         |
    OpenRouteService Matrix   -> bronze_route_responses -> silver_routes
                                         |
                                         v
    gold_candidate_matches_external  (one row = one request_id + listing_id pair)

What is real and what is not:
  * Users and products are pulled live over HTTP from dummyjson.com (free, no key).
  * No public API publishes "requests for household items", so requests are derived
    from the requester users and tagged data_origin = 'synthetic_derived'.
  * DummyJSON coordinates are random and not routable, so every user is assigned
    to one of the districts in LOCATIONS. That column is tagged
    location_origin = 'synthetic_assigned'.

Runs as a Databricks notebook/job or locally through Databricks Connect.
The ORS key is read from a secret scope. It is never written in this file.
"""

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone

import requests
from pyspark.sql import Window
from pyspark.sql import functions as F

if "spark" not in globals():
    try:
        from databricks.connect import DatabricksSession

        spark = DatabricksSession.builder.getOrCreate()
    except ImportError:
        from pyspark.sql import SparkSession

        spark = SparkSession.builder.getOrCreate()


# COMMAND ----------

# ----------------------------- CONFIG ---------------------------------------

CATALOG = "bootcamp_students"
BRONZE = "shipp_bronze"
SILVER = "shipp_silver"
GOLD = "shipp_gold"

# Kept separate from the Lakebase-fed tables so this job can never overwrite them.
T_BRONZE_USERS = f"{CATALOG}.{BRONZE}.bronze_external_users"
T_BRONZE_LISTINGS = f"{CATALOG}.{BRONZE}.bronze_external_listings"
T_BRONZE_ROUTES = f"{CATALOG}.{BRONZE}.bronze_route_responses"
T_SILVER_USERS = f"{CATALOG}.{SILVER}.silver_external_users"
T_SILVER_LISTINGS = f"{CATALOG}.{SILVER}.silver_external_listings"
T_SILVER_REQUESTS = f"{CATALOG}.{SILVER}.silver_external_requests"
T_SILVER_ROUTES = f"{CATALOG}.{SILVER}.silver_routes"
T_GOLD_MATCHES = f"{CATALOG}.{GOLD}.gold_candidate_matches_external"

# Secret location - change to the scope/key your team actually created.
SECRET_SCOPE = "shipp"
SECRET_KEY = "ors_api_key"

DUMMYJSON = "https://dummyjson.com"
LISTING_CATEGORIES = ["furniture", "home-decoration", "kitchen-accessories"]

ORS_MATRIX_URL = "https://api.openrouteservice.org/v2/matrix/driving-car"

# Fixed anchor so re-running on a different day produces the same dates.
ANCHOR_DATE = "2026-10-05"

MAX_RETRIES = 4
BACKOFF_SECONDS = 2
RETRYABLE = {-1, 429, 500, 502, 503, 504}

# location_id MUST equal the position in this list (it is the ORS matrix index).
# Coordinates are approximate district centres. Swap for your own city if needed.
LOCATIONS = [
    (0, "Dubai Marina", 25.0805, 55.1403),
    (1, "Downtown Dubai", 25.1972, 55.2744),
    (2, "Jumeirah Lakes Towers", 25.0693, 55.1417),
    (3, "Business Bay", 25.1850, 55.2650),
    (4, "Al Barsha", 25.1107, 55.2000),
    (5, "Deira", 25.2711, 55.3075),
    (6, "Jumeirah", 25.2285, 55.2610),
    (7, "Mirdif", 25.2200, 55.4200),
    (8, "Dubai Silicon Oasis", 25.1212, 55.3773),
    (9, "Al Nahda", 25.2930, 55.3700),
]

# PLACEHOLDER scoring - replace once the team finalises the formula.
SCORING_VERSION = "v0_placeholder"
W_DISTANCE = 0.6
W_AVAILABILITY = 0.4
MAX_DISTANCE_KM = 50.0

BRONZE_DDL = (
    "record_key string, payload string, payload_hash string, http_status int, "
    "source_url string, data_origin string, batch_id string, ingested_at timestamp"
)


# COMMAND ----------

# ----------------------------- HELPERS --------------------------------------


def get_secret(scope, key):
    """Works in a notebook (dbutils) and through Databricks Connect (SDK)."""
    try:
        return dbutils.secrets.get(scope, key)  # noqa: F821 - notebook global
    except NameError:
        from databricks.sdk import WorkspaceClient

        return WorkspaceClient().dbutils.secrets.get(scope, key)


def http_call(method, url, **kwargs):
    """HTTP with retry/backoff. Returns (status, body_text). Never raises on HTTP errors."""
    status, text = -1, ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.request(method, url, timeout=30, **kwargs)
            status, text = resp.status_code, resp.text
        except requests.RequestException as exc:
            status, text = -1, json.dumps({"error": str(exc)})
        if status == 200:
            return status, text
        if status in RETRYABLE and attempt < MAX_RETRIES:
            wait = BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(f"  {method} {url} -> {status}, retry {attempt}/{MAX_RETRIES} in {wait}s")
            time.sleep(wait)
            continue
        break
    return status, text


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def bronze_row(record_key, payload_text, status, source_url, data_origin, batch_id):
    return (
        str(record_key),
        payload_text,
        sha(payload_text),
        int(status),
        source_url,
        data_origin,
        batch_id,
        datetime.now(timezone.utc),
    )


def write_bronze(table, rows):
    """Append-only raw landing. Same record + same payload is never inserted twice."""
    spark.sql(f"CREATE TABLE IF NOT EXISTS {table} ({BRONZE_DDL}) USING DELTA")
    if not rows:
        return
    spark.createDataFrame(rows, schema=BRONZE_DDL).createOrReplaceTempView("_bronze_incoming")
    spark.sql(
        f"""
        MERGE INTO {table} t
        USING _bronze_incoming s
          ON t.record_key = s.record_key AND t.payload_hash = s.payload_hash
        WHEN NOT MATCHED THEN INSERT *
        """
    )


def latest_per_key(df):
    w = Window.partitionBy("record_key").orderBy(F.col("ingested_at").desc())
    return df.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")


def overwrite(df, table):
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(table)


def locations_df():
    return spark.createDataFrame(
        LOCATIONS, "location_id int, location string, latitude double, longitude double"
    )


# COMMAND ----------

# ----------------------------- 1. BRONZE ------------------------------------


def ingest_users(batch_id):
    url = f"{DUMMYJSON}/users?limit=0"
    status, text = http_call("GET", url)
    if status != 200:
        raise RuntimeError(f"DummyJSON users failed: {status} {text[:200]}")
    rows = [
        bronze_row(u["id"], json.dumps(u, sort_keys=True), 200, url, "external_dummyjson", batch_id)
        for u in json.loads(text)["users"]
    ]
    write_bronze(T_BRONZE_USERS, rows)
    print(f"[bronze] users fetched: {len(rows)}")


def ingest_listings(batch_id):
    rows = []
    for category in LISTING_CATEGORIES:
        url = f"{DUMMYJSON}/products/category/{category}?limit=0"
        status, text = http_call("GET", url)
        if status != 200:
            raise RuntimeError(f"DummyJSON {category} failed: {status} {text[:200]}")
        for p in json.loads(text)["products"]:
            rows.append(
                bronze_row(
                    p["id"], json.dumps(p, sort_keys=True), 200, url, "external_dummyjson", batch_id
                )
            )
    write_bronze(T_BRONZE_LISTINGS, rows)
    print(f"[bronze] listings fetched: {len(rows)}")


# COMMAND ----------

# ----------------------------- 2. SILVER ------------------------------------


def build_silver_users():
    raw = latest_per_key(spark.table(T_BRONZE_USERS))
    users = (
        raw.select(
            F.get_json_object("payload", "$.id").cast("int").alias("source_user_id"),
            F.get_json_object("payload", "$.firstName").alias("display_name"),
            "data_origin",
            "ingested_at",
        )
        # Rule: a user without an id cannot be keyed, so it is rejected (and counted).
        .where(F.col("source_user_id").isNotNull())
        .withColumn("user_id", F.concat(F.lit("ext_u_"), F.col("source_user_id").cast("string")))
        .withColumn(
            "role",
            F.when(F.col("source_user_id") % 2 == 0, F.lit("DONOR")).otherwise(F.lit("REQUESTER")),
        )
        .withColumn(
            "location_id", F.pmod(F.col("source_user_id"), F.lit(len(LOCATIONS))).cast("int")
        )
        .join(F.broadcast(locations_df()), "location_id")
        .withColumn("location_origin", F.lit("synthetic_assigned"))
        # email, phone, address, etc. stay in Bronze only (spec 6.4 / 9.1)
        .select(
            "user_id",
            "source_user_id",
            "display_name",
            "role",
            "location_id",
            "location",
            "latitude",
            "longitude",
            "location_origin",
            "data_origin",
            "ingested_at",
        )
    )
    overwrite(users, T_SILVER_USERS)
    print(f"[silver] users: {spark.table(T_SILVER_USERS).count()} (bronze keys: {raw.count()})")


def build_silver_listings():
    raw = latest_per_key(spark.table(T_BRONZE_LISTINGS))
    donors = (
        spark.table(T_SILVER_USERS)
        .where("role = 'DONOR'")
        .withColumn("donor_idx", F.row_number().over(Window.orderBy("source_user_id")) - 1)
        .select(
            "donor_idx",
            F.col("user_id").alias("donor_id"),
            "location_id",
            "location",
            "latitude",
            "longitude",
        )
    )
    n_donors = donors.count()
    if n_donors == 0:
        raise RuntimeError("No donors in silver_external_users - cannot assign listings.")

    anchor = F.lit(ANCHOR_DATE).cast("date")
    conditions = F.array(F.lit("like_new"), F.lit("good"), F.lit("fair"))

    parsed = raw.select(
        F.get_json_object("payload", "$.id").cast("int").alias("source_listing_id"),
        F.trim(F.get_json_object("payload", "$.title")).alias("title"),
        F.trim(F.get_json_object("payload", "$.description")).alias("description"),
        F.lower(F.get_json_object("payload", "$.category")).alias("category"),
        "data_origin",
        "ingested_at",
    )
    # Rule: id, title and category are required. Rows missing any are rejected, not patched.
    valid = parsed.where(
        F.col("source_listing_id").isNotNull()
        & F.col("title").isNotNull()
        & F.col("category").isin(LISTING_CATEGORIES)
    )
    sid = F.col("source_listing_id")
    listings = (
        valid.withColumn("donor_idx", F.pmod(sid * 7, F.lit(n_donors)).cast("int"))
        .join(donors, "donor_idx")
        .withColumn("listing_id", F.concat(F.lit("ext_l_"), sid.cast("string")))
        .withColumn("condition", F.element_at(conditions, (F.pmod(sid, F.lit(3)) + 1).cast("int")))
        .withColumn("available_from", F.date_sub(anchor, F.pmod(sid, F.lit(10)).cast("int")))
        .withColumn("available_until", F.date_add(anchor, (F.pmod(sid, F.lit(30)) + 30).cast("int")))
        .withColumn("status", F.lit("Available"))
        .select(
            "listing_id",
            "donor_id",
            "title",
            "description",
            "category",
            "condition",
            "location_id",
            "location",
            "latitude",
            "longitude",
            "available_from",
            "available_until",
            "status",
            F.col("ingested_at").alias("updated_at"),
            "data_origin",
        )
    )
    overwrite(listings, T_SILVER_LISTINGS)
    accepted = spark.table(T_SILVER_LISTINGS).count()
    print(f"[silver] listings accepted: {accepted}, rejected: {raw.count() - accepted}")


def build_silver_requests():
    anchor = F.lit(ANCHOR_DATE).cast("date")
    categories = F.array(*[F.lit(c) for c in LISTING_CATEGORIES])
    sid = F.col("source_user_id")
    requests_df = (
        spark.table(T_SILVER_USERS)
        .where("role = 'REQUESTER'")
        .withColumn("request_id", F.concat(F.lit("ext_r_"), sid.cast("string")))
        .withColumn(
            "category",
            F.element_at(categories, (F.pmod(sid, F.lit(len(LISTING_CATEGORIES))) + 1).cast("int")),
        )
        .withColumn(
            "request_text",
            F.concat(
                F.lit("Looking for "),
                F.regexp_replace("category", "-", " "),
                F.lit(" items near "),
                F.col("location"),
            ),
        )
        .withColumn("need_by_date", F.date_add(anchor, (F.pmod(sid, F.lit(28)) + 7).cast("int")))
        .withColumn("status", F.lit("Open"))
        .select(
            "request_id",
            F.col("user_id").alias("requester_id"),
            "request_text",
            "category",
            "location_id",
            "location",
            "latitude",
            "longitude",
            "need_by_date",
            "status",
            F.col("ingested_at").alias("updated_at"),
            F.lit("synthetic_derived").alias("data_origin"),
        )
    )
    overwrite(requests_df, T_SILVER_REQUESTS)
    print(f"[silver] requests: {spark.table(T_SILVER_REQUESTS).count()}")


# COMMAND ----------

# ----------------------------- 3. ROUTES (ORS) ------------------------------


def route_request():
    """One matrix call covers every district pair. Returns (body, request_hash)."""
    for idx, loc in enumerate(LOCATIONS):
        if loc[0] != idx:
            raise ValueError("LOCATIONS: location_id must equal the list position.")
    body = {
        "locations": [[lon, lat] for (_, _, lat, lon) in LOCATIONS],  # ORS wants [lon, lat]
        "metrics": ["distance", "duration"],
        "units": "km",
    }
    return body, sha(json.dumps({"url": ORS_MATRIX_URL, "body": body}, sort_keys=True))


def ingest_routes(batch_id):
    body, request_hash = route_request()
    spark.sql(f"CREATE TABLE IF NOT EXISTS {T_BRONZE_ROUTES} ({BRONZE_DDL}) USING DELTA")

    cached = (
        spark.table(T_BRONZE_ROUTES)
        .where((F.col("record_key") == request_hash) & (F.col("http_status") == 200))
        .limit(1)
        .count()
    )
    if cached:
        print("[bronze] routes: cache hit, ORS not called")
        return request_hash

    api_key = get_secret(SECRET_SCOPE, SECRET_KEY)
    status, text = http_call(
        "POST",
        ORS_MATRIX_URL,
        json=body,
        headers={"Authorization": api_key, "Content-Type": "application/json"},
    )
    # Failures are stored too: that row is the failure log. Nothing is invented downstream.
    write_bronze(
        T_BRONZE_ROUTES,
        [bronze_row(request_hash, text, status, ORS_MATRIX_URL, "external_openrouteservice", batch_id)],
    )
    print(f"[bronze] routes: ORS called, http_status={status}")
    return request_hash


def build_silver_routes(request_hash):
    raw = (
        spark.table(T_BRONZE_ROUTES)
        .where((F.col("record_key") == request_hash) & (F.col("http_status") == 200))
        .orderBy(F.col("ingested_at").desc())
        .limit(1)
    )
    parsed = raw.select(
        F.from_json(
            "payload", "distances array<array<double>>, durations array<array<double>>"
        ).alias("j"),
        "ingested_at",
    )
    by_origin = parsed.select(
        F.posexplode("j.distances").alias("origin_location_id", "distance_row"),
        F.col("j.durations").alias("durations"),
        "ingested_at",
    )
    by_pair = by_origin.select(
        "origin_location_id",
        F.posexplode("distance_row").alias("dest_location_id", "distance_km"),
        "durations",
        "ingested_at",
    )
    routes = by_pair.select(
        "origin_location_id",
        "dest_location_id",
        F.round("distance_km", 2).alias("distance_km"),
        F.round(
            F.col("durations")[F.col("origin_location_id")][F.col("dest_location_id")] / 60, 1
        ).alias("duration_min"),
        F.lit("openrouteservice").alias("route_source"),
        F.col("ingested_at").alias("fetched_at"),
    )
    overwrite(routes, T_SILVER_ROUTES)
    print(f"[silver] routes: {spark.table(T_SILVER_ROUTES).count()} (expected {len(LOCATIONS) ** 2})")


# COMMAND ----------

# ----------------------------- 4. GOLD --------------------------------------


def build_gold_matches():
    """Grain: one row per (request_id, listing_id)."""
    r = spark.table(T_SILVER_REQUESTS).where("status = 'Open'").alias("r")
    l = spark.table(T_SILVER_LISTINGS).where("status = 'Available'").alias("l")
    rt = spark.table(T_SILVER_ROUTES).alias("rt")

    pairs = r.join(
        l,
        (F.col("r.category") == F.col("l.category"))
        & (F.col("l.available_from") <= F.col("r.need_by_date")),
    )
    scored = (
        pairs.join(
            rt,
            (F.col("rt.origin_location_id") == F.col("l.location_id"))
            & (F.col("rt.dest_location_id") == F.col("r.location_id")),
            "left",
        )
        .select(
            F.col("r.request_id").alias("request_id"),
            F.col("l.listing_id").alias("listing_id"),
            F.col("r.requester_id").alias("requester_id"),
            F.col("l.donor_id").alias("donor_id"),
            F.col("r.category").alias("category"),
            F.col("rt.distance_km").alias("distance_km"),
            F.col("rt.duration_min").alias("duration_min"),
            F.when(F.col("l.available_until") >= F.col("r.need_by_date"), F.lit(1.0))
            .otherwise(F.lit(0.5))
            .alias("availability_score"),
        )
        .withColumn(
            "distance_score",
            F.lit(1.0) - F.least(F.col("distance_km") / F.lit(MAX_DISTANCE_KM), F.lit(1.0)),
        )
        # No route -> no score. A missing distance is never replaced with a guess.
        .withColumn(
            "match_score",
            F.when(
                F.col("distance_km").isNotNull(),
                F.round(
                    F.lit(W_DISTANCE) * F.col("distance_score")
                    + F.lit(W_AVAILABILITY) * F.col("availability_score"),
                    4,
                ),
            ),
        )
        .withColumn(
            "route_status",
            F.when(F.col("distance_km").isNull(), F.lit("MISSING")).otherwise(F.lit("OK")),
        )
        .withColumn(
            "match_rank",
            F.row_number().over(
                Window.partitionBy("request_id").orderBy(
                    F.col("match_score").desc_nulls_last(), F.col("listing_id")
                )
            ),
        )
        .withColumn("scoring_version", F.lit(SCORING_VERSION))
        .withColumn("computed_at", F.current_timestamp())
    )
    overwrite(scored, T_GOLD_MATCHES)
    print(f"[gold] candidate matches: {spark.table(T_GOLD_MATCHES).count()}")


# COMMAND ----------

# ----------------------------- 5. QUALITY CHECKS ----------------------------


def run_quality_checks():
    gold = spark.table(T_GOLD_MATCHES)
    listings = spark.table(T_SILVER_LISTINGS)
    requests_df = spark.table(T_SILVER_REQUESTS)

    total = gold.count()
    checks = {
        "gold has rows": total > 0,
        "gold grain unique (request_id, listing_id)": gold.select("request_id", "listing_id")
        .distinct()
        .count()
        == total,
        "gold keys not null": gold.where("request_id IS NULL OR listing_id IS NULL").count() == 0,
        "gold.listing_id exists in silver": gold.join(listings, "listing_id", "left_anti").count()
        == 0,
        "gold.request_id exists in silver": gold.join(requests_df, "request_id", "left_anti").count()
        == 0,
        "silver listing_id unique": listings.select("listing_id").distinct().count()
        == listings.count(),
        "match_score within 0..1": gold.where("match_score < 0 OR match_score > 1").count() == 0,
    }
    missing_routes = gold.where("route_status = 'MISSING'").count()

    print("\n----- DATA QUALITY -----")
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}  {name}")
    print(f"INFO  matches without a route: {missing_routes} of {total}")

    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError(f"Data quality failed: {failed}")


# COMMAND ----------

# ----------------------------- RUN ------------------------------------------


def main():
    batch_id = str(uuid.uuid4())
    print(f"batch_id = {batch_id}")

    ingest_users(batch_id)
    ingest_listings(batch_id)

    build_silver_users()
    build_silver_listings()
    build_silver_requests()

    request_hash = ingest_routes(batch_id)
    build_silver_routes(request_hash)

    build_gold_matches()
    run_quality_checks()


if __name__ == "__main__":
    main()
# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
"""
Shipp - Supabase operational pipeline (donors, requesters, listings, requests, routes)

Flow (one stage's output is the next stage's input):

    Supabase REST  users / listings / requests
            |
            v
    BRONZE  bronze_supabase_users / _listings / _requests   (raw JSON, one row per record)
            |
            v
    SILVER  silver_listings*   one row = one listing
            silver_requests*   one row = one request
            silver_users*      one row = one user (is_donor / is_requester, PII dropped)
            |
    OpenRouteService Matrix -> bronze_route_responses -> silver_routes*
            |
            v
    GOLD    gold_candidate_matches*   one row = one (request_id, listing_id) pair

    * every Silver/Gold table gets TABLE_SUFFIX so this job cannot overwrite the
      Lakebase-fed tables. Set TABLE_SUFFIX = "" once the team agrees this is the main path.

Keys:
    - Supabase publishable key: public by design, kept below as a constant.
    - Supabase secret key and ORS key: read from the Databricks secret scope at runtime.
      Their VALUES are never written in this file. Only their NAMES are.

How it reads Supabase: a full snapshot poll on every run. That is not CDC. Rows deleted
in Supabase drop out of Silver on the next run because Silver only uses records seen in
the current batch.

Runs as a Databricks notebook/job or locally through Databricks Connect.
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
TABLE_SUFFIX = "_supabase"

T_BRONZE_USERS = f"{CATALOG}.{BRONZE}.bronze_supabase_users"
T_BRONZE_LISTINGS = f"{CATALOG}.{BRONZE}.bronze_supabase_listings"
T_BRONZE_REQUESTS = f"{CATALOG}.{BRONZE}.bronze_supabase_requests"
T_BRONZE_ROUTES = f"{CATALOG}.{BRONZE}.bronze_route_responses{TABLE_SUFFIX}"
T_SILVER_USERS = f"{CATALOG}.{SILVER}.silver_users{TABLE_SUFFIX}"
T_SILVER_LISTINGS = f"{CATALOG}.{SILVER}.silver_listings{TABLE_SUFFIX}"
T_SILVER_REQUESTS = f"{CATALOG}.{SILVER}.silver_requests{TABLE_SUFFIX}"
T_SILVER_ROUTES = f"{CATALOG}.{SILVER}.silver_routes{TABLE_SUFFIX}"
T_GOLD_MATCHES = f"{CATALOG}.{GOLD}.gold_candidate_matches{TABLE_SUFFIX}"

# ---- Supabase ----
SUPABASE_URL = "https://lwsotpufqjovxotlqdqj.supabase.co"
SUPABASE_PUBLISHABLE_KEY = "sb_publishable_X_v9CH2f8LXLnhxl02PwAg_j1-zVS4f"  # public by design

# "secret"      -> backend key from the secret scope. Bypasses row-level security. Use this.
# "publishable" -> public key above. Only returns rows your RLS read policies allow.
SUPABASE_KEY_MODE = "secret"

# (table name in Supabase, primary key column). Change if your names differ.
SUPABASE_USERS = ("users", "user_id")
SUPABASE_LISTINGS = ("listings", "listing_id")
SUPABASE_REQUESTS = ("requests", "request_id")
PAGE_SIZE = 1000

# ---- Secrets: NAMES only. Change the scope to the one your team created. ----
SECRET_SCOPE = "shipp"
SECRET_ORS_KEY = "ors_api_key"
SECRET_SUPABASE_KEY = "supabase_secret_key"

# ---- OpenRouteService ----
ORS_MATRIX_URL = "https://api.openrouteservice.org/v2/matrix/driving-car"
ORS_CHUNK = 50  # origins x destinations per call = 2,500 routes max
ORS_PAUSE_SECONDS = 1.6

MAX_RETRIES = 4
BACKOFF_SECONDS = 2
RETRYABLE = {-1, 429, 500, 502, 503, 504}

# ---- Matching (statuses compared in lower case) ----
LISTING_MATCHABLE_STATUSES = ["available"]
REQUEST_MATCHABLE_STATUSES = ["open", "matchesavailable"]

# PLACEHOLDER scoring - replace once the team finalises the formula.
SCORING_VERSION = "v0_placeholder"
W_DISTANCE = 0.6
W_AVAILABILITY = 0.4
MAX_DISTANCE_KM = 50.0

BRONZE_DDL = (
    "record_key string, payload string, payload_hash string, http_status int, "
    "source_url string, data_origin string, batch_id string, ingested_at timestamp, "
    "last_seen_batch_id string, last_seen_at timestamp"
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


def supabase_key():
    if SUPABASE_KEY_MODE == "publishable":
        return SUPABASE_PUBLISHABLE_KEY
    return get_secret(SECRET_SCOPE, SECRET_SUPABASE_KEY)


def http_call(method, url, **kwargs):
    """HTTP with retry/backoff. Returns (status, body_text). Never raises on HTTP errors."""
    status, text = -1, ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.request(method, url, timeout=30, **kwargs)
            status, text = resp.status_code, resp.text
        except requests.RequestException as exc:
            status, text = -1, json.dumps({"error": type(exc).__name__})
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


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def bronze_row(record_key, payload_text, status, source_url, data_origin, batch_id):
    now = datetime.now(timezone.utc)
    return (
        str(record_key),
        payload_text,
        sha(payload_text),
        int(status),
        source_url,
        data_origin,
        batch_id,
        now,
        batch_id,
        now,
    )


def write_bronze(table, rows):
    """
    Raw landing. A new payload version is inserted; an unchanged record only has its
    last_seen_* metadata refreshed, so re-running never duplicates data.
    """
    spark.sql(f"CREATE TABLE IF NOT EXISTS {table} ({BRONZE_DDL}) USING DELTA")
    unique = {(r[0], r[2]): r for r in rows}  # (record_key, payload_hash)
    if not unique:
        return
    spark.createDataFrame(list(unique.values()), schema=BRONZE_DDL).createOrReplaceTempView(
        "_bronze_incoming"
    )
    spark.sql(
        f"""
        MERGE INTO {table} t
        USING _bronze_incoming s
          ON t.record_key = s.record_key AND t.payload_hash = s.payload_hash
        WHEN MATCHED THEN UPDATE SET
          t.last_seen_batch_id = s.last_seen_batch_id,
          t.last_seen_at = s.last_seen_at
        WHEN NOT MATCHED THEN INSERT *
        """
    )


def current_snapshot(table, batch_id):
    """Records present in Supabase during this run, latest version per key."""
    df = spark.table(table).where(F.col("last_seen_batch_id") == batch_id)
    w = Window.partitionBy("record_key").orderBy(F.col("ingested_at").desc())
    return df.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")


def overwrite(df, table):
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(table)


def jstr(field):
    return F.expr(f"nullif(trim(get_json_object(payload, '$.{field}')), '')")


def jcast(field, dtype):
    # try_cast: a bad value becomes NULL (and is then rejected by a stated rule) instead of
    # crashing the job under ANSI mode.
    return F.expr(f"try_cast(get_json_object(payload, '$.{field}') as {dtype})")


def jdate(field):
    return F.expr(f"try_cast(substring(get_json_object(payload, '$.{field}'), 1, 10) as date)")


def valid_coords():
    return (
        F.col("latitude").between(-90, 90)
        & F.col("longitude").between(-180, 180)
        & F.col("latitude").isNotNull()
        & F.col("longitude").isNotNull()
    )


def location_key():
    # ~110 m precision. Two points in the same spot share one route lookup (cache key).
    return F.format_string("%.3f,%.3f", F.round("latitude", 3), F.round("longitude", 3))


# COMMAND ----------

# ----------------------------- 1. BRONZE ------------------------------------


def fetch_supabase_table(table, pk, api_key):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    records, offset = [], 0
    while True:
        status, text = http_call(
            "GET",
            url,
            params={"select": "*", "order": f"{pk}.asc", "limit": PAGE_SIZE, "offset": offset},
            headers={"apikey": api_key, "Accept": "application/json"},  # apikey header only
        )
        if status != 200:
            raise RuntimeError(
                f"Supabase table '{table}' failed with HTTP {status}: {text[:300]}\n"
                "401/403 -> wrong key or secret name. 404 -> table name wrong or not in the "
                "public schema (check SUPABASE_* names in CONFIG)."
            )
        page = json.loads(text)
        records.extend(page)
        if len(page) < PAGE_SIZE:
            return url, records
        offset += PAGE_SIZE


def ingest_supabase(source, bronze_table, api_key, batch_id):
    table, pk = source
    url, records = fetch_supabase_table(table, pk, api_key)
    rows = [
        bronze_row(
            rec[pk], json.dumps(rec, sort_keys=True), 200, url, "supabase_operational", batch_id
        )
        for rec in records
        if rec.get(pk) is not None
    ]
    write_bronze(bronze_table, rows)
    print(f"[bronze] {table}: fetched {len(records)}, keyed {len(rows)}")


# COMMAND ----------

# ----------------------------- 2. SILVER ------------------------------------


def build_silver_listings(batch_id):
    raw = current_snapshot(T_BRONZE_LISTINGS, batch_id)
    parsed = raw.select(
        jstr("listing_id").alias("listing_id"),
        jstr("donor_id").alias("donor_id"),
        jstr("title").alias("title"),
        jstr("description").alias("description"),
        F.lower(jstr("category")).alias("category"),
        F.lower(jstr("condition")).alias("condition"),
        jstr("location").alias("location"),
        jcast("latitude", "double").alias("latitude"),
        jcast("longitude", "double").alias("longitude"),
        jdate("available_from").alias("available_from"),
        jdate("available_until").alias("available_until"),
        jstr("status").alias("status"),
        jcast("updated_at", "timestamp").alias("updated_at"),
        "data_origin",
        "ingested_at",
    )
    # Rule: id, donor, category and valid coordinates are required. Rows that miss any of
    # them are rejected and counted - never patched with invented values.
    valid = parsed.where(
        F.col("listing_id").isNotNull()
        & F.col("donor_id").isNotNull()
        & F.col("category").isNotNull()
        & valid_coords()
    ).withColumn("location_key", location_key())
    overwrite(valid, T_SILVER_LISTINGS)
    accepted = spark.table(T_SILVER_LISTINGS).count()
    print(f"[silver] listings accepted: {accepted}, rejected: {raw.count() - accepted}")


def build_silver_requests(batch_id):
    raw = current_snapshot(T_BRONZE_REQUESTS, batch_id)
    parsed = raw.select(
        jstr("request_id").alias("request_id"),
        jstr("requester_id").alias("requester_id"),
        jstr("request_text").alias("request_text"),
        F.lower(jstr("category")).alias("category"),
        jstr("location").alias("location"),
        jcast("latitude", "double").alias("latitude"),
        jcast("longitude", "double").alias("longitude"),
        jdate("need_by_date").alias("need_by_date"),
        jstr("status").alias("status"),
        jcast("updated_at", "timestamp").alias("updated_at"),
        "data_origin",
        "ingested_at",
    )
    valid = parsed.where(
        F.col("request_id").isNotNull()
        & F.col("requester_id").isNotNull()
        & F.col("category").isNotNull()
        & valid_coords()
    ).withColumn("location_key", location_key())
    overwrite(valid, T_SILVER_REQUESTS)
    accepted = spark.table(T_SILVER_REQUESTS).count()
    print(f"[silver] requests accepted: {accepted}, rejected: {raw.count() - accepted}")


def build_silver_users(batch_id):
    """Donor / Requester are roles of the same user, derived from what the user actually did."""
    raw = current_snapshot(T_BRONZE_USERS, batch_id)
    donors = (
        spark.table(T_SILVER_LISTINGS)
        .select(F.col("donor_id").alias("user_id"))
        .distinct()
        .withColumn("is_donor", F.lit(True))
    )
    requesters = (
        spark.table(T_SILVER_REQUESTS)
        .select(F.col("requester_id").alias("user_id"))
        .distinct()
        .withColumn("is_requester", F.lit(True))
    )
    users = (
        raw.select(
            jstr("user_id").alias("user_id"),
            jstr("current_city").alias("current_city"),
            jcast("created_at", "timestamp").alias("created_at"),
            "data_origin",
            "ingested_at",
        )
        # name, email, phone stay in Bronze only (spec 6.4 / 9.1)
        .where(F.col("user_id").isNotNull())
        .join(donors, "user_id", "left")
        .join(requesters, "user_id", "left")
        .withColumn("is_donor", F.coalesce("is_donor", F.lit(False)))
        .withColumn("is_requester", F.coalesce("is_requester", F.lit(False)))
    )
    overwrite(users, T_SILVER_USERS)
    summary = (
        spark.table(T_SILVER_USERS)
        .agg(
            F.count("*").alias("users"),
            F.sum(F.col("is_donor").cast("int")).alias("donors"),
            F.sum(F.col("is_requester").cast("int")).alias("requesters"),
        )
        .first()
    )
    print(
        f"[silver] users: {summary['users']}, donors: {summary['donors']}, "
        f"requesters: {summary['requesters']}"
    )


# COMMAND ----------

# ----------------------------- 3. CANDIDATE PAIRS + ROUTES ------------------


def candidate_pairs():
    """Eligible request x listing pairs: same category, both active, available in time."""
    r = (
        spark.table(T_SILVER_REQUESTS)
        .where(F.lower("status").isin(REQUEST_MATCHABLE_STATUSES))
        .alias("r")
    )
    l = (
        spark.table(T_SILVER_LISTINGS)
        .where(F.lower("status").isin(LISTING_MATCHABLE_STATUSES))
        .alias("l")
    )
    return r.join(
        l,
        (F.col("r.category") == F.col("l.category"))
        & (F.col("r.requester_id") != F.col("l.donor_id"))
        & (
            F.col("l.available_from").isNull()
            | F.col("r.need_by_date").isNull()
            | (F.col("l.available_from") <= F.col("r.need_by_date"))
        ),
    )


def key_to_lonlat(key):
    lat, lon = key.split(",")
    return [float(lon), float(lat)]  # ORS wants [lon, lat]


def ingest_routes(batch_id):
    """Cache-first: only location pairs that have never been requested go to ORS."""
    spark.sql(f"CREATE TABLE IF NOT EXISTS {T_BRONZE_ROUTES} ({BRONZE_DDL}) USING DELTA")

    needed = candidate_pairs().select(
        F.col("l.location_key").alias("origin_key"), F.col("r.location_key").alias("dest_key")
    ).distinct()
    if spark.catalog.tableExists(T_SILVER_ROUTES):
        known = spark.table(T_SILVER_ROUTES).select("origin_key", "dest_key")
        needed = needed.join(known, ["origin_key", "dest_key"], "left_anti")

    missing = {(row["origin_key"], row["dest_key"]) for row in needed.collect()}
    if not missing:
        print("[bronze] routes: cache hit, ORS not called")
        return

    origins = sorted({o for o, _ in missing})
    dests = sorted({d for _, d in missing})
    api_key = get_secret(SECRET_SCOPE, SECRET_ORS_KEY)
    calls = failures = 0

    for o_chunk in chunks(origins, ORS_CHUNK):
        for d_chunk in chunks(dests, ORS_CHUNK):
            if not any((o, d) in missing for o in o_chunk for d in d_chunk):
                continue
            body = {
                "locations": [key_to_lonlat(k) for k in o_chunk + d_chunk],
                "sources": list(range(len(o_chunk))),
                "destinations": list(range(len(o_chunk), len(o_chunk) + len(d_chunk))),
                "metrics": ["distance", "duration"],
                "units": "km",
            }
            status, text = http_call(
                "POST",
                ORS_MATRIX_URL,
                json=body,
                headers={"Authorization": api_key, "Content-Type": "application/json"},
            )
            calls += 1
            failures += status != 200
            # The raw response is kept as-is inside response_text. Failed calls are stored
            # too: that row is the failure log.
            payload = json.dumps(
                {"origin_keys": o_chunk, "dest_keys": d_chunk, "response_text": text},
                sort_keys=True,
            )
            write_bronze(
                T_BRONZE_ROUTES,
                [
                    bronze_row(
                        sha(json.dumps(body, sort_keys=True)),
                        payload,
                        status,
                        ORS_MATRIX_URL,
                        "external_openrouteservice",
                        batch_id,
                    )
                ],
            )
            time.sleep(ORS_PAUSE_SECONDS)

    print(f"[bronze] routes: {len(missing)} new pairs, ORS calls: {calls}, failed: {failures}")


def build_silver_routes():
    ok = spark.table(T_BRONZE_ROUTES).where("http_status = 200")
    wrapped = ok.select(
        F.from_json(
            "payload", "origin_keys array<string>, dest_keys array<string>, response_text string"
        ).alias("w"),
        "ingested_at",
    )
    parsed = wrapped.select(
        "w.origin_keys",
        "w.dest_keys",
        F.from_json(
            "w.response_text", "distances array<array<double>>, durations array<array<double>>"
        ).alias("m"),
        "ingested_at",
    )
    by_origin = parsed.select(
        F.posexplode("origin_keys").alias("oi", "origin_key"), "dest_keys", "m", "ingested_at"
    )
    by_pair = by_origin.select(
        "oi", "origin_key", F.posexplode("dest_keys").alias("di", "dest_key"), "m", "ingested_at"
    )
    routes = by_pair.select(
        "origin_key",
        "dest_key",
        F.round(F.col("m.distances")[F.col("oi")][F.col("di")], 2).alias("distance_km"),
        F.round(F.col("m.durations")[F.col("oi")][F.col("di")] / 60, 1).alias("duration_min"),
        F.lit("openrouteservice").alias("route_source"),
        F.col("ingested_at").alias("fetched_at"),
    )
    w = Window.partitionBy("origin_key", "dest_key").orderBy(F.col("fetched_at").desc())
    latest = routes.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")
    overwrite(latest, T_SILVER_ROUTES)
    print(f"[silver] routes: {spark.table(T_SILVER_ROUTES).count()}")


# COMMAND ----------

# ----------------------------- 4. GOLD --------------------------------------


def build_gold_matches():
    """Grain: one row per (request_id, listing_id)."""
    rt = spark.table(T_SILVER_ROUTES).alias("rt")
    scored = (
        candidate_pairs()
        .join(
            rt,
            (F.col("rt.origin_key") == F.col("l.location_key"))
            & (F.col("rt.dest_key") == F.col("r.location_key")),
            "left",
        )
        .select(
            F.col("r.request_id").alias("request_id"),
            F.col("l.listing_id").alias("listing_id"),
            F.col("r.requester_id").alias("requester_id"),
            F.col("l.donor_id").alias("donor_id"),
            F.col("r.category").alias("category"),
            F.col("l.title").alias("listing_title"),
            F.col("rt.distance_km").alias("distance_km"),
            F.col("rt.duration_min").alias("duration_min"),
            F.when(
                F.col("l.available_until").isNull()
                | F.col("r.need_by_date").isNull()
                | (F.col("l.available_until") >= F.col("r.need_by_date")),
                F.lit(1.0),
            )
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
    users = spark.table(T_SILVER_USERS)

    total = gold.count()
    checks = {
        "silver listings has rows": listings.count() > 0,
        "silver requests has rows": requests_df.count() > 0,
        "silver listing_id unique": listings.select("listing_id").distinct().count()
        == listings.count(),
        "silver request_id unique": requests_df.select("request_id").distinct().count()
        == requests_df.count(),
        "listings.donor_id exists in users": listings.join(
            users, listings.donor_id == users.user_id, "left_anti"
        ).count()
        == 0,
        "requests.requester_id exists in users": requests_df.join(
            users, requests_df.requester_id == users.user_id, "left_anti"
        ).count()
        == 0,
        "gold grain unique (request_id, listing_id)": gold.select("request_id", "listing_id")
        .distinct()
        .count()
        == total,
        "gold keys not null": gold.where("request_id IS NULL OR listing_id IS NULL").count() == 0,
        "match_score within 0..1": gold.where("match_score < 0 OR match_score > 1").count() == 0,
    }
    missing_routes = gold.where("route_status = 'MISSING'").count()

    print("\n----- DATA QUALITY -----")
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}  {name}")
    print(f"INFO  gold rows: {total}, without a route: {missing_routes}")

    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError(f"Data quality failed: {failed}")


# COMMAND ----------

# ----------------------------- RUN ------------------------------------------


def main():
    batch_id = str(uuid.uuid4())
    print(f"batch_id = {batch_id} | supabase key mode = {SUPABASE_KEY_MODE}")

    api_key = supabase_key()
    ingest_supabase(SUPABASE_USERS, T_BRONZE_USERS, api_key, batch_id)
    ingest_supabase(SUPABASE_LISTINGS, T_BRONZE_LISTINGS, api_key, batch_id)
    ingest_supabase(SUPABASE_REQUESTS, T_BRONZE_REQUESTS, api_key, batch_id)

    build_silver_listings(batch_id)
    build_silver_requests(batch_id)
    build_silver_users(batch_id)

    ingest_routes(batch_id)
    build_silver_routes()

    build_gold_matches()
    run_quality_checks()


if __name__ == "__main__":
    main()
"""Stages 8A / 8B — listing files and trusted listing content (Silver).

silver_listing_files   one row per current listing_file_id (delete-aware), with the real file
                       state in the UC Volume: exists / size / sha256.
silver_listing_content one row per current listing_id: cleaned text + the vision result for the
                       listing's primary image + the text we will embed. Nothing is invented:
                       image fields are filled ONLY when vision_status = OK.

Vision results are selected on the driver in plain Python (latest_vision_results) instead of a
Spark UDF. The vision Bronze table has one row per image call, so this stays small, and it avoids
shipping repo modules to Spark workers.
"""

from typing import Iterable, List, Mapping

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from config.settings import (
    IMAGE_MIME_TYPES,
    TEXT_MAX_DESCRIPTION_CHARS,
    TEXT_MAX_TITLE_CHARS,
    VISION_MAX_DESCRIPTION_CHARS,
)
from rag.text import clean_text_col
from rag.vision import parse_vision_output

LISTING_FILE_COLUMNS = [
    "listing_file_id", "listing_id", "file_path", "file_type", "uploaded_at",
    "file_exists", "file_size_bytes", "file_sha256",
    "source_pg_lsn", "source_sort_by", "source_change_type", "silver_processed_at",
]

VISION_RESULT_SCHEMA = (
    "listing_file_id string, file_sha256 string, vision_call_id string, vision_ok boolean, "
    "image_description string, detected_labels array<string>, vision_error string"
)

CONTENT_COLUMNS = [
    "listing_id", "listing_file_id", "file_path", "title", "description_clean",
    "category", "condition", "listing_status",
    "image_description", "detected_labels", "searchable_text",
    "vision_endpoint", "prompt_version", "vision_status", "vision_error", "source_vision_call_id",
    "listing_updated_at", "content_processed_at",
]


def normalize_volume_path(col: Column) -> Column:
    """binaryFile reports 'dbfs:/Volumes/...'; Lakebase stores '/Volumes/...'."""
    return F.regexp_replace(col, r"^dbfs:", "")


def volume_file_facts(binary_df: DataFrame) -> DataFrame:
    """spark.read.format('binaryFile') output -> (file_path, file_size_bytes, file_sha256)."""
    return binary_df.select(
        normalize_volume_path(F.col("path")).alias("file_path"),
        F.col("length").cast("long").alias("file_size_bytes"),
        F.sha2(F.col("content"), 256).alias("file_sha256"),
    )


def build_silver_listing_files(current_rows: DataFrame, current_listing_ids: DataFrame,
                               volume_facts: DataFrame) -> DataFrame:
    """Current file rows (already delete-aware) for listings that still exist, plus Volume facts."""
    return (
        current_rows.alias("f")
        .join(current_listing_ids.select("listing_id").alias("l"), "listing_id", "inner")
        .join(volume_facts.alias("v"), F.col("f.file_path") == F.col("v.file_path"), "left")
        .select(
            F.col("f.listing_file_id"), F.col("listing_id"), F.col("f.file_path"),
            F.lower(F.trim(F.col("f.file_type"))).alias("file_type"),
            F.col("f.uploaded_at"),
            F.col("v.file_path").isNotNull().alias("file_exists"),
            F.col("v.file_size_bytes"), F.col("v.file_sha256"),
            F.col("f._pg_lsn").alias("source_pg_lsn"),
            F.col("f._sort_by").alias("source_sort_by"),
            F.col("f._pg_change_type").alias("source_change_type"),
            F.current_timestamp().alias("silver_processed_at"),
        )
        .select(*LISTING_FILE_COLUMNS)
    )


def is_image_path(path_col: Column) -> Column:
    ext = F.lower(F.regexp_extract(path_col, r"\.([A-Za-z0-9]+)$", 1))
    return ext.isin(list(IMAGE_MIME_TYPES))


def primary_image_files(silver_files: DataFrame) -> DataFrame:
    """One image per listing: an existing file first, then earliest upload, then smallest id."""
    order = Window.partitionBy("listing_id").orderBy(
        F.col("file_exists").desc(), F.col("uploaded_at").asc_nulls_last(), F.col("listing_file_id"))
    return (
        silver_files.filter(is_image_path(F.col("file_path")))
        .withColumn("_rn", F.row_number().over(order))
        .filter("_rn = 1")
        .drop("_rn")
    )


def latest_vision_results(rows: Iterable[Mapping], endpoint: str, prompt_version: str) -> List[tuple]:
    """Bronze vision rows -> one result per (listing_file_id, file_sha256) for this endpoint+prompt.

    A successful call always wins over a failed one; otherwise the newest call wins.
    Success is re-checked by parsing; a row whose output cannot be parsed counts as FAILED.
    """
    best = {}
    for r in rows:
        if r["vision_endpoint"] != endpoint or r["prompt_version"] != prompt_version:
            continue
        key = (r["listing_file_id"], r["file_sha256"])
        ok = r["http_status"] == 200 and r["error_message"] is None
        rank = (ok, r["called_at"])
        if key not in best or rank > best[key][0]:
            best[key] = (rank, r)

    results = []
    for (file_id, sha), ((ok, _), r) in sorted(best.items(), key=lambda kv: kv[0]):
        description, labels, parse_error = parse_vision_output(r["response_body"]) if ok else (None, [], None)
        if ok and parse_error:
            ok = False
        error = None if ok else (parse_error or r["error_message"] or "unknown vision failure")
        results.append((file_id, sha, r["call_id"], ok,
                        description if ok else None, labels if ok else [], error))
    return results


def build_listing_content(listings: DataFrame, primary_files: DataFrame, vision: DataFrame,
                          endpoint: str, prompt_version: str) -> DataFrame:
    l, p, v = listings.alias("l"), primary_files.alias("p"), vision.alias("v")
    joined = (
        l.join(p, F.col("l.listing_id") == F.col("p.listing_id"), "left")
        .join(v, (F.col("p.listing_file_id") == F.col("v.listing_file_id"))
              & (F.col("p.file_sha256") == F.col("v.file_sha256")), "left")
    )
    status = (
        F.when(F.col("p.listing_file_id").isNull(), "NO_IMAGE")
        .when(~F.col("p.file_exists"), "FILE_MISSING")
        .when(F.col("v.vision_call_id").isNull(), "PENDING")
        .when(F.col("v.vision_ok"), "OK")
        .otherwise("FAILED")
    )
    ok = F.col("vision_status") == "OK"
    readable = lambda c: F.lower(F.regexp_replace(c, "_", " "))  # noqa: E731

    return (
        joined.select(
            F.col("l.listing_id").alias("listing_id"),
            F.col("p.listing_file_id").alias("listing_file_id"),
            F.col("p.file_path").alias("file_path"),
            clean_text_col(F.col("l.title"), TEXT_MAX_TITLE_CHARS).alias("title"),
            clean_text_col(F.col("l.description"), TEXT_MAX_DESCRIPTION_CHARS).alias("description_clean"),
            F.col("l.category").alias("category"),
            F.col("l.condition").alias("condition"),
            F.col("l.status").alias("listing_status"),
            F.col("v.image_description").alias("_raw_description"),
            F.col("v.detected_labels").alias("_raw_labels"),
            F.col("v.vision_error").alias("_raw_error"),
            F.col("v.vision_call_id").alias("source_vision_call_id"),
            F.col("l.updated_at").alias("listing_updated_at"),
            status.alias("vision_status"),
        )
        .withColumn("image_description",
                    F.when(ok, clean_text_col(F.col("_raw_description"), VISION_MAX_DESCRIPTION_CHARS)))
        .withColumn("detected_labels",
                    F.when(ok, F.col("_raw_labels")).otherwise(F.array().cast("array<string>")))
        .withColumn("vision_error",
                    F.when(F.col("vision_status") == "FAILED", F.col("_raw_error"))
                    .when(F.col("vision_status") == "FILE_MISSING",
                          F.lit("file_path not found in the listing_images volume")))
        .withColumn("source_vision_call_id", F.when(F.col("vision_status").isin("OK", "FAILED"),
                                                    F.col("source_vision_call_id")))
        .withColumn("searchable_text", F.concat_ws(
            ". ",
            F.col("title"),
            F.concat(F.lit("Category: "), readable(F.col("category"))),
            F.concat(F.lit("Condition: "), readable(F.col("condition"))),
            F.col("description_clean"),
            F.col("image_description"),
            F.when(F.size("detected_labels") > 0,
                   F.concat(F.lit("Visible features: "), F.array_join("detected_labels", ", "))),
        ))
        .withColumn("vision_endpoint", F.lit(endpoint))
        .withColumn("prompt_version", F.lit(prompt_version))
        .withColumn("content_processed_at", F.current_timestamp())
        .select(*CONTENT_COLUMNS)
    )

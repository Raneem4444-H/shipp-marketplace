"""Listing files, content statuses (never invented), search docs — local Spark."""

import datetime as dt

from pyspark.sql import functions as F

from rag.content import (
    CONTENT_COLUMNS,
    VISION_RESULT_SCHEMA,
    build_listing_content,
    build_silver_listing_files,
    latest_vision_results,
    primary_image_files,
)
from rag.search_docs import SEARCH_DOC_COLUMNS, build_search_docs, merge_sql

T0 = dt.datetime(2026, 9, 30, 12, 0)
VOL = "/Volumes/bootcamp_students/shipp_bronze/listing_images"
OK_BODY = ('{"choices":[{"message":{"content":"{\\"image_description\\": \\"Oak dining table.\\", '
           '\\"detected_labels\\": [\\"table\\", \\"oak\\"]}"}}]}')


def vision_row(file_id, sha, ok, at, body=OK_BODY, endpoint="ep", prompt="v1"):
    return {"call_id": f"{file_id}-{at}", "called_at": T0 + dt.timedelta(minutes=at), "listing_file_id": file_id,
            "file_sha256": sha, "vision_endpoint": endpoint, "prompt_version": prompt,
            "http_status": 200 if ok else 503, "response_body": body if ok else "busy",
            "error_message": None if ok else "HTTP 503"}


def test_latest_vision_results_prefers_success_and_filters_prompt():
    rows = [vision_row("f1", "s1", True, 1), vision_row("f1", "s1", False, 5),       # later failure loses
            vision_row("f2", "s2", False, 1), vision_row("f2", "s2", False, 3),      # newest failure wins
            vision_row("f3", "s3", True, 1, prompt="v0")]                            # old prompt ignored
    res = {r[0]: r for r in latest_vision_results(rows, "ep", "v1")}
    assert set(res) == {"f1", "f2"}
    assert res["f1"][3] is True and res["f1"][4] == "Oak dining table." and res["f1"][5] == ["table", "oak"]
    assert res["f2"][3] is False and res["f2"][4] is None and res["f2"][6] == "HTTP 503"


def test_files_statuses_and_search_docs(spark):
    current = spark.createDataFrame([
        ("f1", "L1", f"{VOL}/L1/a.jpg", "image/jpeg", T0, "insert", 10, 1),
        ("f2", "L2", f"{VOL}/L2/a.jpg", "image/jpeg", T0, "insert", 10, 2),
        ("f3", "L3", f"{VOL}/L3/gone.jpg", "image/jpeg", T0, "insert", 10, 3),
        ("f4", "L4", f"{VOL}/L4/a.jpg", "image/jpeg", T0, "insert", 10, 4),
        ("f9", "L9", f"{VOL}/L9/a.jpg", "image/jpeg", T0, "insert", 10, 5),          # orphan
    ], "listing_file_id string, listing_id string, file_path string, file_type string, uploaded_at timestamp, "
       "_pg_change_type string, _pg_lsn long, _sort_by long")
    listing_ids = spark.createDataFrame([(x,) for x in ["L1", "L2", "L3", "L4", "L5"]], "listing_id string")
    volume = spark.createDataFrame([(f"{VOL}/{x}/a.jpg", 100, f"sha-{x}") for x in ["L1", "L2", "L4"]],
                                   "file_path string, file_size_bytes long, file_sha256 string")
    files = build_silver_listing_files(current, listing_ids, volume)
    assert {r.listing_file_id for r in files.collect()} == {"f1", "f2", "f3", "f4"}
    assert {r.listing_file_id: r.file_exists for r in files.collect()}["f3"] is False

    vision = spark.createDataFrame([
        ("f1", "sha-L1", "c1", True, "Oak dining table. Call +971 50 123 4567", ["table"], None),
        ("f2", "sha-L2", "c2", False, None, [], "HTTP 503"),
    ], VISION_RESULT_SCHEMA)
    listings = spark.createDataFrame([
        (x, f"Table {x}", "desc " + x + " mail a@b.com", "FURNITURE", "LIKE_NEW",
         "AVAILABLE" if x != "L5" else "DRAFT", T0) for x in ["L1", "L2", "L3", "L4", "L5"]
    ], "listing_id string, title string, description string, category string, condition string, "
       "status string, updated_at timestamp")
    out = build_listing_content(listings, primary_image_files(files), vision, "ep", "v1")
    assert out.columns == CONTENT_COLUMNS
    by = {r.listing_id: r for r in out.collect()}
    assert {k: v.vision_status for k, v in by.items()} == {
        "L1": "OK", "L2": "FAILED", "L3": "FILE_MISSING", "L4": "PENDING", "L5": "NO_IMAGE"}
    assert by["L1"].detected_labels == ["table"] and "[redacted]" in by["L1"].image_description
    assert by["L2"].image_description is None and by["L2"].detected_labels == [] and by["L2"].vision_error == "HTTP 503"
    assert "Visible features: table" in by["L1"].searchable_text and "a@b.com" not in by["L1"].searchable_text
    assert "Condition: like new" in by["L4"].searchable_text

    docs = build_search_docs(out)
    assert docs.columns == SEARCH_DOC_COLUMNS
    assert {r.listing_id for r in docs.collect()} == {"L1", "L2", "L3", "L4"}   # DRAFT excluded
    assert docs.filter(F.col("doc_hash").isNull()).count() == 0
    again = {r.listing_id: r.doc_hash for r in build_search_docs(out).collect()}
    assert again == {r.listing_id: r.doc_hash for r in docs.collect()}           # hash is deterministic
    assert "WHEN NOT MATCHED BY SOURCE THEN DELETE" in merge_sql("t", "s")

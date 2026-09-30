"""Stage 9A — gold_listing_search_docs: the only source of the AI Search index.

Grain: one row per AVAILABLE listing. Written with MERGE (never overwrite) so that:
- unchanged listings produce no change events (doc_hash equal -> no update),
- deleted / no-longer-available listings are removed (WHEN NOT MATCHED BY SOURCE THEN DELETE),
- the Delta Sync index only re-embeds what actually changed (Change Data Feed on).
"""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from config.settings import ELIGIBLE_LISTING_STATUSES

SEARCH_DOC_COLUMNS = [
    "listing_id", "title", "category", "condition", "status",
    "image_description", "detected_labels_text", "search_text", "vision_status",
    "doc_hash", "document_updated_at",
]
SEARCH_DOCS_DDL = (
    "listing_id STRING NOT NULL, title STRING, category STRING, condition STRING, status STRING, "
    "image_description STRING, detected_labels_text STRING, search_text STRING, vision_status STRING, "
    "doc_hash STRING, document_updated_at TIMESTAMP"
)
_HASHED = ["listing_id", "title", "category", "condition", "status",
           "image_description", "detected_labels_text", "search_text", "vision_status"]


def build_search_docs(content: DataFrame) -> DataFrame:
    docs = (
        content
        .filter(F.col("listing_status").isin(ELIGIBLE_LISTING_STATUSES))
        .filter(F.col("searchable_text").isNotNull() & (F.length("searchable_text") > 0))
        .select(
            "listing_id", "title", "category", "condition",
            F.col("listing_status").alias("status"),
            "image_description",
            F.array_join("detected_labels", ", ").alias("detected_labels_text"),
            F.col("searchable_text").alias("search_text"),
            "vision_status",
        )
    )
    return (
        docs
        .withColumn("doc_hash", F.sha2(F.concat_ws("\u0001", *[F.coalesce(F.col(c), F.lit("")) for c in _HASHED]), 256))
        .withColumn("document_updated_at", F.current_timestamp())
        .select(*SEARCH_DOC_COLUMNS)
    )


def create_table_sql(table: str) -> str:
    return (f"CREATE TABLE IF NOT EXISTS {table} ({SEARCH_DOCS_DDL}) USING DELTA "
            "TBLPROPERTIES (delta.enableChangeDataFeed = true)")


def enable_cdf_sql(table: str) -> str:
    return f"ALTER TABLE {table} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)"


def merge_sql(table: str, source_view: str) -> str:
    return f"""
MERGE INTO {table} AS t
USING {source_view} AS s
ON t.listing_id = s.listing_id
WHEN MATCHED AND t.doc_hash <> s.doc_hash THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
WHEN NOT MATCHED BY SOURCE THEN DELETE
""".strip()

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# from config.tables import BRONZE_REQUESTS_HISTORY, SILVER_REQUESTS
from config.tables import BRONZE_REQUESTS_HISTORY, SILVER_REQUESTS

print(BRONZE_REQUESTS_HISTORY)
print(SILVER_REQUESTS)

CURRENT_STATE_CHANGE_TYPES = ("insert", "update_postimage")


def build_silver_requests(bronze: DataFrame) -> DataFrame:
    """
    Reconstruct exactly one current row per request_id.

    Rank all CDC events first, then retain the latest event only when
    it represents a current row. This preserves correct delete behavior
    once the runtime delete change type is observed.
    """
    latest_window = Window.partitionBy("request_id").orderBy(
        F.col("_pg_lsn").desc(),
        F.col("_sort_by").desc(),
    )

    ranked = bronze.withColumn(
        "_current_rn",
        F.row_number().over(latest_window),
    )

    latest_current = (
        ranked
        .filter(F.col("_current_rn") == 1)
        .filter(F.col("_pg_change_type").isin(*CURRENT_STATE_CHANGE_TYPES))
    )

    cleaned = (
        latest_current
        .filter(F.col("request_id").isNotNull())
        .filter(F.col("requester_id").isNotNull())
        .filter(F.col("latitude").between(-90, 90))
        .filter(F.col("longitude").between(-180, 180))
        .select(
            "request_id",
            "requester_id",
            "request_text",
            "category",
            "status",
            "latitude",
            "longitude",
            "need_by_date",
            "updated_at",
            F.col("_pg_lsn").alias("source_pg_lsn"),
            F.col("_sort_by").alias("source_sort_by"),
            F.col("_pg_change_type").alias("source_change_type"),
            F.current_timestamp().alias("silver_processed_at"),
        )
    )

    return cleaned


def write_silver_requests(spark: SparkSession) -> DataFrame:
    bronze = spark.table(BRONZE_REQUESTS_HISTORY)
    silver = build_silver_requests(bronze)

    (
        silver.write
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(SILVER_REQUESTS)
    )

    return silver

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from config.tables import BRONZE_LISTINGS_HISTORY, SILVER_LISTINGS


CURRENT_STATE_CHANGE_TYPES = ("insert", "update_postimage")


def build_silver_listings(bronze: DataFrame) -> DataFrame:
    """
    Reconstruct exactly one current row per listing_id.

    Important:
    - Rank ALL observed CDC events first.
    - Only after rn=1, keep latest events that represent a current row.
    - This avoids resurrecting an older row if a newer delete event is later observed.
    - DELETE semantics remain runtime-driven; no delete operation name is invented here.
    """
    latest_window = Window.partitionBy("listing_id").orderBy(
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
        .filter(F.col("listing_id").isNotNull())
        .filter(F.col("donor_id").isNotNull())
        .filter(F.col("latitude").between(-90, 90))
        .filter(F.col("longitude").between(-180, 180))
        .select(
            "listing_id",
            "donor_id",
            "title",
            "description",
            "category",
            "condition",
            "latitude",
            "longitude",
            "available_from",
            "available_until",
            "status",
            "updated_at",
            F.col("_pg_lsn").alias("source_pg_lsn"),
            F.col("_sort_by").alias("source_sort_by"),
            F.col("_pg_change_type").alias("source_change_type"),
            F.current_timestamp().alias("silver_processed_at"),
        )
    )

    return cleaned


def write_silver_listings(spark: SparkSession) -> DataFrame:
    bronze = spark.table(BRONZE_LISTINGS_HISTORY)
    silver = build_silver_listings(bronze)

    (
        silver.write
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(SILVER_LISTINGS)
    )

    return silver

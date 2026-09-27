from pyspark.sql import functions as F
from pyspark.sql.window import Window

BRONZE_LISTINGS_TABLE = (
    "bootcamp_students.shipp_bronze.lb_listings_history"
)

SILVER_LISTINGS_TABLE = (
    "bootcamp_students.shipp_silver.silver_listings"
)

bronze_listings = spark.table(BRONZE_LISTINGS_TABLE)

print("Bronze Listings table loaded successfully.")
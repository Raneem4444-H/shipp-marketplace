from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def duplicate_key_count(df: DataFrame, key: str) -> int:
    return (
        df.groupBy(key)
        .count()
        .filter(F.col("count") > 1)
        .count()
    )


def null_key_count(df: DataFrame, key: str) -> int:
    return df.filter(F.col(key).isNull()).count()


def invalid_coordinate_count(df: DataFrame) -> int:
    return df.filter(
        F.col("latitude").isNull()
        | F.col("longitude").isNull()
        | ~F.col("latitude").between(-90, 90)
        | ~F.col("longitude").between(-180, 180)
    ).count()

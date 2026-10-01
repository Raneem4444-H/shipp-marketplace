"""Quality-gate helpers shared by every stage notebook."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def duplicate_key_count(df: DataFrame, *keys: str) -> int:
    return df.groupBy(*keys).count().filter(F.col("count") > 1).count()


def null_count(df: DataFrame, col_name: str) -> int:
    return df.filter(F.col(col_name).isNull()).count()


def out_of_range_coordinate_count(df: DataFrame, lat: str = "latitude", lon: str = "longitude") -> int:
    """Coordinates present but impossible. NULL coordinates are allowed (the row is just not routable)."""
    return df.filter(
        (F.col(lat).isNotNull() & ~F.col(lat).between(-90, 90))
        | (F.col(lon).isNotNull() & ~F.col(lon).between(-180, 180))
    ).count()


def run_quality_gate(violations: dict, row_count: int = None, allow_empty: bool = False) -> None:
    """Print every check and fail loudly if any is non-zero. Never loosen a check to pass."""
    if row_count is not None:
        print("Row count:", row_count)
    for name, count in violations.items():
        print(f"  {name:<40} {count}")
    failed = {name: count for name, count in violations.items() if count}
    if row_count is not None and not allow_empty:
        assert row_count > 0, "QUALITY FAILED: zero rows."
    assert not failed, f"QUALITY FAILED: {failed}"
    print("PASS — quality gate.")

"""Geo helpers as Spark column expressions."""

from pyspark.sql import Column
from pyspark.sql import functions as F

from config.settings import ROUTE_KEY_DECIMALS

EARTH_RADIUS_KM = 6371.0


def coord_key(lat_col: str, lon_col: str) -> Column:
    """Route cache key 'lat,lon' rounded to ROUTE_KEY_DECIMALS (~11 m at 4 decimals)."""
    fmt = f"%.{ROUTE_KEY_DECIMALS}f"
    return F.concat_ws(",", F.format_string(fmt, F.col(lat_col)), F.format_string(fmt, F.col(lon_col)))


def haversine_km(lat1: Column, lon1: Column, lat2: Column, lon2: Column) -> Column:
    """Straight-line distance in km. Pre-filter only — never shown to users as a route distance."""
    dlat = F.radians(lat2 - lat1)
    dlon = F.radians(lon2 - lon1)
    a = (F.pow(F.sin(dlat / 2), 2)
         + F.cos(F.radians(lat1)) * F.cos(F.radians(lat2)) * F.pow(F.sin(dlon / 2), 2))
    return 2 * EARTH_RADIUS_KM * F.asin(F.sqrt(a))


def now_ntz() -> Column:
    """Current time as TIMESTAMP_NTZ, comparable with Lakebase-synced timestamp_ntz columns."""
    return F.current_timestamp().cast("timestamp_ntz")

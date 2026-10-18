
"""Reverse geocoding for SHIPP map-selected pickup locations."""

import logging

import requests
import streamlit as st

logger = logging.getLogger(__name__)

ORS_REVERSE_URL = (
    "https://api.openrouteservice.org/geocode/reverse"
)


def approximate_area_label(latitude: float, longitude: float) -> str:
    """Coarse, pin-derived area label used when name lookup is unavailable.

    Two decimals is roughly 1 km, so the label never exposes an exact address.
    It keeps the confirmed map pin as the only source of location, which means
    a missing ORS key or an ORS outage no longer blocks publishing a listing or
    creating a request.
    """

    if not (-90 <= latitude <= 90):
        raise ValueError("Invalid latitude.")
    if not (-180 <= longitude <= 180):
        raise ValueError("Invalid longitude.")

    lat_hemisphere = "N" if latitude >= 0 else "S"
    lon_hemisphere = "E" if longitude >= 0 else "W"
    return (
        f"Near {abs(latitude):.2f}°{lat_hemisphere}, "
        f"{abs(longitude):.2f}°{lon_hemisphere}"
    )


@st.cache_data(ttl=3600, show_spinner=False)
def reverse_geocode_pickup_area(
    latitude: float,
    longitude: float,
    api_key: str,
) -> str | None:
    """Resolve coordinates to a human-readable pickup area.

    Returns None when the API fails or no suitable location exists.
    """

    if not (-90 <= latitude <= 90):
        raise ValueError("Invalid latitude.")

    if not (-180 <= longitude <= 180):
        raise ValueError("Invalid longitude.")

    if not api_key:
        logger.error("ORS geocoding credential is missing.")
        return None

    try:
        response = requests.get(
            ORS_REVERSE_URL,
            params={
                "api_key": api_key,
                "point.lat": latitude,
                "point.lon": longitude,
                "size": 1,
            },
            timeout=8,
        )

        response.raise_for_status()

        features = response.json().get("features", [])

        if not features:
            return None

        properties = features[0].get("properties", {})

        # Prefer a neighborhood/area rather than a private address.
        area = (
            properties.get("neighbourhood")
            or properties.get("locality")
            or properties.get("borough")
            or properties.get("county")
        )

        city = (
            properties.get("locality")
            or properties.get("localadmin")
            or properties.get("region")
        )

        parts = []
        for value in (area, city):
            if value and value not in parts:
                parts.append(value)

        if not parts:
            return None

        return ", ".join(parts)

    except (requests.RequestException, ValueError) as exc:
        logger.warning(
            "Pickup location reverse geocoding failed: %s",
            type(exc).__name__,
        )
        return None

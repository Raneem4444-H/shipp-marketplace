
"""Reverse geocoding for SHIPP map-selected pickup locations."""

import logging

import requests
import streamlit as st

logger = logging.getLogger(__name__)

ORS_REVERSE_URL = (
    "https://api.openrouteservice.org/geocode/reverse"
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

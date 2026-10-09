"""Listing gallery adapter; uses the existing tested renderer and photo cache."""
from __future__ import annotations


def render_listings(listings, *, empty_message: str, key_prefix: str) -> None:
    from ui.legacy_core import render_listing_gallery

    render_listing_gallery(
        listings, empty_message=empty_message, key_prefix=key_prefix,
    )

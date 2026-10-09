"""Authorized donor dashboard: reads only the signed-in donor's available listings."""
from __future__ import annotations

import streamlit as st

from services.dashboard_service import DashboardService
from services.identity_service import require_role
from ui.components.product_card import render_listings
from ui.legacy_core import marketplace

st.title("Donor dashboard")
profile = require_role("DONOR")
if profile is not None:
    dashboard = DashboardService(marketplace)
    try:
        listings = dashboard.donor_listings(profile)
    except Exception:
        st.error("Your listings could not be loaded. Please try later.")
    else:
        st.metric("Your available listings", len(listings))
        render_listings(listings, empty_message="No available listings yet.", key_prefix="donor_dashboard")
        st.caption("This view shows available listings only, not historical/expired totals.")

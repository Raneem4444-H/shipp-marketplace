"""Authorized requester dashboard: requests + saved items scoped to ownership."""
from __future__ import annotations

import streamlit as st

from services.dashboard_service import DashboardService
from services.identity_service import require_role
from ui.legacy_core import marketplace

st.title("My requests")
profile = require_role("REQUESTER")
if profile is not None:
    dashboard = DashboardService(marketplace)
    try:
        requests = dashboard.requester_requests(profile)
    except Exception:
        st.error("Your requests could not be loaded. Please try later.")
    else:
        st.metric("Recent requests", len(requests))
        if not requests:
            st.info("You have not created any requests yet.")
        else:
            options = {f"{row['category']} — {str(row['request_text'])[:70]}": row for row in requests}
            selected = options[st.selectbox("Your request", list(options))]
            st.write(selected)
            try:
                saved = dashboard.requester_saves(profile, str(selected["request_id"]))
            except Exception:
                st.error("Saved items could not be loaded.")
            else:
                st.metric("Saved items for this request", len(saved))
                if saved:
                    st.dataframe(saved, width="stretch", hide_index=True)

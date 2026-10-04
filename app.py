# ============================================================
# SHIPP — Databricks App
# P0 Marketplace + Agent Integration
# ============================================================

from __future__ import annotations

import html
from datetime import date, timedelta
from pathlib import Path
import sys

import streamlit as st


# ------------------------------------------------------------
# Paths / existing SHIPP Agent package
# ------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent
AGENT_SRC = ROOT_DIR / "agent" / "agent_ship" / "src"
CSS_PATH = ROOT_DIR / "assets" / "shipp.css"

if str(AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_SRC))

from app_marketplace import MarketplaceRepo
from shipp.agent.agent import ShippAgent
from shipp.agent.clients import build_lakebase_connect, build_workspace_client
from shipp.agent.config import AgentSettings


# ------------------------------------------------------------
# Page + visual system
# ------------------------------------------------------------

st.set_page_config(
    page_title="SHIPP",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def load_css() -> None:
    if CSS_PATH.exists():
        css = CSS_PATH.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


load_css()

st.markdown(
    """
    <div class="shipp-header">
      <div class="shipp-brand">
        <span class="shipp-logo">◇</span>
        <span class="shipp-brand-name">SHIPP</span>
      </div>
      <div class="shipp-header-status">
        <span class="shipp-status-dot"></span>
        Lakebase → Spark → Gold → AI Search → Agent
      </div>
    </div>

    <section class="shipp-hero">
      <div class="shipp-eyebrow">AI-assisted household marketplace</div>
      <h1 class="shipp-hero-title">Give useful household items a second life.</h1>
      <p class="shipp-hero-copy">
        Donors publish items they no longer need. Requesters describe what they need.
        SHIPP uses trusted pipeline outputs, route-aware matching, AI Search, and a
        controlled Agent action to help connect them.
      </p>
    </section>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------
# Existing validated platform clients
# ------------------------------------------------------------

@st.cache_resource
def load_agent() -> ShippAgent:
    return ShippAgent.from_env()


@st.cache_resource
def load_marketplace() -> MarketplaceRepo:
    settings = AgentSettings.from_env()
    workspace = build_workspace_client()
    connect = build_lakebase_connect(settings, workspace)
    return MarketplaceRepo(connect, settings.lakebase_schema)


try:
    agent = load_agent()
    marketplace = load_marketplace()
except Exception as exc:
    st.error("SHIPP could not connect to its Databricks resources.")
    st.code(str(exc))
    st.stop()


# ------------------------------------------------------------
# Session state
# ------------------------------------------------------------

defaults = {
    "messages": [],
    "pending_save": None,
    "tool_trace": [],
    "active_request_id": None,
    "active_requester_id": None,
    "last_created_listing_id": None,
    "last_created_request_id": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ------------------------------------------------------------
# Persona selection — not authentication
# ------------------------------------------------------------

st.markdown("## What would you like to do today?")

persona = st.radio(
    "Choose your SHIPP journey",
    ["Give an item", "Find an item"],
    horizontal=True,
    label_visibility="collapsed",
)

st.caption(
    "For the capstone demo, SHIPP uses existing Lakebase users. "
    "Full authentication is intentionally outside the P0 scope."
)


# ============================================================
# DONOR JOURNEY
# ============================================================

if persona == "Give an item":
    st.markdown("### Donor — publish an available household item")
    st.write(
        "Create the operational listing in Lakebase. The existing incremental "
        "pipeline then carries that change through Bronze, Silver, route/search "
        "enrichment, and Gold."
    )

    try:
        donors = marketplace.list_users("DONOR")
    except Exception as exc:
        st.error("Could not load Donor users from Lakebase.")
        st.code(str(exc))
        st.stop()

    if not donors:
        st.warning("No active DONOR users are available in Lakebase.")
        st.stop()

    donor_by_label = {
        f"{row['name']} · {row['user_id']}": row["user_id"]
        for row in donors
    }
    donor_label = st.selectbox("Who is donating?", list(donor_by_label))
    donor_id = donor_by_label[donor_label]

    with st.form("create_listing_form", clear_on_submit=False):
        left, right = st.columns(2)

        with left:
            title = st.text_input("Item title", placeholder="Wooden dining table")
            category = st.selectbox(
                "Category",
                ["FURNITURE", "KITCHEN", "ELECTRONICS", "BOOKS", "CLOTHING", "OTHER"],
            )
            condition = st.selectbox(
                "Condition",
                ["LIKE_NEW", "GOOD", "FAIR", "USED"],
            )
            available_until = st.date_input(
                "Available until",
                value=date.today() + timedelta(days=14),
                min_value=date.today(),
            )

        with right:
            location = st.text_input(
                "Pickup location",
                placeholder="Al Reem Island, Abu Dhabi",
            )
            latitude = st.number_input(
                "Latitude",
                min_value=-90.0,
                max_value=90.0,
                value=24.4976,
                format="%.6f",
            )
            longitude = st.number_input(
                "Longitude",
                min_value=-180.0,
                max_value=180.0,
                value=54.4075,
                format="%.6f",
            )

        description = st.text_area(
            "Description",
            placeholder="Describe the item, size, material, condition, and anything useful to the requester.",
        )

        submitted_listing = st.form_submit_button(
            "Publish item",
            type="primary",
            use_container_width=True,
        )

    if submitted_listing:
        if not title.strip() or not location.strip():
            st.warning("Item title and pickup location are required.")
        else:
            try:
                listing_id = marketplace.create_listing(
                    donor_id=donor_id,
                    title=title,
                    description=description,
                    category=category,
                    condition=condition,
                    location=location,
                    latitude=float(latitude),
                    longitude=float(longitude),
                    available_until=available_until,
                )
                st.session_state.last_created_listing_id = listing_id
                st.success(f"Listing published to Lakebase: {listing_id}")
                st.info(
                    "Next data step: Lakebase change → CDC/Bronze → Silver → "
                    "enrichment/search → Gold candidate matches."
                )
            except Exception as exc:
                st.error("The listing could not be created.")
                st.code(str(exc))

    if st.session_state.last_created_listing_id:
        st.markdown("#### Latest published listing")
        st.code(st.session_state.last_created_listing_id)


# ============================================================
# REQUESTER JOURNEY
# ============================================================

else:
    st.markdown("### Requester — tell SHIPP what you need")
    st.write(
        "Create a new request or select an existing one. Once the request is "
        "available in Gold candidate matches, the Agent can retrieve, explain, "
        "and propose a save."
    )

    try:
        requesters = marketplace.list_users("REQUESTER")
    except Exception as exc:
        st.error("Could not load Requester users from Lakebase.")
        st.code(str(exc))
        st.stop()

    if not requesters:
        st.warning("No active REQUESTER users are available in Lakebase.")
        st.stop()

    requester_by_label = {
        f"{row['name']} · {row['user_id']}": row["user_id"]
        for row in requesters
    }
    requester_label = st.selectbox(
        "Who is requesting?",
        list(requester_by_label),
        key="requester_select",
    )
    requester_id = requester_by_label[requester_label]

    request_mode = st.radio(
        "Request",
        ["Use an existing request", "Create a new request"],
        horizontal=True,
    )

    selected_request_id = None

    if request_mode == "Create a new request":
        with st.form("create_request_form", clear_on_submit=False):
            left, right = st.columns(2)

            with left:
                category = st.selectbox(
                    "What category do you need?",
                    ["FURNITURE", "KITCHEN", "ELECTRONICS", "BOOKS", "CLOTHING", "OTHER"],
                    key="request_category",
                )
                need_by_date = st.date_input(
                    "Need it by",
                    value=date.today() + timedelta(days=7),
                    min_value=date.today(),
                )
                location = st.text_input(
                    "Your location",
                    placeholder="Al Maryah Island, Abu Dhabi",
                )

            with right:
                latitude = st.number_input(
                    "Latitude",
                    min_value=-90.0,
                    max_value=90.0,
                    value=24.5014,
                    format="%.6f",
                    key="request_latitude",
                )
                longitude = st.number_input(
                    "Longitude",
                    min_value=-180.0,
                    max_value=180.0,
                    value=54.3872,
                    format="%.6f",
                    key="request_longitude",
                )

            request_text = st.text_area(
                "Describe what you need",
                placeholder="I need a compact dining table for a small apartment.",
            )

            submitted_request = st.form_submit_button(
                "Create request",
                type="primary",
                use_container_width=True,
            )

        if submitted_request:
            if not request_text.strip() or not location.strip():
                st.warning("Request description and location are required.")
            else:
                try:
                    new_request_id = marketplace.create_request(
                        requester_id=requester_id,
                        request_text=request_text,
                        category=category,
                        location=location,
                        latitude=float(latitude),
                        longitude=float(longitude),
                        need_by_date=need_by_date,
                    )
                    st.session_state.last_created_request_id = new_request_id
                    st.session_state.active_request_id = new_request_id
                    st.session_state.active_requester_id = requester_id
                    st.session_state.messages = []
                    st.session_state.pending_save = None
                    st.session_state.tool_trace = []
                    st.success(f"Request created in Lakebase: {new_request_id}")
                    st.info(
                        "The request is operational now. Matching becomes available "
                        "after the existing incremental pipeline refreshes Silver/Gold."
                    )
                except Exception as exc:
                    st.error("The request could not be created.")
                    st.code(str(exc))

        selected_request_id = st.session_state.last_created_request_id

    else:
        try:
            requests = marketplace.list_requests(requester_id)
        except Exception as exc:
            st.error("Could not load requests from Lakebase.")
            st.code(str(exc))
            st.stop()

        if not requests:
            st.info("This requester has no requests yet. Create one to continue.")
        else:
            request_by_label = {
                (
                    f"{row['category'] or 'UNCATEGORIZED'} · "
                    f"{row['request_text'][:70]} · {row['status']}"
                ): row["request_id"]
                for row in requests
            }
            selected_label = st.selectbox(
                "Choose your request",
                list(request_by_label),
            )
            selected_request_id = request_by_label[selected_label]

    if selected_request_id:
        if (
            st.session_state.active_request_id != selected_request_id
            or st.session_state.active_requester_id != requester_id
        ):
            st.session_state.active_request_id = selected_request_id
            st.session_state.active_requester_id = requester_id
            st.session_state.messages = []
            st.session_state.pending_save = None
            st.session_state.tool_trace = []

        request_id = selected_request_id
        user_id = requester_id

        st.markdown("---")
        st.markdown("### SHIPP matching + Agent")
        st.caption(
            f"Active request: {request_id} · Requester: {user_id}"
        )

        st.markdown(
            """
            **What happens behind this screen**

            Lakebase request → CDC/Bronze → Silver → ORS route enrichment →
            Gold candidate matches → AI Search context → SHIPP Agent →
            user-approved save → Lakebase
            """
        )

        col_find, col_saved = st.columns([1, 1])

        with col_find:
            if st.button(
                "Find my best available match",
                type="primary",
                use_container_width=True,
            ):
                try:
                    with st.spinner("Checking Gold matches, AI Search, and current Lakebase state..."):
                        turn = agent.chat(
                            user_id=user_id,
                            request_id=request_id,
                            user_message=(
                                "Recommend the best available item for this request. "
                                "Use the trusted candidate matches, relevant listing context, "
                                "and current listing state. Explain why it is the best match "
                                "and propose saving it if appropriate."
                            ),
                            history=st.session_state.messages,
                        )

                    reply = turn.reply or "No recommendation was returned."
                    st.session_state.messages.append(
                        {"role": "assistant", "content": reply}
                    )
                    st.session_state.pending_save = turn.pending_save
                    st.session_state.tool_trace = turn.tool_trace
                except Exception as exc:
                    st.error("Agent request failed.")
                    st.code(str(exc))

        with col_saved:
            if st.button("Refresh saved state", use_container_width=True):
                st.rerun()

        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        prompt = st.chat_input(
            "Ask SHIPP about these matches, condition, distance, or availability"
        )

        if prompt:
            st.session_state.messages.append(
                {"role": "user", "content": prompt}
            )
            with st.chat_message("user"):
                st.markdown(prompt)

            try:
                with st.spinner("SHIPP is checking trusted evidence..."):
                    turn = agent.chat(
                        user_id=user_id,
                        request_id=request_id,
                        user_message=prompt,
                        history=st.session_state.messages[:-1],
                    )

                reply = turn.reply or "No recommendation was returned."
                st.session_state.messages.append(
                    {"role": "assistant", "content": reply}
                )
                st.session_state.pending_save = turn.pending_save
                st.session_state.tool_trace = turn.tool_trace

                with st.chat_message("assistant"):
                    st.markdown(reply)
            except Exception as exc:
                st.error("Agent request failed.")
                st.code(str(exc))

        if st.session_state.tool_trace:
            with st.expander("Agent evidence trace — Gold → AI Search → Lakebase"):
                for number, trace in enumerate(
                    st.session_state.tool_trace,
                    start=1,
                ):
                    st.markdown(f"**{number}. {trace.get('tool', 'unknown')}**")
                    st.json(trace)

        pending = st.session_state.pending_save

        if pending is not None:
            st.markdown("### Confirm save")

            pending_title = html.escape(str(pending.title))
            pending_listing_id = html.escape(str(pending.listing_id))
            pending_reason = html.escape(str(pending.reason))

            st.markdown(
                f"""
                <div class="shipp-recommendation">
                  <span class="shipp-recommendation-label">Recommended match</span>
                  <div class="shipp-recommendation-title">{pending_title}</div>
                  <div class="shipp-recommendation-id">{pending_listing_id}</div>
                  <div class="shipp-reason">
                    <strong>Why it matches:</strong> {pending_reason}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button(
                "♡ Save this item",
                type="primary",
                use_container_width=True,
            ):
                try:
                    with st.spinner("Rechecking current Lakebase state before write..."):
                        result = agent.confirm_save(
                            user_id=user_id,
                            request_id=request_id,
                            listing_id=pending.listing_id,
                        )

                    if result.ok:
                        st.success(
                            f"Saved successfully. Saved Item ID: {result.saved_item_id}"
                        )
                        st.session_state.pending_save = None
                    else:
                        st.warning(f"Save rejected: {result.message}")
                except Exception as exc:
                    st.error("Save failed.")
                    st.code(str(exc))

        st.markdown("### Saved items for this request")
        try:
            saved_items = marketplace.list_saved_items(user_id, request_id)
            if saved_items:
                st.dataframe(saved_items, use_container_width=True, hide_index=True)
            else:
                st.caption("Nothing has been saved for this request yet.")
        except Exception as exc:
            st.warning("Saved-state refresh is temporarily unavailable.")
            st.code(str(exc))


st.markdown(
    """
    <div class="shipp-footer">
      Donor / Requester → Lakebase → CDC → Bronze → Silver → ORS →
      Gold → AI Search → SHIPP Agent → Approved Save → Lakebase → Analytics
    </div>
    """,
    unsafe_allow_html=True,
)

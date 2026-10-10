# ============================================================
# SHIPP — Databricks App
# Hybrid Marketplace + AI Advisor
# ============================================================

from __future__ import annotations

import html
import os
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
import sys

import folium
import streamlit as st
from streamlit_folium import st_folium


# ------------------------------------------------------------
# Paths / existing SHIPP Agent package
# ------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parents[1]
AGENT_SRC = ROOT_DIR / "agent" / "agent_ship" / "src"
CSS_PATH = ROOT_DIR / "assets" / "shipp.css"

if str(AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_SRC))

from app_marketplace import MarketplaceRepo
from app_runtime import (
    bootstrap_streamlit_secrets,
    deployment_target,
    runtime_config_status,
)
from shipp.agent.agent import ShippAgent
from shipp.agent.clients import build_lakebase_connect, build_workspace_client


# ------------------------------------------------------------
# Page / theme
# ------------------------------------------------------------


# Streamlit Community Cloud stores configuration in st.secrets rather than
# Databricks App resource bindings. Root-level secrets are already exposed by
# Streamlit; this additionally supports clean [databricks]/[lakebase]/[shipp]
# sections without printing any secret values.
try:
    bootstrap_streamlit_secrets(st.secrets)
except Exception:
    # No secrets file is a valid state for Databricks Apps because resources
    # are injected by the platform. Startup checks below surface real gaps.
    pass

RUNTIME_STATUS = runtime_config_status()
DEPLOYMENT_TARGET = deployment_target()


def load_css() -> None:
    if CSS_PATH.exists():
        st.markdown(
            f"<style>{CSS_PATH.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )


load_css()


# ------------------------------------------------------------
# Constants / demo-friendly labels
# ------------------------------------------------------------

CATEGORIES = [
    "FURNITURE",
    "KITCHEN",
    "ELECTRONICS",
    "BOOKS",
    "CLOTHING",
    "OTHER",
]

CONDITIONS = ["LIKE_NEW", "GOOD", "FAIR", "USED"]

# Friendly display names only. Operational IDs and ownership remain unchanged.
DEMO_ALIASES = {
    "demo-donor-001": "Jake Wilson",
    "demo-requester-001": "Kim Stevens",
}


def display_user(row: dict[str, str]) -> str:
    return DEMO_ALIASES.get(row["user_id"], row["name"])


def is_agent_fallback(reply: str) -> bool:
    return reply.strip().lower().startswith(
        "i couldn't finish checking the matches"
    )


# ------------------------------------------------------------
# Existing validated platform clients
# ------------------------------------------------------------

@st.cache_resource
def load_agent() -> ShippAgent:
    return ShippAgent.from_env()


@st.cache_resource
def load_marketplace() -> MarketplaceRepo:
    # Marketplace startup only needs Databricks auth + Lakebase settings.
    # Do not require Agent-only config (LLM, SQL warehouse, AI Search)
    # just to render the frontend or use operational donor/requester flows.
    settings = SimpleNamespace(
        lakebase_schema=os.getenv("SHIPP_LAKEBASE_SCHEMA", "shipp"),
        lakebase_endpoint=(
            os.getenv("SHIPP_LAKEBASE_ENDPOINT")
            or os.getenv("ENDPOINT_NAME")
        ),
        lakebase_instance=os.getenv("SHIPP_LAKEBASE_INSTANCE"),
    )
    workspace = build_workspace_client()
    connect = build_lakebase_connect(settings, workspace)

    return MarketplaceRepo(
        connect,
        settings.lakebase_schema,
        workspace=workspace,
        image_volume_path=os.getenv(
            "SHIPP_LISTING_IMAGE_VOLUME",
            "/Volumes/bootcamp_students/shipp_bronze/listing_images",
        ),
    )


def render_startup_blocker(exc: Exception) -> None:
    """Render an actionable deployment blocker instead of a blank/error page."""

    target = (
        "Databricks App"
        if DEPLOYMENT_TARGET == "databricks_app"
        else "Streamlit Community Cloud"
    )

    st.markdown(
        """
        <div class="shipp-header">
          <div class="shipp-brand">
            <span class="shipp-logo">◇</span>
            <div>
              <div class="shipp-brand-name">SHIPP</div>
              <div class="shipp-tagline">Household items, matched intelligently.</div>
            </div>
          </div>
          <div class="shipp-status shipp-status-offline">
            <span class="shipp-status-dot shipp-status-dot-offline"></span>
            Setup required
          </div>
        </div>

        <section class="shipp-hero">
          <div class="shipp-eyebrow">Deployment setup</div>
          <h1>SHIPP is deployed, but its data connection is not ready.</h1>
          <p>
            The frontend loaded successfully. The remaining blocker is the
            runtime connection to Databricks/Lakebase for this deployment.
          </p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.error(
        "The application cannot open the SHIPP marketplace database yet. "
        "No business data was changed."
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Runtime", target)
    c2.metric(
        "Marketplace config",
        "PASS" if RUNTIME_STATUS["marketplace_ready"] else "CHECK",
    )
    c3.metric(
        "AI Agent config",
        "PASS" if RUNTIME_STATUS["agent_ready"] else "CHECK",
    )

    missing = list(RUNTIME_STATUS["marketplace_missing"])
    if missing:
        st.markdown("### Missing deployment configuration")
        st.code("\n".join(missing))
        st.caption(
            "Add these names in Streamlit Community Cloud → App settings → Secrets. "
            "Do not put secret values in GitHub."
        )

    error_text = str(exc)
    with st.expander("Connection diagnostic", expanded=True):
        if "No PGHOST and no SHIPP_LAKEBASE_INSTANCE" in error_text:
            st.warning(
                "Lakebase host/instance is not configured for this external app."
            )
        elif "default auth" in error_text.lower() or "credential" in error_text.lower():
            st.warning(
                "Databricks authentication is incomplete or the configured "
                "service principal cannot mint a Lakebase credential."
            )
        elif "timeout" in error_text.lower() or "could not translate host" in error_text.lower():
            st.warning(
                "The configuration is present, but the Streamlit Cloud runtime "
                "cannot currently reach the configured Lakebase host."
            )
        else:
            st.warning(
                "Configuration exists, but the marketplace connection still failed."
            )

        st.code(error_text[:1200])

    st.markdown("### Required Streamlit secret groups")
    st.markdown(
        """
        **Databricks authentication**
        - `DATABRICKS_HOST`
        - `DATABRICKS_CLIENT_ID`
        - `DATABRICKS_CLIENT_SECRET`

        **Lakebase**
        - `PGHOST`
        - `PGPORT`
        - `PGDATABASE`
        - `PGUSER`
        - `SHIPP_LAKEBASE_ENDPOINT`
        - `SHIPP_LAKEBASE_SCHEMA`

        **AI / retrieval**
        - `SHIPP_LLM_ENDPOINT`
        - `SHIPP_SQL_WAREHOUSE_ID`
        - `SHIPP_CANDIDATE_MATCHES_TABLE`
        - `SHIPP_SEARCH_INDEX`
        - `SHIPP_LISTING_IMAGE_VOLUME`
        """
    )

    st.info(
        "After saving Streamlit Secrets, reboot the app. "
        "The normal donor/requester marketplace will load automatically "
        "when Lakebase connectivity passes."
    )


try:
    marketplace = load_marketplace()
except Exception as exc:
    render_startup_blocker(exc)
    st.stop()

# External hosts such as Streamlit Community Cloud do not receive Databricks
# App resource bindings automatically. Missing Agent-only environment
# variables must not prevent the marketplace frontend from starting.
agent = None
agent_startup_error = None
try:
    agent = load_agent()
except Exception as exc:
    agent_startup_error = str(exc)
    st.warning(
        "Marketplace is online, but SHIPP AI Advisor is not configured for "
        "this deployment yet. Donor/requester marketplace flows remain available."
    )


@st.cache_data(ttl=120, show_spinner=False)
def load_listing_image(_marketplace: MarketplaceRepo, listing_id: str) -> bytes | None:
    return _marketplace.get_primary_listing_image(listing_id)


@st.cache_data(ttl=120, show_spinner=False)
def load_listing_images(_marketplace: MarketplaceRepo, listing_id: str) -> list[dict]:
    return _marketplace.get_listing_images(listing_id)


def _select_listing_photo(state_key: str, index: int) -> None:
    st.session_state[state_key] = index


@st.dialog("Item details & photos")
def show_listing_photo(
    listing_id: str,
    title: str,
    *,
    description: str = "",
    location: str = "",
    category: str = "",
    condition: str = "",
) -> None:
    st.subheader(title)
    if location:
        st.caption(f"{category} · {condition} · {location}")

    with st.spinner("Loading item photos..."):
        photos = load_listing_images(marketplace, listing_id)

    if not photos:
        st.info("No photos are attached to this listing yet.")
    else:
        photo_key = f"shipp_photo_index_{listing_id}"
        current = max(0, min(int(st.session_state.get(photo_key, 0)), len(photos) - 1))
        st.session_state[photo_key] = current
        image_bytes = photos[current]["content"]

        st.caption(f"Photo {current + 1} of {len(photos)}")
        if image_bytes:
            st.image(image_bytes, use_container_width=True)
        else:
            st.warning("This photo is currently unavailable from image storage.")

        previous, following = st.columns(2)
        with previous:
            st.button(
                "← Previous photo", key=f"photo_prev_{listing_id}",
                disabled=current == 0, on_click=_select_listing_photo,
                args=(photo_key, current - 1), use_container_width=True,
            )
        with following:
            st.button(
                "Next photo →", key=f"photo_next_{listing_id}",
                disabled=current == len(photos) - 1,
                on_click=_select_listing_photo,
                args=(photo_key, current + 1), use_container_width=True,
            )

        if len(photos) > 1:
            thumbnails = st.columns(len(photos), gap="small")
            for index, photo in enumerate(photos):
                with thumbnails[index]:
                    if photo["content"]:
                        st.image(photo["content"], use_container_width=True)
                    else:
                        st.caption("Unavailable")
                    st.button(
                        f"{index + 1}", key=f"photo_thumb_{listing_id}_{index}",
                        type="primary" if index == current else "secondary",
                        on_click=_select_listing_photo,
                        args=(photo_key, index), use_container_width=True,
                        help=f"Select photo {index + 1}",
                    )

    if description:
        st.markdown("**About this item**")
        st.write(description)
    with st.expander("Technical reference", expanded=False):
        st.code(f"listing_id = {listing_id}")

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
    "last_saved_item_id": None,
    "last_saved_listing_id": None,
    "last_save_status": None,
    "last_saved_refresh_pass": None,
    "last_agent_read_tools": [],
    "review_error": None,
    "donor_lat": 24.4976,
    "donor_lon": 54.4075,
    "requester_lat": 24.5014,
    "requester_lon": 54.3872,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ------------------------------------------------------------
# Reusable UI helpers
# ------------------------------------------------------------

def location_picker(
    *,
    key: str,
    title: str,
    default_lat: float,
    default_lon: float,
) -> tuple[float, float]:
    lat_key = f"{key}_lat"
    lon_key = f"{key}_lon"

    if lat_key not in st.session_state:
        st.session_state[lat_key] = default_lat
    if lon_key not in st.session_state:
        st.session_state[lon_key] = default_lon

    lat = float(st.session_state[lat_key])
    lon = float(st.session_state[lon_key])

    st.markdown(f"**{title}**")
    st.caption("Click the map to place the location pin.")

    map_obj = folium.Map(
        location=[lat, lon],
        zoom_start=12,
        tiles="OpenStreetMap",
        control_scale=True,
    )
    folium.Marker(
        [lat, lon],
        tooltip="Selected location",
        icon=folium.Icon(color="darkgreen", icon="home"),
    ).add_to(map_obj)

    result = st_folium(
        map_obj,
        key=f"{key}_map",
        height=310,
        use_container_width=True,
        returned_objects=["last_clicked"],
    )

    clicked = (result or {}).get("last_clicked")
    if clicked:
        new_lat = float(clicked["lat"])
        new_lon = float(clicked["lng"])

        if (
            abs(new_lat - lat) > 0.000001
            or abs(new_lon - lon) > 0.000001
        ):
            st.session_state[lat_key] = new_lat
            st.session_state[lon_key] = new_lon
            st.rerun()

    st.caption(
        f"Selected coordinates: "
        f"{st.session_state[lat_key]:.6f}, "
        f"{st.session_state[lon_key]:.6f}"
    )

    return (
        float(st.session_state[lat_key]),
        float(st.session_state[lon_key]),
    )


def render_listing_gallery(
    listings: list[dict],
    *,
    empty_message: str,
    key_prefix: str,
) -> None:
    """Display live Lakebase listings; Gold still owns match eligibility."""
    if not listings:
        st.info(empty_message)
        return

    columns = st.columns(3, gap="large")
    for index, listing in enumerate(listings):
        listing_id = str(listing["listing_id"])
        category = str(listing.get("category") or "Other").replace("_", " ").title()
        condition = str(listing.get("condition") or "Condition unknown").replace("_", " ").title()
        location = str(listing.get("location") or "Location unavailable").strip()
        title = str(listing.get("title") or "Untitled item").strip()
        description = str(listing.get("description") or "No description provided.").strip()

        with columns[index % 3]:
            with st.container(border=True):
                image_bytes = load_listing_image(marketplace, listing_id)
                if image_bytes:
                    st.image(image_bytes, use_container_width=True)
                else:
                    st.markdown(
                        '<div class="listing-image-placeholder">'
                        '<span>Photo unavailable</span></div>',
                        unsafe_allow_html=True,
                    )

                st.markdown(
                    f"""
                    <div class="listing-card-copy">
                      <div class="product-card-top">
                        <span class="product-category">{html.escape(category)}</span>
                        <span class="listing-live-badge">Listed</span>
                      </div>
                      <h3 class="product-title">{html.escape(title)}</h3>
                      <div class="product-area">{html.escape(location)}</div>
                      <p class="listing-description">{html.escape(description)}</p>
                      <div class="product-meta">
                        <span>{html.escape(condition)}</span>
                        <span>Free item</span>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(
                    "View details & photos",
                    key=f"{key_prefix}_photo_{listing_id}",
                    type="secondary",
                    use_container_width=True,
                ):
                    show_listing_photo(
                        listing_id=listing_id, title=title,
                        description=description, location=location,
                        category=category, condition=condition,
                    )

def render_deployment_evidence() -> None:
    """Render non-secret deployed-runtime proof without changing business state."""

    with st.expander("Deployment & permissions evidence", expanded=False):
        target_label = (
            "Databricks App"
            if DEPLOYMENT_TARGET == "databricks_app"
            else "Streamlit Cloud / external Streamlit"
        )
        st.caption(
            f"Runtime target: {target_label}. This check uses the same Lakebase "
            "connection as the running application and never prints passwords, "
            "OAuth tokens, API keys, or secret values."
        )

        config = RUNTIME_STATUS
        cfg1, cfg2, cfg3 = st.columns(3)
        cfg1.metric(
            "Marketplace config",
            "PASS" if config["marketplace_ready"] else "CHECK",
        )
        cfg2.metric(
            "AI Agent config",
            "PASS" if config["agent_ready"] else "CHECK",
        )
        cfg3.metric(
            "Deployment target",
            "Databricks App"
            if DEPLOYMENT_TARGET == "databricks_app"
            else "Streamlit Cloud",
        )

        if config["marketplace_missing"]:
            st.warning(
                "Missing marketplace configuration names: "
                + ", ".join(config["marketplace_missing"])
            )
        if config["agent_missing"]:
            st.info(
                "Missing AI configuration names: "
                + ", ".join(config["agent_missing"])
            )

        try:
            evidence = marketplace.runtime_identity_permissions()
        except Exception as exc:
            st.error("FAIL — deployed App cannot validate its Lakebase runtime identity.")
            st.code(str(exc))
            return

        status = "PASS" if evidence["all_required"] else "FAIL"
        st.markdown(f"**{status} — Lakebase runtime identity and required grants**")

        e1, e2, e3 = st.columns(3)
        e1.metric("Schema USAGE", "PASS" if evidence["schema_usage"] else "FAIL")
        e2.metric(
            "Required table grants",
            "PASS" if all(evidence["privileges"].values()) else "FAIL",
        )
        e3.metric("Runtime database", str(evidence["database"]))

        st.code(
            "\n".join(
                [
                    f"current_user = {evidence['current_user']}",
                    f"session_user = {evidence['session_user']}",
                    f"database = {evidence['database']}",
                ]
            )
        )

        privilege_rows = [
            {
                "object_privilege": name,
                "status": "PASS" if ok else "FAIL",
            }
            for name, ok in evidence["privileges"].items()
        ]
        st.dataframe(privilege_rows, use_container_width=True, hide_index=True)

        if st.session_state.last_created_listing_id:
            listing = marketplace.get_listing_record(
                st.session_state.last_created_listing_id
            )
            st.markdown(
                "**Live donor listing write/readback:** "
                + ("PASS" if listing else "FAIL")
            )
            if listing:
                st.code(f"listing_id = {listing['listing_id']}")

        if st.session_state.last_created_request_id:
            request = marketplace.get_request_record(
                st.session_state.last_created_request_id
            )
            st.markdown(
                "**Live requester request write/readback:** "
                + ("PASS" if request else "FAIL")
            )
            if request:
                st.code(f"request_id = {request['request_id']}")

        if st.session_state.last_agent_read_tools:
            st.markdown("**Last Agent READ:** PASS")
            st.code(
                "tools = "
                + ", ".join(st.session_state.last_agent_read_tools)
            )

        if st.session_state.last_save_status:
            st.markdown(
                f"**Last Agent WRITE:** {st.session_state.last_save_status}"
            )
            if st.session_state.last_saved_item_id:
                st.code(
                    "\n".join(
                        [
                            f"saved_item_id = {st.session_state.last_saved_item_id}",
                            f"listing_id = {st.session_state.last_saved_listing_id}",
                            "saved_state_refresh = "
                            + (
                                "PASS"
                                if st.session_state.last_saved_refresh_pass
                                else "FAIL"
                            ),
                        ]
                    )
                )


def reset_request_session(request_id: str, requester_id: str) -> None:
    if (
        st.session_state.active_request_id != request_id
        or st.session_state.active_requester_id != requester_id
    ):
        st.session_state.active_request_id = request_id
        st.session_state.active_requester_id = requester_id
        st.session_state.messages = []
        st.session_state.pending_save = None
        st.session_state.tool_trace = []


def run_agent_turn(
    *,
    user_id: str,
    request_id: str,
    prompt: str,
) -> None:
    if agent is None:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": (
                    "SHIPP AI Advisor is not configured for this deployment yet. "
                    "The operational marketplace remains available."
                ),
            }
        )
        if agent_startup_error:
            st.caption(f"AI configuration: {agent_startup_error}")
        return

    try:
        with st.spinner("SHIPP is checking trusted matches and current availability..."):
            turn = agent.chat(
                user_id=user_id,
                request_id=request_id,
                user_message=prompt,
                history=st.session_state.messages,
            )

        reply = turn.reply or ""

        if is_agent_fallback(reply):
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": (
                        "SHIPP Advisor is temporarily unavailable. "
                        "You can still browse the trusted matching items."
                    ),
                }
            )
        elif reply:
            st.session_state.messages.append(
                {"role": "assistant", "content": reply}
            )

        st.session_state.pending_save = turn.pending_save
        st.session_state.tool_trace = turn.tool_trace
        read_tool_names = {
            "get_candidate_matches",
            "search_listing_context",
            "get_listing_status",
        }
        st.session_state.last_agent_read_tools = sorted(
            {
                str(trace.get("tool", ""))
                for trace in turn.tool_trace
                if str(trace.get("tool", "")) in read_tool_names
            }
        )

    except Exception as exc:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": (
                    "SHIPP Advisor is temporarily unavailable. "
                    "You can still browse the trusted matching items."
                ),
            }
        )
        st.code(str(exc))


def render_saved_items(user_id: str, request_id: str) -> None:
    try:
        saved_items = marketplace.list_saved_items(user_id, request_id)
    except Exception as exc:
        st.caption("Saved items are temporarily unavailable.")
        st.code(str(exc))
        return

    if not saved_items:
        st.caption("No saved items for this request yet.")
        return

    for item in saved_items:
        condition = item.get("condition") or "Condition not specified"
        location = item.get("location") or "Location not specified"
        saved_at = item.get("saved_at")

        st.markdown(
            f"""
            <div class="saved-card">
              <div class="saved-title">♡ {html.escape(str(item['title']))}</div>
              <div class="saved-meta">
                {html.escape(str(condition))} ·
                {html.escape(str(location))} ·
                Saved {html.escape(str(saved_at))}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.expander("Technical saved-state evidence", expanded=False):
        st.dataframe(saved_items, use_container_width=True, hide_index=True)




def initialize_session() -> None:
    """Initialize independent mutable state on every new Streamlit session."""
    import copy
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = copy.deepcopy(default_value)

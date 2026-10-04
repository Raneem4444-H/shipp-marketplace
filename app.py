# ============================================================
# SHIPP — Databricks App
# Hybrid Marketplace + AI Advisor
# ============================================================

from __future__ import annotations

import html
import os
from datetime import date, timedelta
from pathlib import Path
import sys

import folium
import streamlit as st
from streamlit_folium import st_folium


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
# Page / theme
# ------------------------------------------------------------

st.set_page_config(
    page_title="SHIPP",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed",
)


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
    settings = AgentSettings.from_env()
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


try:
    agent = load_agent()
    marketplace = load_marketplace()
except Exception:
    st.error(
        "SHIPP cannot reach its Databricks resources right now. "
        "Please refresh the app or try again shortly."
    )
    st.stop()


@st.cache_data(ttl=120, show_spinner=False)
def load_listing_image(_marketplace: MarketplaceRepo, listing_id: str) -> bytes | None:
    return _marketplace.get_primary_listing_image(listing_id)


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

    except Exception:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": (
                    "SHIPP Advisor is temporarily unavailable. "
                    "You can still browse the trusted matching items."
                ),
            }
        )


def render_saved_items(user_id: str, request_id: str) -> None:
    try:
        saved_items = marketplace.list_saved_items(user_id, request_id)
    except Exception:
        st.caption("Saved items are temporarily unavailable.")
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


# ------------------------------------------------------------
# Header / product positioning
# ------------------------------------------------------------

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
      <div class="shipp-status">
        <span class="shipp-status-dot"></span>
        Marketplace online
      </div>
    </div>

    <section class="shipp-hero">
      <div class="shipp-eyebrow">AI-assisted household marketplace</div>
      <h1>Give useful household items a second life.</h1>
      <p>
        Give away household items you no longer need, or find trusted matches
        near you. SHIPP combines route-aware matching with an AI advisor that
        can explain and help you save the best option.
      </p>
    </section>
    """,
    unsafe_allow_html=True,
)

st.markdown("## What would you like to do?")

persona = st.radio(
    "Choose your marketplace journey",
    ["Give an item", "Find an item"],
    horizontal=True,
    label_visibility="collapsed",
)


# ============================================================
# DONOR JOURNEY
# ============================================================

if persona == "Give an item":
    st.markdown("### Give an item")
    st.caption(
        "Create a clear listing with photos, item details, pickup location, "
        "and availability."
    )

    try:
        donors = marketplace.list_users("DONOR")
    except Exception as exc:
        st.error("Donor profiles are temporarily unavailable.")
        st.code(str(exc))
        st.stop()

    if not donors:
        st.info("No donor demo profiles are available.")
        st.stop()

    donor_by_label = {
        display_user(row): row["user_id"]
        for row in donors
    }

    donor_label = st.selectbox(
        "Donor profile",
        list(donor_by_label),
        key="donor_profile",
    )
    donor_id = donor_by_label[donor_label]

    st.markdown("#### 1. Add photos")
    uploaded_files = st.file_uploader(
        "Upload item photos",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        help="Upload 1–5 clear photos. The first photo is used as the cover image.",
    )

    if uploaded_files:
        if len(uploaded_files) > 5:
            st.warning("Please keep the listing to a maximum of 5 photos.")
        preview_columns = st.columns(min(len(uploaded_files), 3))
        for index, upload in enumerate(uploaded_files[:5]):
            with preview_columns[index % len(preview_columns)]:
                st.image(
                    upload,
                    caption="Cover photo" if index == 0 else upload.name,
                    use_container_width=True,
                )

    st.markdown("#### 2. Item details")
    detail_left, detail_right = st.columns(2)

    with detail_left:
        title = st.text_input(
            "Item title",
            placeholder="Wooden dining table",
        )
        category = st.selectbox("Category", CATEGORIES)
        condition = st.selectbox("Condition", CONDITIONS)

    with detail_right:
        available_until = st.date_input(
            "Available until",
            value=date.today() + timedelta(days=14),
            min_value=date.today(),
        )
        location_name = st.text_input(
            "Pickup area",
            placeholder="Al Reem Island, Abu Dhabi",
        )

    description = st.text_area(
        "Description",
        placeholder=(
            "Describe size, material, condition, useful features, "
            "and anything the requester should know."
        ),
        height=120,
    )

    st.markdown("#### 3. Pickup location")
    donor_lat, donor_lon = location_picker(
        key="donor",
        title="Choose the pickup point",
        default_lat=24.4976,
        default_lon=54.4075,
    )

    st.markdown("#### 4. Preview and publish")

    preview_title = title.strip() or "Your item title"
    preview_condition = condition.replace("_", " ").title()
    preview_location = location_name.strip() or "Pickup area"

    with st.container(border=True):
        preview_left, preview_right = st.columns([1, 2])

        with preview_left:
            if uploaded_files:
                st.image(uploaded_files[0], use_container_width=True)
            else:
                st.caption("Add a photo to complete the listing preview.")

        with preview_right:
            st.markdown(f"### {preview_title}")
            st.caption(
                f"{category.title()} · {preview_condition} · {preview_location}"
            )
            st.write(
                description.strip()
                or "Add a description so requesters understand the item."
            )
            st.caption(f"Available until {available_until}")

    if st.button(
        "Publish item",
        type="primary",
        use_container_width=True,
        key="publish_listing",
    ):
        if not uploaded_files:
            st.warning("Add at least one item photo before publishing.")
        elif len(uploaded_files) > 5:
            st.warning("Please keep the listing to a maximum of 5 photos.")
        elif not title.strip() or not location_name.strip():
            st.warning("Item title and pickup area are required.")
        elif not description.strip():
            st.warning("Add a short description before publishing.")
        else:
            try:
                listing_id = marketplace.create_listing(
                    donor_id=donor_id,
                    title=title,
                    description=description,
                    category=category,
                    condition=condition,
                    location=location_name,
                    latitude=donor_lat,
                    longitude=donor_lon,
                    available_until=available_until,
                )
                st.session_state.last_created_listing_id = listing_id

                try:
                    saved_images = marketplace.save_listing_images(
                        listing_id,
                        uploaded_files,
                    )
                    st.success(
                        f"Your item is live with {len(saved_images)} photo"
                        f"{'s' if len(saved_images) != 1 else ''}."
                    )
                except Exception:
                    st.warning(
                        "The listing was published, but the photos could not be "
                        "stored. Check the App service-principal access to the "
                        "listing image Volume before the final demo."
                    )

                st.caption(
                    "SHIPP will use the existing incremental pipeline to make "
                    "the listing available for trusted matching."
                )

            except Exception:
                st.error("The item could not be published. No duplicate action was attempted.")


# ============================================================
# REQUESTER JOURNEY
# ============================================================

else:
    st.markdown("### Find an item")
    st.caption(
        "Choose an existing need or create a new one, then browse trusted "
        "matches and ask SHIPP to compare the strongest options."
    )

    try:
        requesters = marketplace.list_users("REQUESTER")
    except Exception as exc:
        st.error("Requester profiles are temporarily unavailable.")
        st.code(str(exc))
        st.stop()

    if not requesters:
        st.info("No requester demo profiles are available.")
        st.stop()

    requester_by_label = {
        display_user(row): row["user_id"]
        for row in requesters
    }

    requester_label = st.selectbox(
        "Requester profile",
        list(requester_by_label),
        key="requester_profile",
    )
    requester_id = requester_by_label[requester_label]

    request_mode = st.radio(
        "Your need",
        ["Use an existing request", "Create a new request"],
        horizontal=True,
    )

    selected_request_id = None
    selected_request_summary = None

    if request_mode == "Create a new request":
        st.markdown("#### Tell SHIPP what you need")

        request_left, request_right = st.columns(2)

        with request_left:
            request_category = st.selectbox(
                "Category",
                CATEGORIES,
                key="request_category",
            )
            need_by_date = st.date_input(
                "Need it by",
                value=date.today() + timedelta(days=7),
                min_value=date.today(),
                key="request_need_by",
            )

        with request_right:
            request_location = st.text_input(
                "Your area",
                placeholder="Al Maryah Island, Abu Dhabi",
                key="request_location",
            )

        request_text = st.text_area(
            "Describe what you need",
            placeholder=(
                "Example: I need a compact wooden dining table "
                "for a small apartment."
            ),
            height=110,
            key="request_text",
        )

        requester_lat, requester_lon = location_picker(
            key="requester",
            title="Choose where you need the item",
            default_lat=24.5014,
            default_lon=54.3872,
        )

        if st.button(
            "Create request",
            type="primary",
            use_container_width=True,
            key="create_request",
        ):
            if not request_text.strip() or not request_location.strip():
                st.warning("Description and location are required.")
            else:
                try:
                    new_request_id = marketplace.create_request(
                        requester_id=requester_id,
                        request_text=request_text,
                        category=request_category,
                        location=request_location,
                        latitude=requester_lat,
                        longitude=requester_lon,
                        need_by_date=need_by_date,
                    )
                    st.session_state.last_created_request_id = new_request_id
                    selected_request_id = new_request_id
                    selected_request_summary = request_text.strip()
                    reset_request_session(new_request_id, requester_id)
                    st.success("Your request was created.")
                    st.caption(
                        "New requests become browsable after the existing SHIPP "
                        "incremental pipeline refreshes trusted Gold matches."
                    )
                except Exception:
                    st.error("The request could not be created.")

        if selected_request_id is None:
            selected_request_id = st.session_state.last_created_request_id

    else:
        try:
            requests = marketplace.list_requests(requester_id)
        except Exception:
            st.error("Your requests are temporarily unavailable.")
            st.stop()

        if not requests:
            st.info("No requests yet. Create one to start matching.")
        else:
            request_by_label = {}
            request_by_id = {}

            for row in requests:
                label = (
                    f"{str(row['category'] or 'Other').title()} — "
                    f"{str(row['request_text'])[:80]}"
                )
                request_by_label[label] = row["request_id"]
                request_by_id[row["request_id"]] = row

            selected_label = st.selectbox(
                "Choose your request",
                list(request_by_label),
            )
            selected_request_id = request_by_label[selected_label]
            selected_request_summary = request_by_id[selected_request_id][
                "request_text"
            ]

    if selected_request_id:
        reset_request_session(selected_request_id, requester_id)
        request_id = selected_request_id
        user_id = requester_id

        st.markdown("---")

        summary = (
            selected_request_summary
            or "Your selected household-item request"
        )

        header_left, header_right = st.columns([3, 1])

        with header_left:
            st.markdown("### Matching items")
            st.caption(summary)

        with header_right:
            with st.expander("♡ Saved", expanded=False):
                render_saved_items(user_id, request_id)

        try:
            matches = agent.get_candidate_matches(
                user_id=user_id,
                request_id=request_id,
            )
        except Exception:
            matches = []
            st.warning(
                "Trusted candidate matches are temporarily unavailable. "
                "You can retry after the pipeline or warehouse is ready."
            )

        browse_mode = st.radio(
            "Browse",
            ["Nearby", "Search"],
            horizontal=True,
            label_visibility="collapsed",
            key="browse_mode",
        )

        search_left, filter_right = st.columns([2.2, 1])

        with search_left:
            if browse_mode == "Search":
                product_query = st.text_input(
                    "Search within your trusted matches",
                    placeholder=(
                        "Example: compact wooden table, good condition, "
                        "small apartment..."
                    ),
                    key="product_query",
                )
            else:
                product_query = ""

        with filter_right:
            sort_option = st.selectbox(
                "Sort by",
                ["Best match", "Nearest", "Shortest travel time"],
                key="sort_option",
            )

        with st.expander("Filters", expanded=False):
            f1, f2, f3 = st.columns(3)

            available_conditions = sorted(
                {
                    str(match.condition)
                    for match in matches
                    if match.condition
                }
            )

            with f1:
                condition_filter = st.multiselect(
                    "Condition",
                    available_conditions,
                    key="condition_filter",
                )

            with f2:
                min_score = st.slider(
                    "Minimum match",
                    0,
                    100,
                    0,
                    5,
                    format="%d%%",
                    key="min_score",
                )

            with f3:
                radius_km = st.selectbox(
                    "Maximum distance",
                    [5, 10, 25, 50, 100],
                    index=2,
                    format_func=lambda value: f"{value} km",
                    key="radius_km",
                )

        filtered_matches = []
        normalized_query = product_query.strip().lower()

        for match in matches:
            score = float(match.match_score or 0.0)
            score_percent = score * 100 if score <= 1 else score

            searchable = " ".join(
                [
                    str(match.title or ""),
                    str(match.category or ""),
                    str(match.condition or ""),
                    str(match.area or ""),
                ]
            ).lower()

            if normalized_query and normalized_query not in searchable:
                continue

            if condition_filter and str(match.condition) not in condition_filter:
                continue

            if score_percent < min_score:
                continue

            if (
                match.distance_km is not None
                and float(match.distance_km) > float(radius_km)
            ):
                continue

            if browse_mode == "Nearby" and match.distance_km is None:
                continue

            filtered_matches.append(match)

        if sort_option == "Best match":
            filtered_matches.sort(
                key=lambda item: float(item.match_score or 0.0),
                reverse=True,
            )
        elif sort_option == "Nearest":
            filtered_matches.sort(
                key=lambda item: (
                    item.distance_km is None,
                    float(item.distance_km)
                    if item.distance_km is not None
                    else float("inf"),
                )
            )
        else:
            filtered_matches.sort(
                key=lambda item: (
                    item.duration_min is None,
                    float(item.duration_min)
                    if item.duration_min is not None
                    else float("inf"),
                )
            )

        st.caption(
            f"{len(filtered_matches)} item"
            f"{'s' if len(filtered_matches) != 1 else ''} shown "
            f"from {len(matches)} trusted candidate"
            f"{'s' if len(matches) != 1 else ''}."
        )

        if not matches:
            st.info(
                "No trusted matches are available for this request yet. "
                "If the request is new, refresh after the pipeline completes."
            )

        elif not filtered_matches:
            st.info(
                "No items match these filters. Increase the distance or clear "
                "one of the filters."
            )

        else:
            card_columns = st.columns(3)

            for index, match in enumerate(filtered_matches):
                with card_columns[index % 3]:
                    image_bytes = load_listing_image(
                        marketplace,
                        match.listing_id,
                    )

                    if image_bytes:
                        st.image(image_bytes, use_container_width=True)

                    score = float(match.match_score or 0.0)
                    score_percent = score * 100 if score <= 1 else score

                    distance_text = (
                        f"{float(match.distance_km):.1f} km"
                        if match.distance_km is not None
                        else "Distance pending"
                    )
                    duration_text = (
                        f"{float(match.duration_min):.0f} min"
                        if match.duration_min is not None
                        else "Route time pending"
                    )
                    area_text = str(match.area or "Area not specified")
                    condition_text = str(
                        match.condition or "Condition not specified"
                    ).replace("_", " ").title()

                    st.markdown(
                        f"""
                        <div class="product-card">
                          <div class="product-card-top">
                            <span class="product-category">
                              {html.escape(str(match.category).title())}
                            </span>
                            <span class="product-score">
                              {score_percent:.0f}% match
                            </span>
                          </div>
                          <h3 class="product-title">
                            {html.escape(str(match.title))}
                          </h3>
                          <div class="product-area">
                            {html.escape(area_text)}
                          </div>
                          <div class="product-meta">
                            <span>{html.escape(condition_text)}</span>
                            <span>{html.escape(distance_text)}</span>
                          </div>
                          <div class="product-duration">
                            {html.escape(duration_text)} travel time
                          </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    if st.button(
                        "Ask SHIPP",
                        key=f"ask_{match.listing_id}",
                        use_container_width=True,
                    ):
                        run_agent_turn(
                            user_id=user_id,
                            request_id=request_id,
                            prompt=(
                                f"Compare listing {match.listing_id} with the "
                                "request. Use semantic listing context and check "
                                "its current operational status. Explain strengths "
                                "and limitations, but do not save anything."
                            ),
                        )
                        st.rerun()

                    if st.button(
                        "Review for save",
                        key=f"review_{match.listing_id}",
                        type="primary",
                        use_container_width=True,
                    ):
                        run_agent_turn(
                            user_id=user_id,
                            request_id=request_id,
                            prompt=(
                                f"Evaluate candidate listing {match.listing_id}. "
                                "Use trusted Gold data, semantic context, and the "
                                "current Lakebase listing status. If it is suitable "
                                "and available, propose saving it."
                            ),
                        )
                        st.rerun()

        st.markdown("---")
        st.markdown("### SHIPP AI Advisor")
        st.caption(
            "Ask SHIPP to compare the strongest matches, explain condition or "
            "distance, or recommend the best option."
        )

        if st.button(
            "Compare my top matches",
            use_container_width=True,
            key="compare_top_matches",
        ):
            run_agent_turn(
                user_id=user_id,
                request_id=request_id,
                prompt=(
                    "Compare the top two or three available candidates for this "
                    "request. Use Gold candidate matches, relevant AI Search "
                    "context, and current listing status. Explain which is best "
                    "overall and why. Do not invent any listing."
                ),
            )
            st.rerun()

        with st.form("advisor_prompt_form", clear_on_submit=True):
            advisor_prompt = st.text_input(
                "Ask SHIPP",
                placeholder=(
                    "Example: Which option is best for a small apartment?"
                ),
                label_visibility="collapsed",
            )
            advisor_submitted = st.form_submit_button(
                "Ask SHIPP",
                use_container_width=True,
            )

        if advisor_submitted and advisor_prompt.strip():
            st.session_state.messages.append(
                {"role": "user", "content": advisor_prompt.strip()}
            )
            run_agent_turn(
                user_id=user_id,
                request_id=request_id,
                prompt=advisor_prompt.strip(),
            )
            st.rerun()

        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        pending = st.session_state.pending_save

        if pending is not None:
            st.markdown("#### Ready to save")

            st.markdown(
                f"""
                <div class="shipp-recommendation">
                  <span class="shipp-recommendation-label">SHIPP recommendation</span>
                  <div class="shipp-recommendation-title">
                    {html.escape(str(pending.title))}
                  </div>
                  <div class="shipp-reason">
                    <strong>Why it fits:</strong>
                    {html.escape(str(pending.reason))}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            confirm_left, confirm_right = st.columns([1, 2])

            with confirm_left:
                if st.button(
                    "Cancel",
                    use_container_width=True,
                    key="cancel_save",
                ):
                    st.session_state.pending_save = None
                    st.rerun()

            with confirm_right:
                if st.button(
                    "♡ Save this item",
                    type="primary",
                    use_container_width=True,
                    key="confirm_save",
                ):
                    try:
                        with st.spinner(
                            "Rechecking current availability before saving..."
                        ):
                            result = agent.confirm_save(
                                user_id=user_id,
                                request_id=request_id,
                                listing_id=pending.listing_id,
                            )

                        if result.ok:
                            st.session_state.pending_save = None
                            st.success("Item saved successfully.")

                            with st.expander(
                                "Technical save evidence",
                                expanded=False,
                            ):
                                st.code(
                                    f"saved_item_id = {result.saved_item_id}"
                                )
                        else:
                            st.warning(
                                "SHIPP rechecked the current listing state and "
                                f"did not save the item: {result.message}"
                            )
                    except Exception:
                        st.error(
                            "The save could not be completed. No unconfirmed "
                            "write was performed."
                        )

        if st.session_state.tool_trace:
            with st.expander(
                "How SHIPP produced this recommendation",
                expanded=False,
            ):
                st.caption(
                    "Evidence path: trusted Gold candidates → semantic context "
                    "→ current operational listing state."
                )
                with st.expander("Technical agent trace", expanded=False):
                    for number, trace in enumerate(
                        st.session_state.tool_trace,
                        start=1,
                    ):
                        st.markdown(
                            f"**{number}. {trace.get('tool', 'unknown')}**"
                        )
                        st.json(trace)


# ------------------------------------------------------------
# Professional project footer
# ------------------------------------------------------------

st.markdown(
    """
    <div class="shipp-footer">
      <div><strong>SHIPP</strong> · Databricks Data & AI Engineering Capstone</div>
      <div class="shipp-footer-team">
        Built by
        <strong>Raneem Alhamarneh</strong>
        · <a href="https://github.com/Raneem4444-H" target="_blank">GitHub</a>
        · <a href="https://www.linkedin.com/in/raneem-alhamarneh/" target="_blank">LinkedIn</a>
        &nbsp;&nbsp;|&nbsp;&nbsp;
        <strong>AbdulRahman</strong>
        · <a href="https://github.com/Abdulrahman2k" target="_blank">GitHub</a>
        · <a href="https://www.linkedin.com/in/abdulrahman2k/" target="_blank">LinkedIn</a>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

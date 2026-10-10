"""SHIPP requester page — verified user, needs, matching, and AI saves."""
from __future__ import annotations
from ui.legacy_core import *  # noqa: F403,F401
from services.identity_service import require_role

def render_requester():
    profile = require_role("REQUESTER")
    if profile is None:
        st.stop()

    requester_id = str(profile["user_id"])

    render_deployment_evidence()
    st.markdown("### Find an item")
    st.caption(
        "Choose an existing need or create a new one, then browse trusted "
        "matches and ask SHIPP to compare the strongest options."
    )

    st.markdown("#### Marketplace")
    st.caption(
        "Browse current donor listings with real photos and descriptions. "
        "For your request, SHIPP will only recommend items that pass the "
        "trusted Gold matching pipeline."
    )
    try:
        live_listings = marketplace.list_available_listings(limit=12)
        render_listing_gallery(
            live_listings,
            empty_message="No donor listings are currently available.",
            key_prefix="marketplace",
        )
    except Exception as exc:
        st.warning("Marketplace listings are temporarily unavailable.")
        st.code(str(exc))

    st.markdown("---")

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
            width="stretch",
            key="create_request",
        ):
            if not request_text.strip() or not request_location.strip():
                st.warning("Description and location are required.")
            elif not st.session_state.get("requester_pin_confirmed", False):
                st.warning("Select your location on the map first.")
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
                    # New requests must use a deliberately chosen pin.
                    st.session_state["requester_pin_confirmed"] = False
                    st.session_state["requester_map_version"] = (
                        st.session_state.get("requester_map_version", 0) + 1
                    )
                    st.session_state.last_created_request_id = new_request_id
                    selected_request_id = new_request_id
                    selected_request_summary = request_text.strip()
                    reset_request_session(new_request_id, requester_id)
                    persisted_request = marketplace.get_request_record(new_request_id)
                    if persisted_request is None:
                        st.error(
                            "The request write returned an ID but Lakebase readback failed."
                        )
                    else:
                        st.success("Your request was created and confirmed in Lakebase.")
                        with st.expander("Technical request evidence", expanded=False):
                            st.code(f"request_id = {new_request_id}")

                    st.caption(
                        "New requests become browsable after the existing SHIPP "
                        "incremental pipeline refreshes trusted Gold matches."
                    )
                except Exception as exc:
                    st.error("The request could not be created.")
                    st.code(str(exc))

        if selected_request_id is None:
            selected_request_id = st.session_state.last_created_request_id

    else:
        try:
            requests = marketplace.list_requests(requester_id)
        except Exception as exc:
            st.error("Your requests are temporarily unavailable.")
            st.code(str(exc))
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

        if agent is None:
            matches = []
            st.info(
                "Trusted AI matching is not configured for this external "
                "deployment yet. Marketplace browsing and request creation "
                "remain available."
            )
            if agent_startup_error:
                st.caption(f"AI configuration: {agent_startup_error}")
        else:
            try:
                matches = agent.get_candidate_matches(
                    user_id=user_id,
                    request_id=request_id,
                )
            except Exception as exc:
                matches = []
                st.warning(
                    "Trusted candidate matches are temporarily unavailable. "
                    "You can retry after the pipeline or warehouse is ready."
                )
                st.code(str(exc))

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
                        st.image(image_bytes, width="stretch")

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
                        width="stretch",
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
                        width="stretch",
                    ):
                        try:
                            with st.spinner(
                                "Checking trusted match and current availability..."
                            ):
                                review = agent.review_for_save(
                                    user_id=user_id,
                                    request_id=request_id,
                                    listing_id=match.listing_id,
                                )
                            st.session_state.pending_save = review.pending_save
                            st.session_state.review_error = None
                            st.session_state.tool_trace = review.tool_trace
                            st.session_state.messages.append(
                                {"role": "assistant", "content": review.reply}
                            )
                            st.session_state.last_agent_read_tools = sorted(
                                {
                                    str(trace.get("tool", ""))
                                    for trace in review.tool_trace
                                    if str(trace.get("tool", ""))
                                    in {
                                        "get_candidate_matches",
                                        "search_listing_context",
                                        "get_listing_status",
                                    }
                                }
                            )
                        except Exception as exc:
                            st.session_state.pending_save = None
                            st.session_state.tool_trace = []
                            st.session_state.messages.append(
                                {
                                    "role": "assistant",
                                    "content": (
                                        "Review could not be completed. "
                                        "Please retry, or ask the administrator "
                                        "to inspect the App logs."
                                    ),
                                }
                            )
                            st.session_state.review_error = str(exc)
                        st.rerun()

        st.markdown("---")
        st.markdown("### SHIPP AI Advisor")
        st.caption(
            "Ask SHIPP to compare the strongest matches, explain condition or "
            "distance, or recommend the best option."
        )

        if st.button(
            "Compare my top matches",
            width="stretch",
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
                width="stretch",
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
                    width="stretch",
                    key="cancel_save",
                ):
                    st.session_state.pending_save = None
                    st.rerun()

            with confirm_right:
                if st.button(
                    "♡ Save this item",
                    type="primary",
                    width="stretch",
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
                            st.session_state.last_saved_item_id = result.saved_item_id
                            st.session_state.last_saved_listing_id = pending.listing_id
                            st.session_state.last_save_status = "PASS"
                            st.cache_data.clear()

                            saved_after = marketplace.list_saved_items(
                                user_id,
                                request_id,
                            )
                            saved_ids = {
                                str(row["saved_item_id"])
                                for row in saved_after
                            }
                            refresh_ok = (
                                result.saved_item_id is not None
                                and str(result.saved_item_id) in saved_ids
                            )
                            st.session_state.last_saved_refresh_pass = refresh_ok

                            if refresh_ok:
                                st.success(
                                    "Item saved and the refreshed Saved state "
                                    "was confirmed from Lakebase."
                                )
                            else:
                                st.error(
                                    "The Agent reported success, but the refreshed "
                                    "Saved state could not confirm the row."
                                )

                            with st.expander(
                                "Technical save evidence",
                                expanded=False,
                            ):
                                st.code(
                                    "\n".join(
                                        [
                                            f"saved_item_id = {result.saved_item_id}",
                                            f"listing_id = {pending.listing_id}",
                                            f"saved_state_refresh = {'PASS' if refresh_ok else 'FAIL'}",
                                        ]
                                    )
                                )
                        else:
                            st.session_state.last_save_status = f"REJECTED — {result.status.value}"
                            st.warning(
                                "SHIPP rechecked the current listing state and "
                                    f"did not save the item: {result.message}"
                            )
                    except Exception as exc:
                        st.error(
                            "The save could not be completed. No unconfirmed "
                            "write was performed."
                        )
                        st.code(str(exc))

        if st.session_state.review_error:
            st.error("Technical review error (admin diagnostics):")
            st.code(st.session_state.review_error)

        if st.session_state.tool_trace:
            tool_names = [
                str(trace.get("tool", "unknown"))
                for trace in st.session_state.tool_trace
            ]
            read_tools = {
                "get_candidate_matches",
                "search_listing_context",
                "get_listing_status",
            }
            exercised = sorted(read_tools.intersection(tool_names))

            with st.expander(
                "How SHIPP produced this recommendation",
                expanded=False,
            ):
                st.caption(
                    "Agent READ evidence: "
                    + (
                        "PASS — " + ", ".join(exercised)
                        if exercised
                        else "No read tool captured in the latest turn."
                    )
                )
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

render_requester()

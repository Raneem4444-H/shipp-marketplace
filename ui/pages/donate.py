"""SHIPP donor page — publish and manage your own donations."""

from __future__ import annotations

import os
from ui.location_geocoding import reverse_geocode_pickup_area
from ui.legacy_core import *  # noqa: F403,F401

from services.identity_service import require_role

def render_donor():
# ---------------------------------------------------------
# 0. SECURITY — VERIFIED DONOR IDENTITY
# ---------------------------------------------------------
    profile = require_role("DONOR")

    if profile is None:
        st.stop()

    # Never accept a donor ID from a demo profile selector.
    donor_id = str(profile["user_id"])

    render_deployment_evidence()

    st.markdown("### Give an item")
    st.caption(
        "Create a clear listing with photos, item details, "
        "pickup location, and availability."
    )

    # ---------------------------------------------------------
    # 1. CURRENT DONOR LISTINGS
    # ---------------------------------------------------------
    st.markdown("#### Your live listings")
    st.caption(
        "These are the items you have already published. "
        "Photos and descriptions are read from Lakebase."
    )

    try:
        donor_listings = marketplace.list_available_listings(
            donor_id=donor_id,
            limit=9,
        )

        render_listing_gallery(
            donor_listings,
            empty_message=(
                "No live listings yet — publish your first item below."
            ),
            key_prefix="donor_live",
        )

    except Exception as exc:
        st.warning("Your live listings are temporarily unavailable.")
        st.code(str(exc))

    st.markdown("---")

    # ---------------------------------------------------------
    # 2. UPLOAD PHOTOS
    # ---------------------------------------------------------
    st.markdown("#### 1. Add photos")

    uploaded_files = st.file_uploader(
        "Upload item photos",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        help=(
            "Upload 1–5 clear photos. "
            "The first photo is used as the cover image."
        ),
    )

    if uploaded_files:
        if len(uploaded_files) > 5:
            st.warning(
                "Please keep the listing to a maximum of 5 photos."
            )

        preview_columns = st.columns(
            min(len(uploaded_files), 3)
        )

        for index, upload in enumerate(uploaded_files[:5]):
            with preview_columns[index % len(preview_columns)]:
                st.image(
                    upload,
                    caption=(
                        "Cover photo"
                        if index == 0
                        else upload.name
                    ),
                    width="stretch",
                )

    # ---------------------------------------------------------
    # 3. ITEM DETAILS
    # ---------------------------------------------------------
    st.markdown("#### 2. Item details")

    detail_left, detail_right = st.columns(2)

    with detail_left:
        title = st.text_input(
            "Item title",
            placeholder="Wooden dining table",
        )

        category = st.selectbox(
            "Category",
            CATEGORIES,
        )

        condition = st.selectbox(
            "Condition",
            CONDITIONS,
        )

    with detail_right:
        available_until = st.date_input(
            "Available until",
            value=date.today() + timedelta(days=14),
            min_value=date.today(),
        )

        # location_name = st.text_input(
        #     "Pickup area",
        #     placeholder="Al Reem Island, Abu Dhabi",
        # )

    description = st.text_area(
        "Description",
        placeholder=(
            "Describe size, material, condition, useful features, "
            "and anything the requester should know."
        ),
        height=120,
    )

    # ---------------------------------------------------------
    # 4. PICKUP LOCATION
    # ---------------------------------------------------------
    st.markdown("#### 3. Pickup location")

    donor_lat, donor_lon = location_picker(
        key="donor",
        title="Choose the pickup point",
        default_lat=24.4976,
        default_lon=54.4075,
    )

    location_name = ""

    if st.session_state.get("donor_pin_confirmed", False):
        ors_key = os.getenv("ORS_API_KEY", "")

        if ors_key:
            location_name = (
                reverse_geocode_pickup_area(
                    donor_lat,
                    donor_lon,
                    ors_key,
                ) or ""
            )
        else:
            st.warning("Pickup geocoding is not configured.")

    st.text_input(
        "Pickup area",
        value=location_name,
        disabled=True,
        help="Automatically populated from your selected map pin.",
    )

    if (
        st.session_state.get("donor_pin_confirmed", False)
        and not location_name
    ):
        st.warning(
            "Could not identify the pickup area. "
            "Try selecting a nearby point."
        )

    # ---------------------------------------------------------
    # 5. LISTING PREVIEW
    # ---------------------------------------------------------
    st.markdown("#### 4. Preview and publish")

    preview_title = (
        title.strip() or "Your item title"
    )

    preview_condition = (
        condition.replace("_", " ").title()
    )

    preview_location = (
        location_name.strip() or "Pickup area"
    )

    with st.container(border=True):
        preview_left, preview_right = st.columns([1, 2])

        with preview_left:
            if uploaded_files:
                st.image(
                    uploaded_files[0],
                    width="stretch",
                )
            else:
                st.caption(
                    "Add a photo to complete the listing preview."
                )

        with preview_right:
            st.markdown(f"### {preview_title}")

            st.caption(
                f"{category.title()} · "
                f"{preview_condition} · "
                f"{preview_location}"
            )

            st.write(
                description.strip()
                or (
                    "Add a description so requesters "
                    "understand the item."
                )
            )

            st.caption(
                f"Available until {available_until}"
            )

    # ---------------------------------------------------------
    # 6. PUBLISH LISTING
    # ---------------------------------------------------------
    if st.button(
        "Publish item",
        type="primary",
        width="stretch",
        key="publish_listing",
    ):

        # Validate before writing to Lakebase.
        if not uploaded_files:
            st.warning(
                "Add at least one item photo before publishing."
            )

        elif len(uploaded_files) > 5:
            st.warning(
                "Please keep the listing to a maximum of 5 photos."
            )

        elif not title.strip() or not location_name.strip():
            st.warning(
                "Item title and pickup area are required."
            )

        elif not description.strip():
            st.warning(
                "Add a short description before publishing."
            )
        elif not st.session_state.get("donor_pin_confirmed", False):
            st.warning("Select your pickup point on the map first.")

        else:
            try:
                # ---------------------------------------------
                # 7. CREATE LISTING IN LAKEBASE
                # ---------------------------------------------
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
                st.session_state["donor_pin_confirmed"] = False
                st.session_state["donor_map_version"] = (
                    st.session_state.get("donor_map_version", 0) + 1
                )
                st.session_state.last_created_listing_id = (
                    listing_id
                )

                # ---------------------------------------------
                # 8. SAVE PHOTOS TO UNITY CATALOG VOLUME
                # ---------------------------------------------
                try:
                    saved_images = marketplace.save_listing_images(
                        listing_id,
                        uploaded_files,
                    )

                    st.success(
                        f"Your item is live with "
                        f"{len(saved_images)} photo"
                        f"{'s' if len(saved_images) != 1 else ''}."
                    )

                except Exception as exc:
                    st.code(str(exc))

                    st.warning(
                        "The listing was published, but the "
                        "photos could not be stored. "
                        "Check the App service-principal "
                        "access to the listing image Volume."
                    )

                # ---------------------------------------------
                # 9. VERIFY LISTING WRITE
                # ---------------------------------------------
                persisted_listing = (
                    marketplace.get_listing_record(listing_id)
                )

                if persisted_listing is None:
                    st.error(
                        "The listing write returned an ID, "
                        "but Lakebase readback failed."
                    )

                else:
                    st.success(
                        "Lakebase confirmed the published listing."
                    )

                    render_listing_gallery(
                        [persisted_listing],
                        empty_message="",
                        key_prefix="published",
                    )

                # ---------------------------------------------
                # 10. PIPELINE INFORMATION
                # ---------------------------------------------
                st.caption(
                    "SHIPP will use the existing incremental "
                    "pipeline to make the listing available "
                    "for trusted matching."
                )

            except Exception as exc:
                st.error(
                    "The item could not be published. "
                    "No duplicate action was attempted."
                )
                st.code(str(exc))

render_donor()

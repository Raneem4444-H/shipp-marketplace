"""Auto-extracted from the original SHIPP app; review before deployment."""
from __future__ import annotations
from ui.legacy_core import *  # noqa: F403,F401 — original dependencies

def render_donor():
    render_deployment_evidence()
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

    st.markdown("#### Your live listings")
    st.caption(
        "These are the items this donor has already published. Photos and "
        "descriptions are read from the operational marketplace."
    )
    try:
        donor_listings = marketplace.list_available_listings(
            donor_id=donor_id,
            limit=9,
        )
        render_listing_gallery(
            donor_listings,
            empty_message="No live listings yet — publish the first item below.",
            key_prefix="donor_live",
        )
    except Exception as exc:
        st.warning("Live donor listings are temporarily unavailable.")
        st.code(str(exc))

    st.markdown("---")
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
                    width="stretch",
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
                st.image(uploaded_files[0], width="stretch")
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
        width="stretch",
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
                except Exception as exc:
                    st.code(str(exc))
                    st.warning(
                        "The listing was published, but the photos could not be "
                        "stored. Check the App service-principal access to the "
                        "listing image Volume before the final demo."
                    )

                persisted_listing = marketplace.get_listing_record(listing_id)
                if persisted_listing is None:
                    st.error(
                        "The listing write returned an ID but Lakebase readback failed."
                    )
                else:
                    st.success("Lakebase confirmed the published listing.")
                    render_listing_gallery(
                        [persisted_listing],
                        empty_message="",
                        key_prefix="published",
                    )

                st.caption(
                    "SHIPP will use the existing incremental pipeline to make "
                    "the listing available for trusted matching."
                )

            except Exception as exc:
                st.error("The item could not be published. No duplicate action was attempted.")
                st.code(str(exc))

render_donor()

"""Auto-extracted from the original SHIPP app; review before deployment."""
from __future__ import annotations
from ui.legacy_core import *  # noqa: F403,F401 — original dependencies
from services.marketplace_service import MarketplaceService
CATALOG_PAGE_SIZE = 9

def render_explore() -> None:
    catalog = MarketplaceService(marketplace)
    st.markdown("## Explore donor items")
    st.caption("Search current Lakebase listings. Filters apply before pagination; only AVAILABLE, non-expired items appear.")
    search_col, category_col, condition_col = st.columns([2, 1, 1])
    with search_col:
        query = st.text_input("Search title or description", key="catalog_query",
                              placeholder="e.g. wooden dining table")
    with category_col:
        category = st.selectbox("Category", ["All categories", *CATEGORIES],
                                key="catalog_category")
    with condition_col:
        condition = st.selectbox("Condition", ["All conditions", *CONDITIONS],
                                 key="catalog_condition")

    # Changing the filters always returns to page 1; no stale offsets.
    signature = (query.strip(), category, condition)
    if st.session_state.get("_catalog_filter_signature") != signature:
        st.session_state["_catalog_filter_signature"] = signature
        st.session_state["catalog_page"] = 0

    page = max(0, int(st.session_state.get("catalog_page", 0)))
    try:
        records = catalog.list_available_listings(
            limit=CATALOG_PAGE_SIZE + 1,
            offset=page * CATALOG_PAGE_SIZE,
            query=query,
            category=None if category == "All categories" else category,
            condition=None if condition == "All conditions" else condition,
        )
    except Exception:
        st.error("Could not retrieve donor listings. Try again later.")
        return

    visible = records[:CATALOG_PAGE_SIZE]
    has_next = len(records) > CATALOG_PAGE_SIZE
    if page and not visible:
        st.session_state["catalog_page"] = page - 1
        st.rerun()
    st.caption(f"Showing page {page + 1}; {len(visible)} item(s) on this page.")
    render_listing_gallery(
        visible,
        empty_message="No available items match these filters.",
        key_prefix=f"catalog_{page}",
    )

    previous_col, next_col = st.columns(2)
    with previous_col:
        if st.button("← Previous page", key="catalog_prev", disabled=page == 0):
            st.session_state["catalog_page"] = page - 1
            st.rerun()
    with next_col:
        if st.button("Next page →", key="catalog_next", disabled=not has_next):
            st.session_state["catalog_page"] = page + 1
            st.rerun()

    st.info(
        "Browsing is not a reservation or Save action. For trusted matches and "
        "AI recommendations, open Find an item."
    )

render_explore()

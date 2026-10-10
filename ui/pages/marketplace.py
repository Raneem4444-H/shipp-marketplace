"""SHIPP Explore: server-filtered, paginated Lakebase catalog."""
from __future__ import annotations

from time import perf_counter

from ui.legacy_core import *  # noqa: F403,F401
from services.marketplace_service import MarketplaceService

CATALOG_PAGE_SIZE = 9


def render_explore() -> None:
    catalog = MarketplaceService(marketplace)
    st.markdown("## Explore available items")
    st.caption("Search household donations by name, description, category, or condition.")

    search_col, category_col, condition_col = st.columns([2, 1, 1])
    with search_col:
        query = st.text_input(
            "Search", key="catalog_query", placeholder="Search for a bed, table, books..."
        )
    with category_col:
        category = st.selectbox("Category", ["All categories", *CATEGORIES], key="catalog_category")
    with condition_col:
        condition = st.selectbox("Condition", ["All conditions", *CONDITIONS], key="catalog_condition")

    # A new filter combination always starts on page 1.
    signature = (query.strip(), category, condition)
    if st.session_state.get("_catalog_filter_signature") != signature:
        st.session_state["_catalog_filter_signature"] = signature
        st.session_state["catalog_page"] = 0

    page = max(0, int(st.session_state.get("catalog_page", 0)))
    try:
        catalog_start = perf_counter()
        records = catalog.list_available_listings(
            limit=CATALOG_PAGE_SIZE + 1,
            offset=page * CATALOG_PAGE_SIZE,
            query=query,
            category=None if category == "All categories" else category,
            condition=None if condition == "All conditions" else condition,
        )
        print(f"[PERF] Explore catalog: {perf_counter() - catalog_start:.3f}s")
    except Exception:
        st.error("Unable to load the item catalog. Please try again later.")
        return

    visible = records[:CATALOG_PAGE_SIZE]
    has_next = len(records) > CATALOG_PAGE_SIZE
    if page and not visible:
        st.session_state["catalog_page"] = page - 1
        st.rerun()

    st.caption(f"Page {page + 1} · {len(visible)} item(s) shown")
    render_listing_gallery(
        visible,
        empty_message="No items match these filters. Try another search or category.",
        key_prefix=f"catalog_{page}",
    )

    previous_col, next_col, _ = st.columns([1, 1, 3])
    with previous_col:
        if st.button("← Previous", key="catalog_prev", disabled=page == 0, width="stretch"):
            st.session_state["catalog_page"] = page - 1
            st.rerun()
    with next_col:
        if st.button("Next →", key="catalog_next", disabled=not has_next, width="stretch"):
            st.session_state["catalog_page"] = page + 1
            st.rerun()

    st.caption("Browsing an item does not reserve it. For request-specific matching, use Find an item.")


render_explore()

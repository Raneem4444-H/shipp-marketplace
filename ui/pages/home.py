"""SHIPP marketplace home: operational listing discovery only."""
from __future__ import annotations

from ui.legacy_core import *  # noqa: F403,F401
from services.marketplace_service import MarketplaceService


def render_home() -> None:
    catalog = MarketplaceService(marketplace)
    st.markdown(
        """
        <section class="shipp-hero">
          <div class="shipp-eyebrow">SHIPP · Community marketplace</div>
          <h1>Useful things deserve another home.</h1>
          <p>Browse household items shared by donors. Explore what's listed,
          or describe what you need to find relevant matches.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    explore_col, give_col, spacer = st.columns([1, 1, 2])
    with explore_col:
        if st.button("Explore items", key="home_explore", type="primary", use_container_width=True):
            st.switch_page("ui/pages/marketplace.py")
    with give_col:
        if st.button("Give an item", key="home_donate", use_container_width=True):
            st.switch_page("ui/pages/donate.py")

    st.markdown("## Recently listed items")
    st.caption("Current non-expired donor listings. Personalized matching is available under Find an item.")
    try:
        listings = catalog.list_available_listings(limit=6)
    except Exception:
        st.error("The catalog is temporarily unavailable. Please try again.")
        return
    render_listing_gallery(
        listings,
        empty_message="No items are listed right now. Check back later.",
        key_prefix="home",
    )


render_home()

"""Auto-extracted from the original SHIPP app; review before deployment."""
from __future__ import annotations
from ui.legacy_core import *  # noqa: F403,F401 — original dependencies
from services.marketplace_service import MarketplaceService

def render_home() -> None:
    catalog = MarketplaceService(marketplace)
    st.markdown(
        """
        <section class="shipp-hero">
          <div class="shipp-eyebrow">AI-assisted household marketplace</div>
          <h1>Give useful household items a second life.</h1>
          <p>Explore real household items offered by donors. For request-specific
          recommendations, use Find an item and SHIPP's trusted matching engine.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("## Recently available items")
    st.caption("Live, non-expired donor listings from Lakebase. These are not personalized matches.")
    try:
        listings = catalog.list_available_listings(limit=6)
    except Exception:
        st.error("The marketplace catalog is temporarily unavailable.")
        return
    render_listing_gallery(
        listings,
        empty_message="No available donor items yet. Check back after the next donation.",
        key_prefix="home",
    )
    if st.button("Browse all available items", key="home_browse", type="primary"):
        st.switch_page("ui/pages/marketplace.py")
    st.caption("To donate, choose Give an item above. To find recommendations, choose Find an item.")

render_home()

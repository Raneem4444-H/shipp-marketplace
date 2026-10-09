# SHIPP Workstream A — Marketplace navigation and catalog

**Scope:** four native Streamlit top-navigation pages: Home, Explore,
Give an item, Find an item. This deliberately does not add or simulate
password-based login/signup or per-user dashboards; identity and ownership
enforcement are Workstream B.

## Architecture
- Root `app.py` remains the deployed Streamlit entry point.
- Existing donor listing/photo publishing, requester creation, Gold matching,
  Agent recommendation, user-approved save, and diagnostic expander are
  preserved inside `render_donor()` and `render_requester()`.
- Home and Explore perform read-only operational queries through
  `MarketplaceRepo.list_available_listings`, not direct Gold writes.
- Explore filters category, condition and title/description **in Lakebase**
  using SQL parameters. Pagination is deterministic by
  `created_at DESC, listing_id DESC`, nine records per page, plus one
  extra row to detect the next page.
- Search/product browsing does not bypass request-specific Gold eligibility:
  users still use Find an item for matches and the Agent.
- Current profiles are **demo selectors** only and must not be treated as
  verified login. Do not expose this demo to untrusted public users.

## Regression checks
```bash
PYTHONPATH="$PWD:$PWD/agent/agent_ship/src:$PWD/agent/agent_ship/tests/unit/agent" \
  python -m pytest -q test/unit/test_marketplace_navigation.py \
    test/unit/test_marketplace_catalog.py
```

Run the full `pytest` and repo GitHub Actions checks before merging.
Do not alter production `main` or the deployed App from this branch.

## Manual review / Databricks smoke test (after review, before rollout)
1. Confirm `Home`, `Explore`, `Give an item`, `Find an item` in top navbar.
2. Home displays up to six available donor listings from Lakebase, not hardcoded mock data.
3. Explore searches across server-side data; category/condition filters and Next/Previous
   work without repeating rows. Test at least two pages when enough data exist.
4. Donor page still publishes a listing and uploads photos; Lakebase readback works.
5. Requester page still creates requests, displays Gold matches and invokes Agent
   READ → review → explicit SAVE; saved-state refresh and audit continue to work.
6. Confirm the App is using root `app.py` and `app.yaml`.
7. Only after these checks, plan a controlled deployment and rollback to prior SHA.

**Known limits:** Catalog browsing is bounded by a 100-row max per query but
pagination can traverse all available listings. This is not a public,
authenticated consumer site; security work must be completed separately.

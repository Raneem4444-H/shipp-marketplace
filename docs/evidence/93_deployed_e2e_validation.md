# SHIPP Task 93 — Deployed End-to-End Evidence

Task 92 validates persisted pipeline products. Task 93 closes the proof that must happen through the **deployed Databricks App and final runtime environment**.

## What Task 93 proves

| Requirement | Evidence source | PASS condition |
|---|---|---|
| Deployed Databricks App works | App Deployment & permissions evidence panel | App loads and runtime evidence query completes |
| App service principal has Lakebase permissions | Same App panel | Schema USAGE + every required table privilege = PASS |
| Live donor creates Listing in deployed UI | App publish flow + Task 93 | App readback confirms ID; same ID reaches Bronze/Silver/Search |
| Live requester creates Request in deployed UI | App create-request flow + Task 93 | App readback confirms ID; same ID reaches Bronze/Silver/Gold |
| Agent READ works from deployed App | App tool trace + lb_agent_activity_history | candidate read + semantic read + listing-status read are audited |
| Agent WRITE succeeds from deployed App | App save result + Task 93 | returned saved_item_id reaches saved-items CDC and save SUCCESS is audited |
| Saved state refreshes in App | App immediate readback after save | saved_state_refresh = PASS |
| Velocity <60 seconds | 09_validate_velocity.ipynb + Task 93 | selected App-created ID has slo_met = true |
| ORS failure/retry behavior | 20_validate_ors_failure_retry.ipynb | deterministic 429 retry + network failure exhaustion PASS |
| Unavailable Listing rejection | deployed App + Agent audit | REJECTED_UNAVAILABLE recorded |
| Duplicate save rejection | deployed App + Agent audit | second save produces REJECTED_DUPLICATE |

## Final validation sequence

### Gate A — Deploy and prove runtime identity

Deploy the branch. Open the App and expand **Deployment & permissions evidence**.

Capture a screenshot showing **PASS — Lakebase runtime identity and required grants**.

If a privilege is FAIL, grant only the missing privilege to the displayed current_user, then retry.

### Gate B — Donor creates a real Listing

From **Give an item**, upload photo(s), enter title/category/condition/location/description/availability, and publish.

PASS requires:
- App says Lakebase confirmed the Listing;
- the new Listing is rendered with its photo and description;
- copy the displayed listing_id.

The donor view now also shows existing Listings under **Your live listings**.

### Gate C — Requester creates a real Request

From **Find an item**, create a Request and copy the request_id. PASS requires Lakebase readback confirmation.

### Gate D — Process the new IDs

Run Task 90, then Task 91. Do not create replacement test data.

### Gate E — Agent READ from the deployed App

Open the new Request and use **Ask SHIPP** and **Review for save**.

Capture the Agent trace. It should exercise trusted reads such as get_candidate_matches, search_listing_context, and get_listing_status.

### Gate F — Agent WRITE + saved-state refresh

Confirm **Save this item**.

PASS requires:
- saved_item_id returned;
- App immediately re-reads Lakebase;
- saved_state_refresh = PASS;
- Saved drawer shows the item.

Copy the saved_item_id.

### Gate G — Duplicate rejection

Use the same Request and Listing and save again.

PASS requires REJECTED_DUPLICATE and no second saved_items row.

### Gate H — Unavailable rejection

Use a controlled stale-candidate test in the same final environment:
1. pick an unsaved Listing currently present in Gold for the Request;
2. change only its Lakebase operational status to a non-AVAILABLE state for the validation fixture;
3. do not refresh Gold before the save attempt;
4. try to save it from the deployed App.

PASS requires REJECTED_UNAVAILABLE with no saved row. Record this Listing ID as unavailable_listing_id.

### Gate I — ORS retry/failure

Run notebooks/validation/20_validate_ors_failure_retry.ipynb.

It uses the production ORSClient with deterministic fake HTTP/network responses and validates retry, Retry-After, retry exhaustion, preserved error evidence, and no API-key leakage.

### Gate J — Velocity

Run notebooks/validation/09_validate_velocity.ipynb for the App-created Listing or Request.

For stronger evidence keep the notebook target of five controlled measurements; Task 93 requires at least one selected App-created ID with a measured sub-60-second result.

### Gate K — Task 93

Run notebooks/pipeline/93_deployed_e2e_validation.ipynb with:
- listing_id
- request_id
- saved_item_id
- unavailable_listing_id

PASS result: **PASS — deployed SHIPP vertical slice validated end to end.**

Evidence is appended to bootcamp_students.shipp_gold.deployed_e2e_validation_log.

## Donor Listing storage and display contract

Donor Listing text and description remain in Lakebase shipp.listings.

Image binaries remain in the Unity Catalog Volume; Lakebase shipp.listing_files stores only file references.

The App now displays donor Listings with real photos and descriptions in both the donor **Your live listings** section and requester **Marketplace** section.

Requester discovery does not replace trusted matching: request-specific recommendation eligibility and ranking still come from Gold.
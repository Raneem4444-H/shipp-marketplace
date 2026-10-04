# SHIPP Final Demo Script

Target duration: 5–7 minutes.

## 1. Business problem

SHIPP connects available household items with requester needs and demonstrates a complete Data Engineering + AI workflow.

## 2. Operational truth

Show Lakebase as the system of record for listings, requests, saved items, and Agent activity.

## 3. Incremental pipeline

Show one operational change flowing through CDC/Bronze and trusted Silver current state.

## 4. Routing and Gold

Show OpenRouteService enrichment and `gold_candidate_matches`. Explain that Gold v1 uses the frozen structured score while hard eligibility rules exclude invalid pairs.

## 5. Variety / AI Search

Show representative image/text-derived listing content, the Gold search document, and a semantic AI Search result with a traceable `listing_id`.

## 6. Deployed App + Agent READ

Open the Databricks App, use the final demo user/request, and ask for the best available match.

Show the tool trace:
Gold → AI Search → Lakebase status → grounded recommendation.

## 7. Approved Agent WRITE

Click Save only after the recommendation is shown.

Record the returned `saved_item_id`.

## 8. Database confirmation

Show the new row directly in `shipp.saved_items` and the matching SUCCESS row in `shipp.agent_activity`.

## 9. CDC + Analytics feedback

Show the new Saved Item and Agent Activity CDC events, then show the updated `gold_marketplace_metrics` row.

## 10. App feedback

Refresh/continue the App and show that the item remains in the saved state based on Lakebase.

## 11. Big Data evidence

Show Variety evidence and the real Velocity measurement:

`retrieval_available_at - operational_change_at`.

## 12. Close

Summarize:

```text
Business Event
→ Lakebase
→ CDC
→ Bronze
→ Silver
→ ORS / Unstructured
→ Gold
→ AI Search
→ Agent
→ approved write
→ Lakebase
→ CDC / Analytics / App feedback
```

State limitations clearly: no Volume claim, no payments, no shipping workflow, no second Agent write required for P0.

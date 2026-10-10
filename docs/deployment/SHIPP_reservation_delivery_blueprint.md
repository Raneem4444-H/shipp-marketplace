# SHIPP Reservation and Delivery Blueprint — Design draft (not applied)

## Baseline
Repository main `a5d209b7` (2026-10-09). Existing `shipp.listings`, `shipp.requests`, `shipp.users`, `shipp.user_roles`, `shipp.saved_items` and `shipp.agent_activity` remain untouched. Migration 002 uses listing statuses `DRAFT`, `AVAILABLE`, `UNAVAILABLE`, `WITHDRAWN`, `EXPIRED`. Existing saved items are **bookmarks only**. The SHIPP partner role exists in seed roles, but `app_auth.py` permits only DONOR/REQUESTER self-registration.

## Business decisions / assumptions
- User rule: USD $5.00 for the first 15 minutes, +$2.00 for every *additional started* 15-minute interval. Item itself is donated for $0.
- Proposed pilot policy (requires user/partner approval): exclusive `HELD` reservation for 24 hours; donor must confirm pickup; quotes valid 15 minutes.
- Actual route distance/time must come from ORS, with input pickup and dropoff coordinates validated and snapshotted. The current ORS Matrix code asks for `units="km"`: distances are kilometers, durations are seconds; store meters via `round(distance_km * 1000)` and round duration seconds **up** before fee calculation. Do not price using Silver `duration_min`, which is rounded to one decimal place. Treat minutes as an estimate; require requester approval of price. A change in pickup/destination requires a fresh quote.
- A delivery company is an organization with approved dispatchers/drivers, rather than allowing any requester to self-select SHIPPING_PARTNER.
- Payment-provider sandbox for prototype. No real paid order or live GPS tracking may be claimed without the actual provider integration, verified webhooks, and courier API/driver application.

## Pricing V1
`duration_seconds` comes from ORS and is rounded **up to the next whole second**. Extra charged intervals = `(max(duration_seconds - 900, 0) + 899) // 900`; total cents = `500 + 200 * intervals`. At 900 sec: 500; 901 sec: 700; 1800 sec: 700; 1801 sec: 900. Money in integer USD cents.

## Reservation state machine
- NONE -> HELD (verified requester, `OPEN`/`MATCHES_AVAILABLE` owned request (decide whether `ITEM_SAVED` remains eligible for multiple items), distinct donor, AVAILABLE unexpired listing, atomic exclusivity check)
- HELD -> CONFIRMED (donor explicitly approves pickup; only before hold expiry)
- HELD -> DECLINED (donor rejects); HELD -> EXPIRED (expiry job or lazy cleanup); HELD -> CANCELLED (requester/admin cancellation)
- CONFIRMED -> CANCELLED (business-policy cancellation before pickup, coordinate refunds as needed)
- CONFIRMED -> COMPLETED (only after confirmed delivery receipt)
- Final states immutable for purposes of new reservation eligibility. Any new reservation for same item additionally requires `listings.status='AVAILABLE'` and the donated item not previously completed.
- `HELD` or `CONFIRMED` is exclusively protected by a PostgreSQL partial UNIQUE index, not only a UI button.

## Shipment state machine
`READY_FOR_DISPATCH -> ASSIGNED -> PICKUP_SCHEDULED -> PICKED_UP -> IN_TRANSIT -> DELIVERED -> COMPLETED`.
Exception branches: cancellation/refund before pickup; failure or dispute after pickup. Driver reports delivered; requester confirms receipt, which makes shipment and reservation completed. Append shipment_events within the same DB transaction as each valid state transition. Also append reservation_events in the reservation transition transaction.

## Payment state machine
`CREATED -> PENDING -> AUTHORIZED -> PAID`; failures -> FAILED/CANCELLED; paid cancellation -> REFUND_PENDING -> REFUNDED as provider confirms. Backend creates a payment session only after donor confirmation and accepted unexpired quote. Do not trust a success redirect; verify signed webhooks and deduplicate provider event IDs. Never store PAN/CVV/card details.

## Consistency
- Lock `shipp.listings` row `FOR UPDATE` on reservation, revalidate `status='AVAILABLE'` and expiry. Confirm request owner in trusted code. In the same transaction mark stale `HELD` rows `EXPIRED`, then INSERT new reservation; the partial unique index ensures at most one HELD/CONFIRMED reservation. Do not hold locks during ORS HTTP calls.
- Keep `listings.status` unchanged during a temporary hold to avoid abusing `UNAVAILABLE`. **Every listing read path** (Home, Explore, Agent availability check and reserve backend) must exclude active `HELD`/`CONFIRMED` reservations; do not advertise a `HELD` item as claimable until the expiry job or lazy cleanup has transitioned it to `EXPIRED`. On completion set listing to `UNAVAILABLE` so donated item cannot be claimed again. Review user-facing state labels and Gold/Vector availability freshness.
- Fail closed if identity unknown, owner/request mismatch, out-of-bounds coordinates, invalid ORS duration, stale quote, revoked courier, inactive partner, or payment status not verified.
- Quote and shipment updates must verify the referencing reservation, payment, requester and partner in the service transaction; the SQL defines some but not all cross-table business dependencies.

## Permissions matrix
- Requester: own request, own reservation, own quote and payment; view shipment milestone/timeline; cancel own hold; confirm own delivery. Never impersonate another requester.
- Donor: manage own item, approve/decline a hold on own listing, see restricted pickup delivery milestones; no access to payment credentials or other requesters' unrelated data.
- Approved dispatcher: see only company-assigned deliveries and update permitted dispatch statuses; set driver belonging to same company.
- Approved driver: see only assigned jobs and update pickup/transit/delivery with appropriate proof; no price editing, no other users' personal data.
- Admin/support: specific, audited elevated actions and refunds. Read-only analytics/CDC service principal separate from transactional app credentials.
- No production reservation from SHIPP's current demo profile dropdown; a verified OIDC identity->profile mapping must be enabled first.

## Source file locations
- `lakebase/migrations/011_reservations_delivery_payments.sql` — approved DB migration (this draft can be saved by the user only after review)
- `services/reservation_service.py` — eligibility and lifecycle authorization
- `services/quote_service.py` — call ORS, price quote and revalidation
- `services/shipment_service.py` — partner assignment and guarded event transitions
- `services/payment_service.py` — provider checkout/webhook and refund state machine
- `app_marketplace.py` or dedicated repository modules — parameterized transactions, no SQL in Streamlit UI
- `ui/legacy_core.py` + `ui/pages/marketplace.py` — Take it and confirmed quote
- `ui/pages/donor_dashboard.py` — donor hold approval and pickup window
- `ui/pages/requester_dashboard.py` — reservations/payment/tracking
- `ui/pages/shipping_dashboard.py` + `ui/components/navbar.py` — approved shipping partner view
- `test/unit` and `test/integration` — tests, including real PostgreSQL concurrency (two sessions)
- `data_pipeline` + Delta/Gold — CDC of reservation/quote/shipment events, metrics

## Implementation gate order
1. Confirm policies and identity gate; inspect live Lakebase constraints and backups.
2. Create migration on a local feature branch. Apply in development DB only; verify DDL, indexes and grants.
3. Implement atomic hold, stale-expiry cleanup, donor approval, cancellation; concurrency test 2 requesters, 1 winner.
4. Update *all* catalog and Agent availability paths. Test reserved listing cannot be shown as claimable.
5. Add Take it UI and My Reservations; verify readback and audit.
6. ORS quote with snapshotted coordinates and exact cents formula; test price boundaries, quote expiry and reprice.
7. Partner membership, dispatch and append-only tracking events; user-role isolation tests.
8. Payment sandbox, webhook signatures/dedup, refunds. Deploy only after app/user authorization and integration tests.
9. CDC/Gold analytics and dashboard; measure actual durations and completion/decline rates.
10. Controlled pilot acceptance: full actor journey, duplicate/concurrent reserve, unavailable item, stale quote, payment failure, driver no-show, cancellation and recovery, security review.

## NOT YET VERIFIED
Exact live Lakebase schema/privileges, current App deployment SHA, provider availability and fees, identity integration, payout terms and courier tracking integration. This draft is an architectural plan, not a tested DB migration.

# SHIPP grading gap closure — evidence reconciliation (2026-10-10)

## Purpose and source boundary

This document identifies the *specific remaining evidence* needed to finish the eight-category 100-point grading rubric. It does not claim a later deployed version is operational. The reviewed GitHub baseline is `f288de79f2413b538dfdc288aeda0d122cd5a98d`; GitHub CI completed successfully for that commit.

The provided Databricks CSV exports are execution evidence **from earlier on October 10**, before the latest `main` merge; repeat final validation after release freeze.

### What existing exports actually prove

- Task 92 `92_release_validation (3).csv`: **39/39 PASS** (run `51fad600-7e39-49e6-8483-c33916ec9018`; checked `2026-10-10T07:00:51.512Z`). Includes 13 Silver requests, 78 Gold matches, 38 Gold listing search documents, 22 Bronze ORS responses, 12 Bronze Vision responses, and one marketplace metrics snapshot.
- Task 93 `93_deployed_e2e_validation (1).csv`: **26/27 PASS**. Listing and request flowed to CDC and Silver; request received Gold candidates; Agent used structured/semantic/status reads; `save_item` reached CDC with audit; duplicate and unavailable attempts were rejected; ORS deterministic failure/retry gate passed.
- The single FAIL was `velocity_under_60_seconds`: **1 recorded run, 0 meeting SLO**, best `279783.489914` seconds (about 77.7 h). This measures event-to-retrieval elapsed time, not necessarily active Spark execution time. The date/time and run metadata must be analyzed before attribution.
- Variety proof exists via actual Vision and search document outputs. **No SHIPP-specific million-row processing evidence is established** by these exports.

## Rubric-linked closure tracker

| Rubric area | Verified existing implementation | Unclosed gate | Closure proof |
| --- | --- | --- | --- |
| Spark (15) | Task 90 Spark transforms and 39/39 previous release checks | Fresh final commit execution | Task 90 + Task 92 PASS, job run ID, record counts |
| External API (10) | ORS Matrix integration; deterministic 429/backoff and failure gate PASS | Fresh live-provider evidence | Real response route ID, Bronze raw/error row, validation notebook |
| Lakebase (15) | Core schema; operational writes; `user_identities` table exists in queried DB | Verified isolated DEV endpoint, PK/FK/unique and signup transaction | Host/branch, read-only catalog evidence, DEV rollback/duplicate tests |
| Agent (20) | Real authorized `save_item`; Task 93 write/CDC/audit and reject evidence PASS | Final deployed workflow on approved SHA | Request/listing/saved IDs + tool trace + activity + Lakebase readback |
| Analytics (10) | CDC-driven Gold metrics and prior release checks | Fresh change → metrics and idempotent rerun | Before/after counts, source LSN, job run, unchanged rerun |
| Frontend (10) | Streamlit navigation, Donor/Requester, confirmation and Agent interaction | True signup and deployment-matched role/ownership flow | Two-user verified identities, unauthorized rejection, records |
| Deployed app (5) | Previously running App, runtime evidence panels exist | Exact latest SHA + resource grants + smoke flow | CLI/App version, service principal privileges, screenshots |
| Big Data (15) | Variety: structured data + actual unstructured Vision/search | Second V (Velocity or Volume) | NEW event with sub-60s end-to-end retrieval **or** genuine SHIPP million-row distributed workload |

## Minimal execution order

1. Freeze approved commit and check whether the stale PR #53 could overwrite later improvements. No blanket cherry-picks, resets or deployments.
2. Run read-only Lakebase endpoint, constraints, role, identity and grant checks on the **confirmed DEV branch**. Database name/user alone is not proof of DEV.
3. Finish identity-backed signup without passwords; use `(provider, issuer, subject)` from verified server authentication and insert `users`, `user_roles`, `user_identities` in one DB transaction. Confirm duplicate rejection and rollback. Never select an existing profile via an untrusted browser ID.
4. Test donor/requester pin confirmation in DEV, followed by App donation, request, Agent candidate/semantic/status reads and `confirm_save` with one controlled pair.
5. Run Task 90 → 91 → 92 on the frozen commit, plus ORS retry/failure checks and CDC-to-Gold metrics. Preserve run IDs and screenshots.
6. Diagnose Velocity with `velocity_root_cause_read_only.sql`, then measure a **fresh eligible business event** using the canonical `09_validate_velocity.ipynb` without weakening any thresholds.
7. Complete Task 93 on the exact deployed release. Save full 27-check result and final run ID. A prior 26/27 run does not prove the new release passes.
8. Commit evidence references, job IDs, deployed URL+revision and readable demo transcript. Do not store API keys, tokens, passwords or precise private addresses.

## Scope boundary

The grading rubric **requires an action-taking Agent**, but not a general shipping/payment platform. The present Agent writes a user-confirmed saved recommendation, so the 60-point read-only-Agent cap does not apply. Reservation/Take it approval/cancellation should be built if the agreed product MVP requires it, but is not a substitute for completing the scored Agent vertical slice or Big Data two-V demonstration.

**Status convention:** `DONE` requires reproducible test/runtime evidence on the claimed revision; `IMPLEMENTED` means code exists; `BLOCKED` means an external precondition prevents safe validation; `MISSING` means required code absent; `DOCUMENTED` means only a plan.

"""In-memory stand-ins for Gold, AI Search, Lakebase and the chat model."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from shipp.agent.config import AgentSettings
from shipp.agent.contracts import (
    ActionStatus,
    CandidateMatch,
    ListingState,
    RequestState,
    SaveResult,
    SearchHit,
)
from shipp.agent.rules import check_listing_saveable, check_request_usable

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
FUTURE = datetime.now(timezone.utc) + timedelta(days=30)


def settings(**overrides: Any) -> AgentSettings:
    base = dict(
        llm_endpoint="test-endpoint",
        sql_warehouse_id="wh",
        candidate_matches_table="shipp.gold.gold_candidate_matches",
        search_index="shipp.gold.gold_listing_search_docs_index",
        lakebase_schema="bootcamp_shipp",
        max_tool_rounds=4,
    )
    base.update(overrides)
    return AgentSettings(**base)


def match(listing_id: str, score: float = 0.9, distance: float | None = 6.4) -> CandidateMatch:
    return CandidateMatch(
        request_id="req-1",
        listing_id=listing_id,
        title=f"Item {listing_id}",
        category="furniture",
        condition="good",
        area="Al Reem Island",
        match_score=score,
        distance_km=distance,
        duration_min=14.0 if distance is not None else None,
        available_until=None,
        computed_at=None,
    )


class FakeGold:
    def __init__(self, matches: list[CandidateMatch] | None = None, fail: bool = False) -> None:
        self.matches = matches or []
        self.fail = fail

    def get_candidate_matches(self, request_id, *, limit, min_score):
        if self.fail:
            raise RuntimeError("warehouse down")
        return [m for m in self.matches if m.match_score >= min_score][:limit]

    def is_candidate(self, request_id, listing_id):
        return any(m.listing_id == listing_id for m in self.matches)


class FakeSearch:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(self, query, *, listing_ids, k):
        self.calls.append({"query": query, "listing_ids": list(listing_ids), "k": k})
        return [
            SearchHit(lid, f"Item {lid}", "furniture", "good", "solid wood, 120cm", 0.8)
            for lid in listing_ids
        ][:k]


class FakeLakebase:
    """Implements the LakebaseRepo surface the agent uses, in memory."""

    def __init__(self) -> None:
        self.listings: dict[str, ListingState] = {}
        self.requests: dict[str, RequestState] = {
            "req-1": RequestState("req-1", "user-1", "open")
        }
        self.saved: set[tuple[str, str, str]] = set()
        self.activity: list[tuple[str, str, str | None, ActionStatus]] = []

    def add_listing(self, listing_id: str, status: str = "available", until=None) -> None:
        self.listings[listing_id] = ListingState(listing_id, status, until or FUTURE)

    def get_listing(self, listing_id):
        return self.listings.get(listing_id)

    def get_request(self, request_id):
        return self.requests.get(request_id)

    def log_activity(self, user_id, tool_name, entity_id, status):
        self.activity.append((user_id, tool_name, entity_id, status))
        return True

    def save_item(self, *, user_id, request_id, listing_id, now=None):
        now = now or datetime.now(timezone.utc)
        reason = check_request_usable(self.requests.get(request_id), user_id) or (
            check_listing_saveable(self.listings.get(listing_id), now)
        )
        if reason:
            self.log_activity(user_id, "save_item", listing_id, ActionStatus.REJECTED)
            return SaveResult(ActionStatus.REJECTED, reason)
        key = (user_id, request_id, listing_id)
        if key in self.saved:
            self.log_activity(user_id, "save_item", listing_id, ActionStatus.DUPLICATE)
            return SaveResult(ActionStatus.DUPLICATE, "dup")
        self.saved.add(key)
        self.log_activity(user_id, "save_item", listing_id, ActionStatus.SUCCESS)
        return SaveResult(ActionStatus.SUCCESS, "Item saved.", "saved-1")


class ScriptedModel:
    """Returns pre-written assistant messages in order and records what it saw."""

    def __init__(self, script: list[dict[str, Any]]) -> None:
        self.script = list(script)
        self.seen: list[list[dict[str, Any]]] = []

    def complete(self, messages, tools):
        self.seen.append(list(messages))
        if not self.script:
            raise AssertionError("ScriptedModel ran out of replies")
        return self.script.pop(0)


def tool_call(name: str, call_id: str = "c1", **args: Any) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ],
    }


def text(content: str) -> dict[str, Any]:
    return {"role": "assistant", "content": content}

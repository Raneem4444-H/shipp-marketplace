"""Regression tests for deterministic, user-confirmed SHIPP save reviews."""

from agent_fakes import (
    FakeGold,
    FakeLakebase,
    FakeSearch,
    ScriptedModel,
    match,
    settings,
)
from shipp.agent.agent import ShippAgent
from shipp.agent.contracts import ActionStatus


def build_agent():
    lake = FakeLakebase()
    lake.add_listing("l1")
    model = ScriptedModel([])
    agent = ShippAgent(
        settings(),
        model,
        FakeGold([match("l1")]),
        FakeSearch(),
        lake,
    )
    return agent, lake, model


def test_review_creates_proposal_without_model_or_write():
    agent, lake, model = build_agent()
    review = agent.review_for_save(
        user_id="user-1", request_id="req-1", listing_id="l1"
    )
    assert review.pending_save is not None
    assert review.pending_save.listing_id == "l1"
    assert [t["tool"] for t in review.tool_trace] == [
        "get_candidate_matches",
        "get_listing_status",
        "search_listing_context",
        "propose_save",
    ]
    assert review.tool_trace[-1]["result"]["proposal_created"] is True
    assert model.seen == []
    assert lake.saved == set()
    assert any(
        row[1] == "propose_save" and row[3] is ActionStatus.SUCCESS
        for row in lake.activity
    )


def test_review_rejects_non_candidate_without_write():
    agent, lake, model = build_agent()
    review = agent.review_for_save(
        user_id="user-1", request_id="req-1", listing_id="fake-id"
    )
    assert review.pending_save is None
    assert len(review.tool_trace) == 1
    assert model.seen == []
    assert lake.saved == set()


def test_review_rejects_unavailable_without_write():
    agent, lake, model = build_agent()
    lake.add_listing("l1", status="withdrawn")
    review = agent.review_for_save(
        user_id="user-1", request_id="req-1", listing_id="l1"
    )
    assert review.pending_save is None
    assert [t["tool"] for t in review.tool_trace] == [
        "get_candidate_matches",
        "get_listing_status",
    ]
    assert lake.saved == set()
    assert model.seen == []


def test_review_rejects_request_owned_by_other_user():
    agent, lake, model = build_agent()
    review = agent.review_for_save(
        user_id="intruder", request_id="req-1", listing_id="l1"
    )
    assert review.pending_save is None
    assert review.tool_trace == []
    assert lake.saved == set()
    assert model.seen == []


def test_review_semantic_failure_never_proposes():
    agent, lake, _ = build_agent()

    def fail_search(query, *, listing_ids, k):
        raise RuntimeError("AI Search temporarily unavailable")

    agent._search.search = fail_search
    review = agent.review_for_save(
        user_id="user-1", request_id="req-1", listing_id="l1"
    )
    assert review.pending_save is None
    assert review.tool_trace[-1]["tool"] == "search_listing_context"
    assert "error" in review.tool_trace[-1]["result"]
    assert lake.saved == set()

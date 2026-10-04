import json

from agent_fakes import (
    FakeGold,
    FakeLakebase,
    FakeSearch,
    ScriptedModel,
    match,
    settings,
    text,
    tool_call,
)
from shipp.agent.agent import FALLBACK_REPLY, ShippAgent
from shipp.agent.contracts import ActionStatus
from shipp.agent.tools import ToolBox, ToolContext

CTX = ToolContext(user_id="user-1", request_id="req-1")


def make_toolbox(matches=None, fail_gold=False):
    lake = FakeLakebase()
    for m in matches or []:
        lake.add_listing(m.listing_id)
    search = FakeSearch()
    box = ToolBox(CTX, settings(), FakeGold(matches, fail=fail_gold), search, lake)
    return box, lake, search


def make_agent(script, matches=None):
    lake = FakeLakebase()
    for m in matches or []:
        lake.add_listing(m.listing_id)
    model = ScriptedModel(script)
    agent = ShippAgent(settings(), model, FakeGold(matches), FakeSearch(), lake)
    return agent, model, lake


# ---------------------------------------------------------------- toolbox
def test_no_candidates_tells_model_to_recommend_nothing():
    box, lake, _ = make_toolbox([])
    out = box.dispatch("get_candidate_matches", "{}")
    assert out["matches"] == []
    assert "Recommend nothing" in out["note"]
    assert lake.activity[-1][1:] == ("get_candidate_matches", "req-1", ActionStatus.SUCCESS)


def test_status_check_on_non_candidate_is_rejected_and_logged():
    box, lake, _ = make_toolbox([match("l1")])
    out = box.dispatch("get_listing_status", json.dumps({"listing_id": "made-up"}))
    assert "error" in out
    assert lake.activity[-1][3] is ActionStatus.REJECTED_NOT_A_MATCH


def test_search_is_restricted_to_candidate_ids():
    box, _, search = make_toolbox([match("l1"), match("l2", 0.8)])
    box.dispatch("search_listing_context", json.dumps({"query": "wooden desk"}))
    assert search.calls[0]["listing_ids"] == ["l1", "l2"]


def test_propose_save_creates_pending_proposal_without_writing():
    box, lake, _ = make_toolbox([match("l1")])
    out = box.dispatch("propose_save", json.dumps({"listing_id": "l1", "reason": "fits"}))
    assert out["proposal_created"] is True
    assert box.pending_save.listing_id == "l1"
    assert lake.saved == set()


def test_propose_save_on_withdrawn_listing_is_rejected():
    box, lake, _ = make_toolbox([match("l1")])
    lake.add_listing("l1", status="withdrawn")
    out = box.dispatch("propose_save", json.dumps({"listing_id": "l1", "reason": "fits"}))
    assert out["proposal_created"] is False
    assert box.pending_save is None


def test_bad_json_and_unknown_tool_do_not_raise():
    box, _, _ = make_toolbox([match("l1")])
    assert "error" in box.dispatch("get_listing_status", "{not json")
    assert "error" in box.dispatch("delete_everything", "{}")
    assert "error" in box.dispatch("get_listing_status", json.dumps({"user_id": "x"}))


def test_backend_failure_returns_safe_error_and_logs_failed():
    box, lake, _ = make_toolbox([match("l1")], fail_gold=True)
    out = box.dispatch("get_candidate_matches", "{}")
    assert "error" in out
    assert lake.activity[-1][3] is ActionStatus.ERROR


# ---------------------------------------------------------------- agent loop
def test_agent_calls_tools_then_answers():
    agent, model, _ = make_agent(
        [tool_call("get_candidate_matches"), text("The Item l1 is your best match.")],
        matches=[match("l1")],
    )
    turn = agent.chat(user_id="user-1", request_id="req-1", user_message="desk?")
    assert turn.reply == "The Item l1 is your best match."
    assert [t["tool"] for t in turn.tool_trace] == ["get_candidate_matches"]
    tool_msg = model.seen[1][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c1"


def test_agent_refuses_other_users_request_without_calling_model():
    agent, model, _ = make_agent([text("should not be used")])
    turn = agent.chat(user_id="intruder", request_id="req-1", user_message="hi")
    assert "does not exist" in turn.reply
    assert model.seen == []


def test_agent_stops_after_max_rounds():
    loop = [tool_call("get_candidate_matches", call_id=f"c{i}") for i in range(10)]
    agent, _, _ = make_agent(loop, matches=[match("l1")])
    turn = agent.chat(user_id="user-1", request_id="req-1", user_message="desk?")
    assert turn.reply == FALLBACK_REPLY
    assert len(turn.tool_trace) == 4


def test_agent_surfaces_pending_save():
    agent, _, lake = make_agent(
        [
            tool_call("propose_save", listing_id="l1", reason="right size"),
            text("I've set it up. Please confirm to save it."),
        ],
        matches=[match("l1")],
    )
    turn = agent.chat(user_id="user-1", request_id="req-1", user_message="save the desk")
    assert turn.pending_save is not None and turn.pending_save.listing_id == "l1"
    assert lake.saved == set()


# ---------------------------------------------------------------- confirm_save
def test_confirm_save_success_then_duplicate():
    agent, _, lake = make_agent([], matches=[match("l1")])
    first = agent.confirm_save(user_id="user-1", request_id="req-1", listing_id="l1")
    second = agent.confirm_save(user_id="user-1", request_id="req-1", listing_id="l1")
    assert first.ok
    assert second.status is ActionStatus.REJECTED_DUPLICATE
    assert len(lake.saved) == 1


def test_confirm_save_rejects_non_candidate():
    agent, _, lake = make_agent([], matches=[match("l1")])
    lake.add_listing("l9")
    result = agent.confirm_save(user_id="user-1", request_id="req-1", listing_id="l9")
    assert result.status is ActionStatus.REJECTED_NOT_A_MATCH
    assert lake.saved == set()


def test_confirm_save_rejects_listing_withdrawn_after_proposal():
    agent, _, lake = make_agent([], matches=[match("l1")])
    lake.add_listing("l1", status="withdrawn")
    result = agent.confirm_save(user_id="user-1", request_id="req-1", listing_id="l1")
    assert result.status is ActionStatus.REJECTED_UNAVAILABLE

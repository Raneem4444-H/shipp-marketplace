"""Live end-to-end check against a real workspace.

Gated on purpose: this only runs once Gold passes its DoD and a seeded request
exists. Enable with:
    SHIPP_RUN_INTEGRATION=1 SHIPP_TEST_USER_ID=... SHIPP_TEST_REQUEST_ID=... pytest tests/integration
It performs reads only; it never calls confirm_save.
"""

import os
import time

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("SHIPP_RUN_INTEGRATION") != "1",
    reason="Integration disabled until Gold DoD passes (set SHIPP_RUN_INTEGRATION=1).",
)


def test_agent_answers_from_real_gold_and_search():
    from shipp.agent import ShippAgent

    agent = ShippAgent.from_env()
    started = time.monotonic()
    turn = agent.chat(
        user_id=os.environ["SHIPP_TEST_USER_ID"],
        request_id=os.environ["SHIPP_TEST_REQUEST_ID"],
        user_message="Which item fits my request best, and is it still available?",
    )
    elapsed = time.monotonic() - started

    tools_used = [t["tool"] for t in turn.tool_trace]
    assert "get_candidate_matches" in tools_used
    assert turn.reply.strip()
    assert not any("error" in t["result"] for t in turn.tool_trace), turn.tool_trace
    print(f"agent latency: {elapsed:.1f}s, tools: {tools_used}")

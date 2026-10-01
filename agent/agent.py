"""The Shipp agent: a bounded tool-calling loop plus a user-confirmed write.

Flow for one user message:
    authorize(user, request) -> model <-> tools (max N rounds) -> reply
    (+ optional SaveProposal for the app to show as a confirm button)

The model never writes to Lakebase. When the user clicks confirm, the app
calls confirm_save(), which re-checks everything against current state.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from shipp.agent.config import AgentSettings
from shipp.agent.contracts import ActionStatus, SaveProposal, SaveResult
from shipp.agent.lakebase import SAVE_TOOL_NAME, LakebaseRepo
from shipp.agent.llm import ChatModel
from shipp.agent.prompts import SYSTEM_PROMPT
from shipp.agent.rules import check_request_usable
from shipp.agent.tools import TOOL_SPECS, GoldPort, SearchPort, ToolBox, ToolContext

logger = logging.getLogger(__name__)

FALLBACK_REPLY = (
    "I couldn't finish checking the matches for this request. Please try again in a moment."
)


@dataclass
class AgentTurn:
    reply: str
    pending_save: SaveProposal | None = None
    tool_trace: list[dict[str, Any]] = field(default_factory=list)


class ShippAgent:
    def __init__(
        self,
        settings: AgentSettings,
        model: ChatModel,
        gold: GoldPort,
        search: SearchPort,
        lakebase: LakebaseRepo,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        self._settings = settings
        self._model = model
        self._gold = gold
        self._search = search
        self._lakebase = lakebase
        self._system_prompt = system_prompt

    @classmethod
    def from_env(cls) -> ShippAgent:
        from shipp.agent.clients import build_lakebase_connect, build_workspace_client
        from shipp.agent.gold import GoldReader
        from shipp.agent.llm import DatabricksChatModel
        from shipp.agent.search import ListingSearch

        settings = AgentSettings.from_env()
        w = build_workspace_client()
        return cls(
            settings=settings,
            model=DatabricksChatModel(settings.llm_endpoint, w),
            gold=GoldReader(w, settings.sql_warehouse_id, settings.candidate_matches_table),
            search=ListingSearch(w, settings.search_index),
            lakebase=LakebaseRepo(build_lakebase_connect(settings, w), settings.lakebase_schema),
        )

    # ------------------------------------------------------------------ chat
    def chat(
        self,
        *,
        user_id: str,
        request_id: str,
        user_message: str,
        history: list[dict[str, str]] | None = None,
    ) -> AgentTurn:
        """Answer one user message about one request.

        `user_id` must come from the app's authenticated session, never from
        user input. `history` holds prior {"role": "user"|"assistant", "content"} turns.
        """
        refusal = check_request_usable(self._lakebase.get_request(request_id), user_id)
        if refusal is not None:
            return AgentTurn(reply=refusal)

        toolbox = ToolBox(
            ToolContext(user_id=user_id, request_id=request_id),
            self._settings,
            self._gold,
            self._search,
            self._lakebase,
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            *[m for m in (history or []) if m.get("role") in ("user", "assistant")],
            {"role": "user", "content": user_message},
        ]
        trace: list[dict[str, Any]] = []

        for _ in range(self._settings.max_tool_rounds):
            try:
                reply = self._model.complete(messages, TOOL_SPECS)
            except Exception:
                logger.exception("Model call failed")
                return AgentTurn(FALLBACK_REPLY, toolbox.pending_save, trace)

            messages.append(reply)
            calls = reply.get("tool_calls") or []
            if not calls:
                return AgentTurn(reply.get("content") or "", toolbox.pending_save, trace)

            for call in calls:
                fn = call["function"]
                result = toolbox.dispatch(fn["name"], fn.get("arguments"))
                trace.append(
                    {"tool": fn["name"], "arguments": fn.get("arguments"), "result": result}
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(result, default=str),
                    }
                )

        logger.warning("Agent hit max_tool_rounds for request %s", request_id)
        return AgentTurn(FALLBACK_REPLY, toolbox.pending_save, trace)

    # ------------------------------------------------------------------ write
    def confirm_save(self, *, user_id: str, request_id: str, listing_id: str) -> SaveResult:
        """Perform the save after the user clicks confirm. Re-validates from scratch."""
        try:
            is_candidate = self._gold.is_candidate(request_id, listing_id)
        except Exception:
            logger.exception("Candidate check failed")
            self._lakebase.log_activity(user_id, SAVE_TOOL_NAME, listing_id, ActionStatus.FAILED)
            return SaveResult(
                ActionStatus.FAILED, "Couldn't verify this match right now. Nothing was saved."
            )
        if not is_candidate:
            self._lakebase.log_activity(user_id, SAVE_TOOL_NAME, listing_id, ActionStatus.REJECTED)
            return SaveResult(
                ActionStatus.REJECTED, "This item is not a match for your request."
            )
        return self._lakebase.save_item(
            user_id=user_id, request_id=request_id, listing_id=listing_id
        )

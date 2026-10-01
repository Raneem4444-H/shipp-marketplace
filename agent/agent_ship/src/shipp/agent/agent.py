"""The Shipp agent: a bounded tool-calling loop plus a user-confirmed write.

Flow for one user message:
    authorize(user, request)
        -> model <-> tools (max N rounds)
        -> reply
        -> optional SaveProposal for the app to show as a confirm button

The model never writes directly to Lakebase.

When the user confirms a save in the application, confirm_save() performs
a fresh validation against trusted Gold candidate data and the current
Lakebase operational state before the write is executed.
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
from shipp.agent.tools import (
    TOOL_SPECS,
    GoldPort,
    SearchPort,
    ToolBox,
    ToolContext,
)

logger = logging.getLogger(__name__)

FALLBACK_REPLY = (
    "I couldn't finish checking the matches for this request. "
    "Please try again in a moment."
)


@dataclass
class AgentTurn:
    """Result of one conversational agent turn."""

    reply: str
    pending_save: SaveProposal | None = None
    tool_trace: list[dict[str, Any]] = field(default_factory=list)


class ShippAgent:
    """SHIPP recommendation agent with controlled read tools and confirmed writes."""

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
    def from_env(cls) -> "ShippAgent":
        """Build the production agent using configured Databricks resources."""

        from shipp.agent.clients import (
            build_lakebase_connect,
            build_workspace_client,
        )
        from shipp.agent.gold import GoldReader
        from shipp.agent.llm import DatabricksChatModel
        from shipp.agent.search import ListingSearch

        settings = AgentSettings.from_env()
        workspace = build_workspace_client()

        return cls(
            settings=settings,
            model=DatabricksChatModel(
                settings.llm_endpoint,
                workspace,
            ),
            gold=GoldReader(
                workspace,
                settings.sql_warehouse_id,
                settings.candidate_matches_table,
            ),
            search=ListingSearch(
                workspace,
                settings.search_index,
            ),
            lakebase=LakebaseRepo(
                build_lakebase_connect(settings, workspace),
                settings.lakebase_schema,
            ),
        )

    # ------------------------------------------------------------------
    # CHAT / READ PATH
    # ------------------------------------------------------------------

    def chat(
        self,
        *,
        user_id: str,
        request_id: str,
        user_message: str,
        history: list[dict[str, str]] | None = None,
    ) -> AgentTurn:
        """Answer one user message for one SHIPP request.

        Security boundary:
        - user_id must come from the authenticated app/session.
        - request_id is validated against the current Lakebase request.
        - the model receives tools but does not write directly to Lakebase.

        The model may:
        - retrieve Gold candidate matches,
        - search indexed listing context,
        - check current listing status,
        - propose a save.

        A proposed save remains pending until the user explicitly confirms it.
        """

        request = self._lakebase.get_request(request_id)

        refusal = check_request_usable(
            request,
            user_id,
        )

        if refusal is not None:
            return AgentTurn(reply=refusal)

        toolbox = ToolBox(
            ToolContext(
                user_id=user_id,
                request_id=request_id,
            ),
            self._settings,
            self._gold,
            self._search,
            self._lakebase,
        )

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": self._system_prompt,
            },
            *[
                message
                for message in (history or [])
                if message.get("role") in ("user", "assistant")
            ],
            {
                "role": "user",
                "content": user_message,
            },
        ]

        trace: list[dict[str, Any]] = []

        for _ in range(self._settings.max_tool_rounds):
            try:
                reply = self._model.complete(
                    messages,
                    TOOL_SPECS,
                )

            except Exception:
                logger.exception(
                    "Model call failed for request_id=%s",
                    request_id,
                )

                return AgentTurn(
                    reply=FALLBACK_REPLY,
                    pending_save=toolbox.pending_save,
                    tool_trace=trace,
                )

            messages.append(reply)

            tool_calls = reply.get("tool_calls") or []

            # Model produced a final answer.
            if not tool_calls:
                return AgentTurn(
                    reply=reply.get("content") or "",
                    pending_save=toolbox.pending_save,
                    tool_trace=trace,
                )

            for call in tool_calls:
                function = call.get("function") or {}

                tool_name = function.get("name")
                raw_arguments = function.get("arguments")

                if not tool_name:
                    logger.warning(
                        "Tool call missing function name for request_id=%s",
                        request_id,
                    )
                    continue

                result = toolbox.dispatch(
                    tool_name,
                    raw_arguments,
                )

                trace.append(
                    {
                        "tool": tool_name,
                        "arguments": raw_arguments,
                        "result": result,
                    }
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": json.dumps(
                            result,
                            default=str,
                        ),
                    }
                )

        logger.warning(
            "Agent hit max_tool_rounds for request_id=%s",
            request_id,
        )

        return AgentTurn(
            reply=FALLBACK_REPLY,
            pending_save=toolbox.pending_save,
            tool_trace=trace,
        )

    # ------------------------------------------------------------------
    # CONFIRMED WRITE PATH
    # ------------------------------------------------------------------

    def confirm_save(
        self,
        *,
        user_id: str,
        request_id: str,
        listing_id: str,
    ) -> SaveResult:
        """Perform a confirmed save after explicit user approval.

        The write path deliberately re-validates the candidate before writing.

        Flow:
            user confirms
                -> verify listing is still a Gold candidate
                -> LakebaseRepo.save_item()
                -> LakebaseRepo re-checks operational state
                -> duplicate / availability rules enforced
                -> saved_items write
                -> agent_activity audit
                -> database-confirmed result returned

        The LLM is never treated as the operational source of truth.
        """

        try:
            is_candidate = self._gold.is_candidate(
                request_id,
                listing_id,
            )

        except Exception:
            logger.exception(
                "Candidate validation failed for request_id=%s listing_id=%s",
                request_id,
                listing_id,
            )

            self._lakebase.log_activity(
                user_id,
                SAVE_TOOL_NAME,
                listing_id,
                ActionStatus.ERROR,
            )

            return SaveResult(
                ActionStatus.ERROR,
                "Couldn't verify this match right now. Nothing was saved.",
            )

        if not is_candidate:
            logger.warning(
                "Rejected save because listing is not a Gold candidate: "
                "request_id=%s listing_id=%s",
                request_id,
                listing_id,
            )

            self._lakebase.log_activity(
                user_id,
                SAVE_TOOL_NAME,
                listing_id,
                ActionStatus.REJECTED_NOT_A_MATCH,
            )

            return SaveResult(
                ActionStatus.REJECTED_NOT_A_MATCH,
                "This item is not a match for your request.",
            )

        return self._lakebase.save_item(
            user_id=user_id,
            request_id=request_id,
            listing_id=listing_id,
        )
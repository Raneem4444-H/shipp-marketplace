"""Chat model access through a Databricks Model Serving endpoint.

Databricks serving endpoints speak the OpenAI chat-completions format, and
databricks-sdk hands back an OpenAI client that is already authenticated for
the workspace (requires the `openai` package). Swapping the model means
changing SHIPP_LLM_ENDPOINT, not code.
"""

from __future__ import annotations

from typing import Any, Protocol


class ChatModel(Protocol):
    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Return one assistant message dict, with `tool_calls` when tools are requested."""
        ...


class DatabricksChatModel:
    def __init__(self, endpoint: str, workspace_client: Any, temperature: float = 0.0) -> None:
        self._endpoint = endpoint
        self._client = workspace_client.serving_endpoints.get_open_ai_client()
        self._temperature = temperature

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        resp = self._client.chat.completions.create(
            model=self._endpoint,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=self._temperature,
        )
        msg = resp.choices[0].message
        out: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            out["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments or "{}",
                    },
                }
                for call in msg.tool_calls
            ]
        return out

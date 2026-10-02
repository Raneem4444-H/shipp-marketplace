"""Vision client for a Databricks Model Serving chat endpoint that accepts images.

Same contract as the ORS client:
- never raises on HTTP/network/model failure; returns a VisionResult envelope,
- keeps the raw response text so it can be written to Bronze BEFORE parsing,
- retries only 429/5xx/network errors, honours Retry-After, never logs credentials,
- never invents image attributes: anything unparseable is an error, not a guess.
"""

import base64
import json
import random
import re
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import requests

from config.settings import (
    IMAGE_MIME_TYPES,
    VISION_BACKOFF_BASE_SECONDS,
    VISION_MAX_DESCRIPTION_CHARS,
    VISION_MAX_IMAGE_BYTES,
    VISION_MAX_LABELS,
    VISION_MAX_RETRIES,
    VISION_MAX_TOKENS,
    VISION_PROMPT_VERSION,
    VISION_RETRYABLE_STATUS,
    VISION_TIMEOUT_SECONDS,
)

SYSTEM_PROMPT = (
    "You describe photos of second-hand household items for a marketplace search index. "
    "Describe only what is clearly visible. Never guess brands, prices, owners or locations. "
    "Never transcribe names, phone numbers, emails or addresses, even if visible in the photo."
)
USER_PROMPT = (
    "Describe the main household item in this photo.\n"
    "Return ONLY a JSON object, no markdown, in exactly this shape:\n"
    '{"image_description": "<at most 60 words: item type, material, colour, style, '
    'visible features, visible wear>", "detected_labels": ["<3 to 10 short lowercase labels>"]}\n'
    'If there is no identifiable household item, return {"image_description": null, "detected_labels": []}.'
)

# Bronze contract for bronze_vision_responses (append-only, written only by notebooks/rag/51)
BRONZE_VISION_SCHEMA = (
    "call_id string, called_at timestamp, listing_id string, listing_file_id string, file_path string, "
    "file_sha256 string, file_size_bytes long, mime_type string, vision_endpoint string, "
    "prompt_version string, request_meta_json string, http_status int, response_body string, "
    "error_message string, retryable boolean, attempts int, latency_ms long"
)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass
class VisionResult:
    request_meta_json: str          # endpoint, prompt version, mime, sha — never the image or a token
    http_status: Optional[int]      # None when no HTTP response was received
    response_body: Optional[str]    # raw text exactly as returned
    error_message: Optional[str]    # None on success
    retryable: bool                 # False = do not call again for this file/prompt version
    attempts: int
    latency_ms: int

    @property
    def ok(self) -> bool:
        return self.http_status == 200 and self.error_message is None


def mime_type_for(path: str) -> Optional[str]:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return IMAGE_MIME_TYPES.get(ext)


def build_payload(image_bytes: bytes, mime_type: str) -> dict:
    data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"

    return {
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": USER_PROMPT,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url
                        },
                    },
                ],
            },
        ],

        # Force a valid JSON object from Databricks Model Serving.
        "response_format": {
            "type": "json_object"
        },

        "max_tokens": VISION_MAX_TOKENS,
        "temperature": 0,
    }

def extract_message_text(body: str) -> str:
    """OpenAI-style chat response -> assistant text. Raises ValueError if the shape is wrong."""
    try:
        parsed = json.loads(body)
        content = parsed["choices"][0]["message"]["content"]
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        raise ValueError(f"not a chat completion response ({type(exc).__name__})") from exc
    if isinstance(content, list):  # some endpoints return content parts
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    if not isinstance(content, str) or not content.strip():
        raise ValueError("empty assistant message")
    return content


def _normalize_labels(raw) -> List[str]:
    if not isinstance(raw, list):
        return []
    labels, seen = [], set()
    for item in raw:
        if not isinstance(item, str):
            continue
        label = re.sub(r"\s+", " ", item).strip().lower()
        if 0 < len(label) <= 40 and label not in seen:
            seen.add(label)
            labels.append(label)
    return labels[:VISION_MAX_LABELS]


def parse_vision_output(body: Optional[str]) -> Tuple[Optional[str], List[str], Optional[str]]:
    """Raw endpoint response -> (image_description, detected_labels, error). Never guesses."""
    if not body:
        return None, [], "empty response body"
    try:
        text = _FENCE_RE.sub("", extract_message_text(body).strip())
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end < start:
            return None, [], "model output contains no JSON object"
        obj = json.loads(text[start:end + 1])
    except ValueError as exc:
        return None, [], f"unparseable model output: {str(exc)[:200]}"
    if not isinstance(obj, dict):
        return None, [], "model output JSON is not an object"
    description = obj.get("image_description")
    if not isinstance(description, str) or not description.strip():
        return None, [], "model reported no identifiable item"
    description = re.sub(r"\s+", " ", description).strip()[:VISION_MAX_DESCRIPTION_CHARS]
    return description, _normalize_labels(obj.get("detected_labels")), None


class VisionClient:
    def __init__(
        self,
        endpoint: str,
        host: str,
        auth_headers: Callable[[], Dict[str, str]],
        timeout_seconds: float = VISION_TIMEOUT_SECONDS,
        max_retries: int = VISION_MAX_RETRIES,
        backoff_base_seconds: float = VISION_BACKOFF_BASE_SECONDS,
        retryable_status: Sequence[int] = VISION_RETRYABLE_STATUS,
        session: Optional[requests.Session] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not endpoint or not host:
            raise ValueError("endpoint and host are required")
        self.endpoint = endpoint
        self.url = f"{host.rstrip('/')}/serving-endpoints/{endpoint}/invocations"
        self._auth_headers = auth_headers
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.retryable_status = set(retryable_status)
        self._session = session or requests.Session()
        self._sleep = sleep

    @classmethod
    def from_workspace(cls, endpoint: str, **kwargs) -> "VisionClient":
        """Auth comes from the notebook's identity via the Databricks SDK — no token in code."""
        from databricks.sdk import WorkspaceClient

        cfg = WorkspaceClient().config
        return cls(endpoint, host=cfg.host, auth_headers=cfg.authenticate, **kwargs)

    def __repr__(self) -> str:
        return f"VisionClient(endpoint={self.endpoint!r})"

    def _backoff(self, attempt: int, retry_after: Optional[str]) -> float:
        if retry_after and retry_after.strip().isdigit():
            return float(retry_after)
        return self.backoff_base_seconds * 2 ** (attempt - 1) + random.uniform(0, 0.5)

    def describe_image(self, image_bytes: bytes, mime_type: Optional[str], file_sha256: str = "") -> VisionResult:
        meta = json.dumps({"endpoint": self.endpoint, "prompt_version": VISION_PROMPT_VERSION,
                           "mime_type": mime_type, "file_sha256": file_sha256,
                           "image_bytes": len(image_bytes or b"")})
        # Deterministic input problems: never call the endpoint, never retry.
        if not image_bytes:
            return VisionResult(meta, None, None, "empty image file", False, 0, 0)
        if not mime_type:
            return VisionResult(meta, None, None, "unsupported image type", False, 0, 0)
        if len(image_bytes) > VISION_MAX_IMAGE_BYTES:
            return VisionResult(meta, None, None,
                                f"image too large ({len(image_bytes)} bytes > {VISION_MAX_IMAGE_BYTES})",
                                False, 0, 0)

        payload = json.dumps(build_payload(image_bytes, mime_type))
        started = time.time()
        attempts, status, body, error, retryable = 0, None, None, None, True
        while attempts <= self.max_retries:
            attempts += 1
            retry_after = None
            try:
                headers = {**self._auth_headers(), "Content-Type": "application/json"}
                resp = self._session.post(self.url, data=payload, headers=headers, timeout=self.timeout_seconds)
                status, body = resp.status_code, resp.text
                if status == 200:
                    _, _, error = parse_vision_output(body)
                    retryable = False  # deterministic at temperature 0; bump the prompt version to retry
                    break
                if status not in self.retryable_status:
                    error, retryable = f"non-retryable HTTP {status}", False
                    break
                error = f"HTTP {status}"
                retry_after = resp.headers.get("Retry-After")
            except requests.RequestException as exc:
                status, body = None, None
                error = f"{type(exc).__name__}: {str(exc)[:300]}"
            if attempts <= self.max_retries:
                self._sleep(self._backoff(attempts, retry_after))
        return VisionResult(meta, status, body, error, retryable if error else False,
                            attempts, int((time.time() - started) * 1000))

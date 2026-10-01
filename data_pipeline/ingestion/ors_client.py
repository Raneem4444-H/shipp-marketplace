"""OpenRouteService Matrix client.

Never raises on HTTP/network failure: every call returns a MatrixResult envelope carrying the
raw response text (or the error), so the caller can persist it to Bronze before parsing.
"""

import json
import random
import time
from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Tuple

import requests

from config.settings import (
    ORS_BACKOFF_BASE_SECONDS,
    ORS_MATRIX_BASE,
    ORS_MAX_RETRIES,
    ORS_PROFILE,
    ORS_RETRYABLE_STATUS,
    ORS_TIMEOUT_SECONDS,
)

LatLon = Tuple[float, float]


@dataclass
class MatrixResult:
    request_json: str               # payload sent (never contains the API key)
    http_status: Optional[int]      # None when no HTTP response was received
    response_body: Optional[str]    # raw text exactly as returned
    error_message: Optional[str]    # None on success
    attempts: int
    latency_ms: int

    @property
    def ok(self) -> bool:
        return self.http_status == 200 and self.error_message is None


class ORSClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = ORS_MATRIX_BASE,
        profile: str = ORS_PROFILE,
        timeout_seconds: float = ORS_TIMEOUT_SECONDS,
        max_retries: int = ORS_MAX_RETRIES,
        backoff_base_seconds: float = ORS_BACKOFF_BASE_SECONDS,
        retryable_status: Sequence[int] = ORS_RETRYABLE_STATUS,
        session: Optional[requests.Session] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("ORS API key is required (read it from the Databricks secret scope).")
        self._api_key = api_key
        self.url = base_url.rstrip("/") + "/" + profile
        self.profile = profile
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.retryable_status = set(retryable_status)
        self._session = session or requests.Session()
        self._sleep = sleep

    def __repr__(self) -> str:  # never leak the key in logs
        return f"ORSClient(url={self.url!r})"

    @staticmethod
    def build_many_to_one_payload(origins: Sequence[LatLon], destination: LatLon) -> dict:
        """ORS expects [lon, lat]. Sources = origins, one destination at the last index."""
        if not origins:
            raise ValueError("At least one origin is required.")
        locations = [[float(lon), float(lat)] for lat, lon in origins]
        locations.append([float(destination[1]), float(destination[0])])
        return {
            "locations": locations,
            "sources": list(range(len(origins))),
            "destinations": [len(origins)],
            "metrics": ["distance", "duration"],
            "units": "km",
        }

    def _backoff(self, attempt: int, retry_after: Optional[str]) -> float:
        if retry_after and retry_after.strip().isdigit():
            return float(retry_after)
        return self.backoff_base_seconds * 2 ** (attempt - 1) + random.uniform(0, 0.5)

    def matrix_many_to_one(self, origins: Sequence[LatLon], destination: LatLon) -> MatrixResult:
        request_json = json.dumps(self.build_many_to_one_payload(origins, destination))
        headers = {"Authorization": self._api_key, "Content-Type": "application/json"}
        started = time.time()
        attempts, status, body, error = 0, None, None, None

        while attempts <= self.max_retries:
            attempts += 1
            retry_after = None
            try:
                resp = self._session.post(self.url, data=request_json, headers=headers,
                                          timeout=self.timeout_seconds)
                status, body = resp.status_code, resp.text
                if status == 200:
                    error = self._validate_body(body)
                    break
                if status not in self.retryable_status:
                    error = f"non-retryable HTTP {status}"
                    break
                error = f"HTTP {status}"
                retry_after = resp.headers.get("Retry-After")
            except requests.RequestException as exc:
                status, body = None, None
                error = f"{type(exc).__name__}: {str(exc)[:300]}"
            if attempts <= self.max_retries:
                self._sleep(self._backoff(attempts, retry_after))

        return MatrixResult(request_json, status, body, error, attempts,
                            int((time.time() - started) * 1000))

    @staticmethod
    def _validate_body(body: str) -> Optional[str]:
        try:
            parsed = json.loads(body)
        except (TypeError, ValueError):
            return "malformed JSON in 200 response"
        if "distances" not in parsed or "durations" not in parsed:
            return "200 response missing distances/durations"
        return None

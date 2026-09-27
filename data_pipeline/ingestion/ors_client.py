import time
from typing import Any

import requests


DEFAULT_ORS_MATRIX_URL = (
    "https://api.heigit.org/openrouteservice/v2/matrix/driving-car"
)


class ORSClient:
    def __init__(
        self,
        api_key: str,
        timeout_seconds: int = 15,
        max_attempts: int = 3,
        base_backoff_seconds: float = 1.0,
        matrix_url: str = DEFAULT_ORS_MATRIX_URL,
    ) -> None:
        if not api_key:
            raise ValueError("ORS API key is required.")

        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.base_backoff_seconds = base_backoff_seconds
        self.matrix_url = matrix_url

    def matrix(
        self,
        locations: list[list[float]],
        sources: list[int] | None = None,
        destinations: list[int] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "locations": locations,
            "metrics": ["distance", "duration"],
            "units": "m",
        }

        if sources is not None:
            payload["sources"] = sources

        if destinations is not None:
            payload["destinations"] = destinations

        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                response = requests.post(
                    self.matrix_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )

                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()

                response.raise_for_status()
                body = response.json()

                if "distances" not in body or "durations" not in body:
                    raise ValueError(
                        "ORS response is missing distances or durations."
                    )

                return body

            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    break

                time.sleep(
                    self.base_backoff_seconds * (2 ** (attempt - 1))
                )

        raise RuntimeError(
            f"ORS matrix request failed after {self.max_attempts} attempts"
        ) from last_error

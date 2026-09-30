"""ORS client tests — no network, no Spark."""

import json

import pytest
import requests

from data_pipeline.ingestion.ors_client import ORSClient


class FakeResponse:
    def __init__(self, status, body, headers=None):
        self.status_code = status
        self.text = body
        self.headers = headers or {}


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, data=None, headers=None, timeout=None):
        self.calls.append({"url": url, "data": data, "headers": headers})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


OK_BODY = json.dumps({"distances": [[6.4]], "durations": [[840.0]]})


def make_client(responses, **kw):
    session = FakeSession(responses)
    sleeps = []
    client = ORSClient("test-key", session=session, sleep=sleeps.append, **kw)
    return client, session, sleeps


def test_payload_is_lon_lat_many_to_one():
    payload = ORSClient.build_many_to_one_payload([(24.49, 54.40), (24.47, 54.35)], (24.50, 54.38))
    assert payload["locations"] == [[54.40, 24.49], [54.35, 24.47], [54.38, 24.50]]
    assert payload["sources"] == [0, 1]
    assert payload["destinations"] == [2]
    assert payload["units"] == "km"


def test_success_first_try():
    client, session, sleeps = make_client([FakeResponse(200, OK_BODY)])
    result = client.matrix_many_to_one([(24.49, 54.40)], (24.50, 54.38))
    assert result.ok and result.attempts == 1 and sleeps == []
    assert result.response_body == OK_BODY
    assert "test-key" not in result.request_json          # key never stored in the payload
    assert session.calls[0]["url"].endswith("/driving-car")


def test_retries_429_then_succeeds_and_honours_retry_after():
    client, _, sleeps = make_client([FakeResponse(429, "slow down", {"Retry-After": "3"}),
                                     FakeResponse(200, OK_BODY)])
    result = client.matrix_many_to_one([(24.49, 54.40)], (24.50, 54.38))
    assert result.ok and result.attempts == 2
    assert sleeps == [3.0]


def test_non_retryable_status_stops_immediately_and_keeps_raw_body():
    client, _, sleeps = make_client([FakeResponse(403, '{"error":"forbidden"}')])
    result = client.matrix_many_to_one([(24.49, 54.40)], (24.50, 54.38))
    assert not result.ok and result.attempts == 1 and sleeps == []
    assert result.http_status == 403 and result.response_body == '{"error":"forbidden"}'


def test_network_errors_exhaust_retries_without_raising():
    errors = [requests.ConnectionError("down")] * 5
    client, _, sleeps = make_client(errors, max_retries=4)
    result = client.matrix_many_to_one([(24.49, 54.40)], (24.50, 54.38))
    assert not result.ok and result.attempts == 5 and len(sleeps) == 4
    assert result.http_status is None and "ConnectionError" in result.error_message


def test_malformed_200_is_an_error_but_body_is_preserved():
    client, _, _ = make_client([FakeResponse(200, "not json")])
    result = client.matrix_many_to_one([(24.49, 54.40)], (24.50, 54.38))
    assert not result.ok and result.response_body == "not json"


def test_empty_key_rejected():
    with pytest.raises(ValueError):
        ORSClient("  ")


def test_repr_does_not_leak_key():
    client, _, _ = make_client([])
    assert "test-key" not in repr(client)

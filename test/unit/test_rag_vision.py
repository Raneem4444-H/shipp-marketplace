"""Vision client + output parsing — no network, no Spark."""

import json

import requests

from rag.vision import VisionClient, build_payload, mime_type_for, parse_vision_output


def chat(content):
    return json.dumps({"choices": [{"message": {"role": "assistant", "content": content}}]})


GOOD = chat('{"image_description": "Solid oak dining table with four legs.", '
            '"detected_labels": ["Dining Table", "oak", "oak", "  wood  "]}')


class FakeResponse:
    def __init__(self, status, body, headers=None):
        self.status_code, self.text, self.headers = status, body, headers or {}


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, data=None, headers=None, timeout=None):
        self.calls.append({"url": url, "data": data, "headers": headers})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make(responses):
    session, sleeps = FakeSession(responses), []
    client = VisionClient("vision-ep", "https://host/", lambda: {"Authorization": "Bearer SECRET"},
                          session=session, sleep=sleeps.append)
    return client, session, sleeps


def test_parse_good_output_normalizes_labels():
    desc, labels, err = parse_vision_output(GOOD)
    assert err is None and desc.startswith("Solid oak")
    assert labels == ["dining table", "oak", "wood"]


def test_parse_fenced_and_list_content():
    fenced = chat('```json\n{"image_description": "A sofa.", "detected_labels": ["sofa"]}\n```')
    assert parse_vision_output(fenced)[0] == "A sofa."
    parts = chat([{"type": "text", "text": '{"image_description": "A lamp.", "detected_labels": []}'}])
    assert parse_vision_output(parts)[:2] == ("A lamp.", [])


def test_parse_never_invents():
    assert parse_vision_output(chat('{"image_description": null, "detected_labels": []}'))[2] \
        == "model reported no identifiable item"
    assert parse_vision_output(chat("I think it is a chair"))[2] == "model output contains no JSON object"
    assert parse_vision_output("not json")[0] is None
    assert parse_vision_output(None)[2] == "empty response body"


def test_payload_has_image_and_no_secret():
    payload = build_payload(b"\xff\xd8abc", "image/jpeg")
    parts = payload["messages"][1]["content"]
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert payload["temperature"] == 0
    assert mime_type_for("/x/a.JPG") == "image/jpeg" and mime_type_for("/x/a.gif") is None


def test_success_first_try():
    client, session, sleeps = make([FakeResponse(200, GOOD)])
    r = client.describe_image(b"img", "image/jpeg", "sha")
    assert r.ok and r.attempts == 1 and sleeps == [] and not r.retryable
    assert session.calls[0]["url"] == "https://host/serving-endpoints/vision-ep/invocations"
    assert "SECRET" not in r.request_meta_json and "SECRET" not in repr(client)


def test_429_then_success_honours_retry_after():
    client, _, sleeps = make([FakeResponse(429, "busy", {"Retry-After": "4"}), FakeResponse(200, GOOD)])
    r = client.describe_image(b"img", "image/png")
    assert r.ok and r.attempts == 2 and sleeps == [4.0]


def test_non_retryable_keeps_raw_body():
    client, _, sleeps = make([FakeResponse(400, '{"error":"bad image"}')])
    r = client.describe_image(b"img", "image/png")
    assert not r.ok and not r.retryable and r.attempts == 1 and sleeps == []
    assert r.response_body == '{"error":"bad image"}'


def test_network_errors_exhaust_retries_and_stay_retryable():
    client, _, sleeps = make([requests.ConnectionError("down")] * 4)
    r = client.describe_image(b"img", "image/png")
    assert not r.ok and r.retryable and r.attempts == 4 and len(sleeps) == 3


def test_unparseable_200_is_failed_not_retried():
    client, _, _ = make([FakeResponse(200, chat("a nice chair"))])
    r = client.describe_image(b"img", "image/png")
    assert not r.ok and not r.retryable and r.response_body is not None


def test_bad_input_never_calls_endpoint():
    client, session, _ = make([])
    assert client.describe_image(b"", "image/png").error_message == "empty image file"
    assert client.describe_image(b"x", None).error_message == "unsupported image type"
    assert "too large" in client.describe_image(b"x" * (5 * 1024 * 1024 + 1), "image/png").error_message
    assert session.calls == []

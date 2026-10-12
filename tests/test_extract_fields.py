import json
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from ingestion.extract_fields import extract_fields

VALID_REPLY = {
    "building_type": "mixed_use",
    "stories": 5,
    "unit_count": 40,
    "square_footage": 52000,
    "is_ground_up": True,
    "involves_demolition": False,
    "zone": "R-3",
    "variance_types": ["c", "d1"],
    "confidence": 0.9,
}
REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


class FakeClient:
    """Anthropic client stand-in: returns `reply_text`, or raises `error`, and counts calls."""

    def __init__(self, reply_text: str | None = None, error: Exception | None = None) -> None:
        self.call_count = 0
        self.messages = SimpleNamespace(create=self._create)
        self._reply_text = reply_text
        self._error = error

    def _create(self, **kwargs: object) -> SimpleNamespace:
        self.call_count += 1
        if self._error is not None:
            raise self._error
        text_block = SimpleNamespace(type="text", text=self._reply_text)
        return SimpleNamespace(content=[text_block], model="claude-test-1")


def test_valid_reply_becomes_a_field_extraction() -> None:
    client = FakeClient(reply_text=json.dumps(VALID_REPLY))

    extraction = extract_fields("Construct a 5-story mixed-use building.", client=client)

    assert extraction.building_type == "mixed_use"
    assert extraction.variance_types == ["c", "d1"]
    assert extraction.model_version == "claude-test-1"


def test_blank_project_text_makes_no_claude_call() -> None:
    client = FakeClient(reply_text=json.dumps(VALID_REPLY))

    extraction = extract_fields("   \n", client=client)

    assert client.call_count == 0
    assert extraction.building_type is None
    assert extraction.model_version is None


def test_rate_limit_leaves_the_extraction_empty_so_it_is_retried_later() -> None:
    response = httpx.Response(429, request=REQUEST)
    client = FakeClient(error=anthropic.RateLimitError("slow down", response=response, body=None))

    extraction = extract_fields("Construct a warehouse.", client=client)

    assert extraction.model_version is None
    assert extraction.variance_types == []


def test_connection_error_leaves_the_extraction_empty() -> None:
    client = FakeClient(error=anthropic.APIConnectionError(request=REQUEST))

    extraction = extract_fields("Construct a warehouse.", client=client)

    assert extraction.model_version is None


def test_reply_that_is_not_json_leaves_the_extraction_empty() -> None:
    client = FakeClient(reply_text="Sorry, I cannot help with that.")

    extraction = extract_fields("Construct a warehouse.", client=client)

    assert extraction.model_version is None


def test_reply_missing_a_field_leaves_the_extraction_empty() -> None:
    incomplete_reply = {key: value for key, value in VALID_REPLY.items() if key != "stories"}
    client = FakeClient(reply_text=json.dumps(incomplete_reply))

    extraction = extract_fields("Construct a warehouse.", client=client)

    assert extraction.model_version is None


def test_bad_api_key_stops_the_run_instead_of_being_swallowed() -> None:
    response = httpx.Response(401, request=REQUEST)
    client = FakeClient(error=anthropic.AuthenticationError("bad key", response=response, body=None))

    with pytest.raises(anthropic.AuthenticationError):
        extract_fields("Construct a warehouse.", client=client)

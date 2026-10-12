from dataclasses import dataclass

import pytest

from ingestion import fetch

AGENDA_URL = "https://town.example/AgendaCenter/Search"
ROBOTS_URL = "https://town.example/robots.txt"


@dataclass
class FakeResponse:
    status_code: int
    text: str = ""


class FakeRobotsServer:
    """Stands in for httpx.get and records every URL requested."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.requested_urls: list[str] = []
        monkeypatch.setattr(fetch.httpx, "get", self._get)
        self.response = FakeResponse(status_code=404)

    def _get(self, url: str, **kwargs: object) -> FakeResponse:
        self.requested_urls.append(url)
        return self.response


@pytest.fixture
def robots_server(monkeypatch: pytest.MonkeyPatch) -> FakeRobotsServer:
    monkeypatch.setattr(fetch, "_robots_parsers", {})
    monkeypatch.setattr(fetch, "_wait_for_rate_limit", lambda: None)
    return FakeRobotsServer(monkeypatch)


def test_missing_robots_txt_allows_fetching(robots_server) -> None:
    robots_server.response = FakeResponse(status_code=404)

    fetch._check_robots_txt(AGENDA_URL)


def test_unreadable_robots_txt_refuses_fetching(robots_server) -> None:
    robots_server.response = FakeResponse(status_code=403)

    with pytest.raises(fetch.RobotsDisallowedError, match="HTTP 403"):
        fetch._check_robots_txt(AGENDA_URL)


def test_blocked_robots_txt_points_to_manual_ingestion(robots_server) -> None:
    robots_server.response = FakeResponse(status_code=403)

    with pytest.raises(fetch.RobotsDisallowedError, match="ingest --dir"):
        fetch._check_robots_txt(AGENDA_URL)


def test_server_error_on_robots_txt_does_not_suggest_bot_protection(robots_server) -> None:
    robots_server.response = FakeResponse(status_code=500)

    with pytest.raises(fetch.RobotsDisallowedError) as error:
        fetch._check_robots_txt(AGENDA_URL)

    assert "bot protection" not in str(error.value)


def test_disallowed_path_refuses_fetching(robots_server) -> None:
    robots_server.response = FakeResponse(status_code=200, text="User-agent: *\nDisallow: /AgendaCenter")

    with pytest.raises(fetch.RobotsDisallowedError, match="disallows"):
        fetch._check_robots_txt(AGENDA_URL)


def test_allowed_path_passes_when_other_paths_are_disallowed(robots_server) -> None:
    robots_server.response = FakeResponse(status_code=200, text="User-agent: *\nDisallow: /admin")

    fetch._check_robots_txt(AGENDA_URL)


def test_robots_txt_is_fetched_once_per_host(robots_server) -> None:
    robots_server.response = FakeResponse(status_code=200, text="User-agent: *\nDisallow: /admin")

    fetch._check_robots_txt(AGENDA_URL)
    fetch._check_robots_txt("https://town.example/AgendaCenter/ViewFile/Agenda/1")

    assert robots_server.requested_urls == [ROBOTS_URL]


def test_unauthorized_town_is_refused_before_any_network_call(robots_server) -> None:
    robots_server.response = FakeResponse(status_code=200)

    with pytest.raises(fetch.CrawlNotAuthorizedError):
        fetch.fetch_url(AGENDA_URL, "montclair")

    assert robots_server.requested_urls == []

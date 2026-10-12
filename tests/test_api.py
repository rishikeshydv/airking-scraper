"""Read API behaviour against a real Postgres (see conftest.py)."""

import datetime
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from api.db import get_db
from api.main import app
from api.models import AgendaItem, Meeting


def make_item(meeting_id: int, item_number: int, **fields: object) -> AgendaItem:
    defaults = dict(
        meeting_id=meeting_id,
        agenda_section="New Applications",
        item_number=item_number,
        application_id=f"APP-{item_number}",
        premises="1 Main St",
        block="100",
        lots=["1"],
        ward="",
        applicant="Acme LLC",
        project_text="Build something.",
        variance_types=[],
    )
    return AgendaItem(**{**defaults, **fields})


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def get_test_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = get_test_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def seeded(session_factory: sessionmaker[Session]) -> None:
    """Two meetings: an older one with a strong lead, a newer one with a weak lead and an unscored item."""
    with session_factory() as session:
        older = Meeting(town="newark", board="planning", meeting_date=datetime.date(2026, 6, 1), raw_text="")
        newer = Meeting(town="bloomfield", board="zoning", meeting_date=datetime.date(2026, 8, 1), raw_text="")
        session.add_all([older, newer])
        session.flush()
        session.add_all(
            [
                make_item(older.id, 1, hvac_tier="A", hvac_score=490, is_ground_up=True, applicant="Hotel Corp"),
                make_item(newer.id, 1, hvac_tier="D", hvac_score=100),
                make_item(newer.id, 2, hvac_tier=None, hvac_score=None),
            ]
        )
        session.commit()


def application_ids(response) -> list[str]:
    return [item["application_id"] for item in response.json()]


def test_default_sort_puts_highest_score_first_and_unscored_last(client, seeded) -> None:
    response = client.get("/agenda-items")

    assert application_ids(response) == ["APP-1", "APP-1", "APP-2"]
    assert [item["hvac_score"] for item in response.json()] == [490, 100, None]


def test_sort_by_date_puts_latest_meeting_first(client, seeded) -> None:
    response = client.get("/agenda-items", params={"sort": "date"})

    assert [item["meeting"]["town"] for item in response.json()] == ["bloomfield", "bloomfield", "newark"]


def test_unknown_sort_value_is_rejected(client, seeded) -> None:
    response = client.get("/agenda-items", params={"sort": "alphabetical"})

    assert response.status_code == 422


def test_tier_filter_returns_only_that_tier(client, seeded) -> None:
    response = client.get("/agenda-items", params={"tier": "A"})

    assert [item["hvac_tier"] for item in response.json()] == ["A"]


def test_ground_up_filter_returns_only_ground_up_items(client, seeded) -> None:
    response = client.get("/agenda-items", params={"ground_up": "true"})

    assert [item["applicant"] for item in response.json()] == ["Hotel Corp"]


def test_town_filter_returns_only_that_town(client, seeded) -> None:
    response = client.get("/agenda-items", params={"town": "newark"})

    assert [item["meeting"]["town"] for item in response.json()] == ["newark"]

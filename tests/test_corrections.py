"""Manual corrections against a real Postgres (see conftest.py)."""

import datetime
import shutil
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from api.models import AgendaItem, Meeting
from ingestion import ingest
from ingestion.extract_fields import FieldExtraction
from tests.test_api import make_item
from tests.test_reingest import FIXTURE_PDF, StubExtractor


@pytest.fixture
def item_id(session_factory: sessionmaker[Session]) -> int:
    """One scored item: tier D residential, so a correction to hotel visibly changes the score."""
    with session_factory() as session:
        meeting = Meeting(town="newark", board="planning", meeting_date=datetime.date(2026, 8, 10), raw_text="")
        session.add(meeting)
        session.flush()
        item = make_item(
            meeting.id,
            1,
            building_type="residential_1_3_family",
            stories=2,
            variance_types=["c"],
            hvac_tier="D",
            hvac_score=102,
            extraction_model_version="stub-model",
        )
        session.add(item)
        session.commit()
        return item.id


def post_correction(client, item_id: int, **body: object):
    return client.post(f"/agenda-items/{item_id}/corrections", json=body)


def test_correction_changes_the_shown_value_and_the_score(client, item_id: int) -> None:
    response = post_correction(client, item_id, field="building_type", value="hotel", corrected_by="Maya")

    item = response.json()
    assert response.status_code == 200
    assert item["building_type"] == "hotel"
    assert item["hvac_tier"] == "A"
    assert item["hvac_score"] == 402  # tier A 400 + one 'c' variance 2


def test_response_keeps_the_extracted_value_and_who_corrected_it(client, item_id: int) -> None:
    response = post_correction(client, item_id, field="building_type", value="hotel", corrected_by="  Maya ")

    override = response.json()["overrides"]["building_type"]
    assert override["raw"] == "residential_1_3_family"
    assert override["value"] == "hotel"
    assert override["corrected_by"] == "Maya"
    assert override["corrected_at"] is not None


def test_correction_is_visible_in_the_list(client, item_id: int) -> None:
    post_correction(client, item_id, field="stories", value=9, corrected_by="Maya")

    listed = client.get("/agenda-items").json()[0]

    assert listed["stories"] == 9
    assert listed["overrides"]["stories"]["raw"] == 2


def test_empty_variance_list_is_a_real_correction(client, item_id: int) -> None:
    response = post_correction(client, item_id, field="variance_types", value=[], corrected_by="Maya")

    item = response.json()
    assert item["variance_types"] == []
    assert item["hvac_score"] == 100


def test_false_is_a_real_correction_for_a_yes_no_field(client, item_id: int) -> None:
    post_correction(client, item_id, field="is_ground_up", value=True, corrected_by="Maya")

    response = post_correction(client, item_id, field="is_ground_up", value=False, corrected_by="Maya")

    assert response.json()["is_ground_up"] is False
    assert response.json()["overrides"]["is_ground_up"]["value"] is False


def test_sending_null_clears_the_correction_and_restores_the_score(client, item_id: int) -> None:
    post_correction(client, item_id, field="building_type", value="hotel", corrected_by="Maya")

    response = post_correction(client, item_id, field="building_type", value=None)

    item = response.json()
    assert item["building_type"] == "residential_1_3_family"
    assert item["overrides"] == {}
    assert item["hvac_score"] == 102


def test_correction_without_a_name_is_rejected(client, item_id: int) -> None:
    response = post_correction(client, item_id, field="building_type", value="hotel")

    assert response.status_code == 422


def test_unknown_building_type_is_rejected(client, item_id: int) -> None:
    response = post_correction(client, item_id, field="building_type", value="spaceport", corrected_by="Maya")

    assert response.status_code == 422


def test_unknown_field_is_rejected(client, item_id: int) -> None:
    response = post_correction(client, item_id, field="applicant", value="Someone", corrected_by="Maya")

    assert response.status_code == 422


def test_yes_no_value_for_a_number_field_is_rejected(client, item_id: int) -> None:
    response = post_correction(client, item_id, field="stories", value=True, corrected_by="Maya")

    assert response.status_code == 422


def test_negative_number_is_rejected(client, item_id: int) -> None:
    response = post_correction(client, item_id, field="unit_count", value=-3, corrected_by="Maya")

    assert response.status_code == 422


def test_correcting_a_missing_item_is_a_404(client, item_id: int) -> None:
    response = post_correction(client, item_id + 1000, field="zone", value="B-2", corrected_by="Maya")

    assert response.status_code == 404


class HotelExtractor(StubExtractor):
    """Re-ingestion keeps producing the original extraction — the correction must still win."""

    def __call__(self, project_text: str) -> FieldExtraction:
        extraction = super().__call__(project_text)
        if extraction.building_type is not None:
            extraction.building_type = "residential_1_3_family"
            extraction.is_ground_up = False
            extraction.variance_types = []
        return extraction


@pytest.fixture
def reingestable_agenda(monkeypatch: pytest.MonkeyPatch, session_factory, tmp_path: Path) -> Path:
    monkeypatch.setattr(ingest, "SessionLocal", session_factory)
    monkeypatch.setattr(ingest.settings, "pdf_storage_dir", str(tmp_path / "stored_pdfs"))
    monkeypatch.setattr(ingest, "extract_fields", HotelExtractor())
    planning_dir = tmp_path / "agendas" / "planning"
    planning_dir.mkdir(parents=True)
    shutil.copy(FIXTURE_PDF, planning_dir / FIXTURE_PDF.name)
    return tmp_path / "agendas"


def test_correction_survives_reingestion_and_still_drives_the_score(
    client, session_factory, reingestable_agenda: Path
) -> None:
    """MILESTONES M7 acceptance: correct a field, re-run ingestion on the same PDF, the correction stays."""
    ingest.ingest_directory(reingestable_agenda)
    with session_factory() as session:
        corrected_id = session.query(AgendaItem).filter(AgendaItem.building_type.is_not(None)).first().id
    post_correction(client, corrected_id, field="building_type", value="hotel", corrected_by="Maya")

    ingest.ingest_directory(reingestable_agenda)

    with session_factory() as session:
        item = session.get(AgendaItem, corrected_id)
        assert item is not None
        assert item.building_type == "residential_1_3_family"
        assert item.building_type_override == "hotel"
        assert item.building_type_corrected_by == "Maya"
        assert item.hvac_tier == "A"


def test_corrected_item_missing_from_a_later_agenda_is_kept(client, session_factory, reingestable_agenda: Path) -> None:
    ingest.ingest_directory(reingestable_agenda)
    with session_factory() as session:
        meeting_id = session.query(Meeting).one().id
        doomed = make_item(meeting_id, 999, agenda_section="Gone", application_id="GONE-1", building_type="hotel")
        session.add(doomed)
        session.commit()
        doomed_id = doomed.id
    post_correction(client, doomed_id, field="zone", value="B-2", corrected_by="Maya")

    ingest.ingest_directory(reingestable_agenda)

    with session_factory() as session:
        assert session.get(AgendaItem, doomed_id) is not None

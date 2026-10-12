"""Re-ingestion behaviour against a real Postgres (see conftest.py)."""

import shutil
from pathlib import Path

import pytest

from api.models import AgendaItem, Meeting, Project
from ingestion import ingest
from ingestion.extract_fields import FieldExtraction

FIXTURE_PDF = Path(__file__).resolve().parent.parent / "ingestion" / "fixtures" / "pdfs" / "planning" / "newark_planning_board.pdf"


class StubExtractor:
    """Stands in for the Claude call: tags every non-blank text as a hotel and counts calls."""

    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, project_text: str) -> FieldExtraction:
        if not project_text.strip():
            return FieldExtraction(None, None, None, None, None, None, None, [], None, None)

        self.call_count += 1
        return FieldExtraction("hotel", 4, 80, 60000, True, False, "B-1", ["d1"], 0.9, "stub-model")


@pytest.fixture
def agenda_dir(tmp_path: Path) -> Path:
    planning_dir = tmp_path / "agendas" / "planning"
    planning_dir.mkdir(parents=True)
    shutil.copy(FIXTURE_PDF, planning_dir / FIXTURE_PDF.name)
    return tmp_path / "agendas"


@pytest.fixture
def pdf_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ingest.settings, "pdf_storage_dir", str(tmp_path / "stored_pdfs"))


@pytest.fixture
def extractor(monkeypatch: pytest.MonkeyPatch, session_factory, pdf_storage) -> StubExtractor:
    """Route ingestion to the scratch database and replace the Claude call with a stub."""
    monkeypatch.setattr(ingest, "SessionLocal", session_factory)
    stub = StubExtractor()
    monkeypatch.setattr(ingest, "extract_fields", stub)
    return stub


def test_reingest_keeps_every_item_id(session_factory, extractor, agenda_dir: Path) -> None:
    ingest.ingest_directory(agenda_dir)
    with session_factory() as session:
        ids_before = sorted(item.id for item in session.query(AgendaItem))

    ingest.ingest_directory(agenda_dir)

    with session_factory() as session:
        ids_after = sorted(item.id for item in session.query(AgendaItem))
    assert ids_before
    assert ids_after == ids_before


def test_reingest_does_not_call_claude_again_for_unchanged_text(session_factory, extractor, agenda_dir: Path) -> None:
    ingest.ingest_directory(agenda_dir)
    calls_after_first_run = extractor.call_count

    ingest.ingest_directory(agenda_dir)

    assert calls_after_first_run > 0
    assert extractor.call_count == calls_after_first_run


def test_reingest_retries_items_whose_extraction_failed(session_factory, extractor, agenda_dir: Path) -> None:
    ingest.ingest_directory(agenda_dir)
    with session_factory() as session:
        item = session.query(AgendaItem).filter(AgendaItem.project_text != "").first()
        item.extraction_model_version = None
        item.building_type = None
        session.commit()
        retried_id = item.id
    calls_before = extractor.call_count

    ingest.ingest_directory(agenda_dir)

    assert extractor.call_count == calls_before + 1
    with session_factory() as session:
        assert session.get(AgendaItem, retried_id).building_type == "hotel"


def test_reingest_recomputes_score_from_stored_fields(session_factory, extractor, agenda_dir: Path) -> None:
    ingest.ingest_directory(agenda_dir)
    with session_factory() as session:
        item = session.query(AgendaItem).filter(AgendaItem.building_type == "hotel").first()
        item.hvac_score = 1
        session.commit()
        item_id = item.id

    ingest.ingest_directory(agenda_dir)

    with session_factory() as session:
        # tier A 400 + ground-up 50 + d1 variance 40 + 60,000 sq ft 12
        assert session.get(AgendaItem, item_id).hvac_score == 502


def test_item_missing_from_the_agenda_is_removed_with_its_orphaned_project(session_factory, extractor, agenda_dir: Path) -> None:
    ingest.ingest_directory(agenda_dir)
    with session_factory() as session:
        meeting = session.query(Meeting).one()
        orphan_project = Project(block="99999", lots=["1"])
        session.add(orphan_project)
        session.flush()
        session.add(
            AgendaItem(
                meeting_id=meeting.id, agenda_section="Gone", item_number=999, application_id="GONE-1",
                premises="", block="99999", lots=["1"], ward="", applicant="", project_text="",
                project_id=orphan_project.id, variance_types=[],
            )
        )
        session.commit()

    ingest.ingest_directory(agenda_dir)

    with session_factory() as session:
        assert session.query(AgendaItem).filter_by(application_id="GONE-1").count() == 0
        assert session.query(Project).filter_by(block="99999").count() == 0


def test_project_is_shared_by_items_with_the_same_block_and_lots_in_any_order(session_factory, extractor, agenda_dir: Path) -> None:
    ingest.ingest_directory(agenda_dir)
    with session_factory() as session:
        session_project = ingest._get_or_create_project(session, "1234", ["5", "1"])
        same_project = ingest._get_or_create_project(session, "1234", ["1", "5"])

        assert session_project.id == same_project.id
        assert session_project.lots == ["1", "5"]

from pathlib import Path

import pytest

from ingestion import ingest

REGULAR_MEETING_TEXT = "Regular Meeting January 13, 2026\n" + "Application 1-2026 Block 10 Lot 2\n" * 20
REORGANIZATION_TEXT = "Reorganizational Meeting January 13, 2026\nRoll call\n"


@pytest.fixture
def fake_pdfs(monkeypatch: pytest.MonkeyPatch):
    """Register fake agenda PDFs as (filename, town, board, text) without touching disk."""

    def register(*pdfs: tuple[str, str, str, str]) -> None:
        text_by_path = {Path(name): text for name, _, _, text in pdfs}
        monkeypatch.setattr(
            ingest,
            "_iter_agenda_pdfs",
            lambda directory: [(Path(name), town, board) for name, town, board, _ in pdfs],
        )
        monkeypatch.setattr(ingest, "_extract_pdf_text", lambda path: text_by_path[path])

    return register


def test_longer_document_wins_when_two_pdfs_share_a_meeting(fake_pdfs) -> None:
    fake_pdfs(
        ("fairfield_reorg.pdf", "fairfield", "planning", REORGANIZATION_TEXT),
        ("fairfield_regular.pdf", "fairfield", "planning", REGULAR_MEETING_TEXT),
    )

    pdfs = ingest._read_agenda_pdfs(Path("agendas"))

    assert [pdf.path.name for pdf in pdfs] == ["fairfield_regular.pdf"]


def test_first_document_is_kept_when_a_later_one_is_shorter(fake_pdfs) -> None:
    fake_pdfs(
        ("fairfield_regular.pdf", "fairfield", "planning", REGULAR_MEETING_TEXT),
        ("fairfield_reorg.pdf", "fairfield", "planning", REORGANIZATION_TEXT),
    )

    pdfs = ingest._read_agenda_pdfs(Path("agendas"))

    assert [pdf.path.name for pdf in pdfs] == ["fairfield_regular.pdf"]


def test_same_date_in_different_boards_is_kept_as_two_meetings(fake_pdfs) -> None:
    fake_pdfs(
        ("fairfield_planning.pdf", "fairfield", "planning", REGULAR_MEETING_TEXT),
        ("fairfield_zoning.pdf", "fairfield", "zoning", REGULAR_MEETING_TEXT),
    )

    pdfs = ingest._read_agenda_pdfs(Path("agendas"))

    assert len(pdfs) == 2


def test_pdf_without_a_meeting_date_is_skipped(fake_pdfs) -> None:
    fake_pdfs(
        ("newark_notes.pdf", "newark", "planning", "Some notes with no date"),
        ("newark_agenda.pdf", "newark", "planning", REGULAR_MEETING_TEXT),
    )

    pdfs = ingest._read_agenda_pdfs(Path("agendas"))

    assert [pdf.path.name for pdf in pdfs] == ["newark_agenda.pdf"]


def test_empty_directory_is_an_error(fake_pdfs) -> None:
    fake_pdfs()

    with pytest.raises(ValueError, match="no agenda PDFs found"):
        ingest._read_agenda_pdfs(Path("agendas"))

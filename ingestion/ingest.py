"""CLI entrypoint: a local directory of agenda PDFs -> Postgres.

Manual ingestion expects PDFs organized the same way as
ingestion/fixtures/pdfs/: one subdirectory per board ("planning"/"zoning"),
filenames prefixed "<town>_" (e.g. planning/newark_planning_board.pdf). This
mirrors the fixture layout because neither the town nor the board is reliably
determinable from a PDF's own text — confirmed while building the Milestone 2
parser (e.g. the Newark zoning fixture never mentions "Newark" or "Zoning" at
all).
"""

import argparse
import io
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pdfplumber
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from api.config import settings
from api.db import SessionLocal
from api.models import AgendaItem as AgendaItemRecord
from api.models import Meeting, Project
from ingestion.extract_fields import extract_fields
from ingestion.fetch import CrawlNotAuthorizedError, RobotsDisallowedError, fetch_url
from ingestion.parse_header import AgendaItem, parse_agenda
from ingestion.scoring import hvac_score, hvac_tier
from ingestion.scrape import TOWN_AGENDA_URLS, parse_agenda_center

_MONTH_NAMES = (
    "January|February|March|April|May|June|July|August|"
    "September|October|November|December"
)
# A plain "Month D(st|nd|rd|th)?, YYYY" search is enough across all 5 towns:
# every fixture's meeting date is the first such match in the text, ahead of
# any later date mentions (extension history, "next meeting", minutes, etc).
# \s* (not \s+) after the comma: confirmed live text with no space at all
# ("August 4,2026", a Fairfield cancellation notice).
MEETING_DATE_RE = re.compile(rf"\b({_MONTH_NAMES})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s*(\d{{4}})\b", re.IGNORECASE)
GOOGLE_DRIVE_URL_RE = re.compile(r"https://drive\.google\.com/\S+")
# Only Newark's fixtures embed one of these; other towns are left null here
# rather than guessed at.
MEETING_TYPE_KEYWORDS = [
    "Conference & Regular Meeting",
    "Regular Meeting",
    "Special Meeting",
    "Conference Meeting",
    "Regular Hearing",
]


def _extract_meeting_date(text: str) -> date:
    match = MEETING_DATE_RE.search(text)
    if match is None:
        raise ValueError("could not find a meeting date in the agenda text")
    month, day, year = match.groups()
    return datetime.strptime(f"{month} {day} {year}", "%B %d %Y").date()


def _extract_meeting_type(text: str) -> str | None:
    head = text[:500]
    for keyword in MEETING_TYPE_KEYWORDS:
        if keyword.lower() in head.lower():
            return keyword
    return None


def _extract_google_drive_url(text: str) -> str | None:
    match = GOOGLE_DRIVE_URL_RE.search(text)
    return match.group(0) if match else None


def _extract_pdf_text_from_bytes(data: bytes) -> str:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _extract_pdf_text(path: Path) -> str:
    return _extract_pdf_text_from_bytes(path.read_bytes())


def _iter_agenda_pdfs(directory: Path) -> list[tuple[Path, str, str]]:
    results: list[tuple[Path, str, str]] = []
    for board in ("planning", "zoning"):
        board_dir = directory / board
        if not board_dir.is_dir():
            continue
        for pdf_path in sorted(board_dir.glob("*.pdf")):
            town = pdf_path.stem.split("_", 1)[0]
            results.append((pdf_path, town, board))
    return results


def _store_source_pdf(pdf_path: Path, meeting_id: int) -> str:
    """Copy the source PDF into settings.pdf_storage_dir so the API can serve
    it back (GET /meetings/{id}/pdf) — manual-mode PDFs otherwise have no
    stable URL at all. Returns the stored filename."""
    storage_dir = Path(settings.pdf_storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{meeting_id}.pdf"
    shutil.copyfile(pdf_path, storage_dir / filename)
    return filename


def _get_or_create_project(session: Session, block: str, lots: list[str]) -> Project | None:
    """Look up (or create) the Project row for a block+lot, the stable
    business key across meetings (docs/ARCHITECTURE.md). None when block is
    empty — nothing to link on, per CLAUDE.md's leave-it-null principle."""
    if not block:
        return None

    # Sorted so "5, 1" and "1, 5" are the same project.
    project_lots = sorted(lots)
    project = session.query(Project).filter_by(block=block, lots=project_lots).one_or_none()
    if project is None:
        project = Project(block=block, lots=project_lots)
        session.add(project)
        session.flush()
    return project


@dataclass
class AgendaPdf:
    path: Path
    town: str
    board: str
    text: str
    meeting_date: date


def _read_agenda_pdfs(directory: Path) -> list[AgendaPdf]:
    """Read every agenda PDF under `directory`, keeping one per (town, board, meeting_date).

    Some towns post more than one document for the same board and date — e.g.
    a January Reorganizational Meeting alongside a Regular Meeting on the same
    calendar date (confirmed live on Fairfield). The meetings table holds one
    row per (town, board, meeting_date), so on a collision keep whichever
    document has more actual content: reorganizational meetings are
    consistently much shorter (just an officer roll call) than one with real
    business.
    """
    pdf_paths = _iter_agenda_pdfs(directory)
    if not pdf_paths:
        raise ValueError(
            f"no agenda PDFs found under {directory} "
            f"(expected {directory}/planning/*.pdf and/or {directory}/zoning/*.pdf)"
        )

    pdf_by_meeting: dict[tuple[str, str, date], AgendaPdf] = {}
    for pdf_path, town, board in pdf_paths:
        text = _extract_pdf_text(pdf_path)
        try:
            meeting_date = _extract_meeting_date(text)
        except ValueError as e:
            # One bad PDF (e.g. a stray non-agenda document) shouldn't
            # lose everything else already gathered in this batch.
            print(f"skipping {pdf_path.name}: {e}", file=sys.stderr)
            continue

        meeting_key = (town, board, meeting_date)
        kept = pdf_by_meeting.get(meeting_key)
        if kept is not None and len(kept.text) >= len(text):
            print(f"skipping {pdf_path.name}: {kept.path.name} already covers {town}/{board} {meeting_date}", file=sys.stderr)
            continue
        if kept is not None:
            print(f"skipping {kept.path.name}: {pdf_path.name} has more content for {town}/{board} {meeting_date}", file=sys.stderr)

        pdf_by_meeting[meeting_key] = AgendaPdf(pdf_path, town, board, text, meeting_date)

    return list(pdf_by_meeting.values())


def _refresh_item_record(session: Session, record: AgendaItemRecord, item: AgendaItem) -> None:
    """Copy a parsed item onto its row, calling Claude only when the item's text is new.

    Re-ingestion writes raw extraction only; the score is recomputed from the
    stored fields every time, so a changed scoring rule takes effect on re-run.
    """
    first_block = item.blocks[0] if item.blocks else None
    block = first_block.block if first_block else ""
    lots = first_block.lots if first_block else []
    project = _get_or_create_project(session, block, lots)

    # Items whose earlier extraction failed (model_version None) are retried too.
    needs_extraction = record.project_text != item.project_text or record.extraction_model_version is None

    record.application_id = item.application_id
    record.premises = item.premises
    record.block = block
    record.lots = lots
    record.ward = item.ward
    record.applicant = item.applicant
    record.attorney = item.attorney
    record.project_text = item.project_text
    record.variances_raw = item.variances_raw
    record.project_id = project.id if project else None

    if needs_extraction:
        extraction = extract_fields(item.project_text)
        record.building_type = extraction.building_type
        record.stories = extraction.stories
        record.unit_count = extraction.unit_count
        record.square_footage = extraction.square_footage
        record.is_ground_up = extraction.is_ground_up
        record.involves_demolition = extraction.involves_demolition
        record.zone = extraction.zone
        record.variance_types = extraction.variance_types
        record.extraction_confidence = extraction.confidence
        record.extraction_model_version = extraction.model_version

    tier = hvac_tier(record.building_type, record.stories)
    record.hvac_tier = tier
    record.hvac_score = hvac_score(tier, record.is_ground_up, record.square_footage, record.variance_types)


def _delete_orphan_projects(session: Session) -> None:
    """Drop projects that no agenda item points at any more."""
    session.flush()
    session.query(Project).filter(~Project.agenda_items.any()).delete(synchronize_session=False)


def _ingest_meeting(session: Session, pdf: AgendaPdf) -> int:
    """Write one agenda PDF's meeting and items into the session. Returns the item count.

    Items are matched to existing rows by (agenda_section, item_number), so a
    re-ingest keeps each row's id and never rewrites anything but the raw fields.
    """
    items = parse_agenda(pdf.text, pdf.town, pdf.board)

    meeting = (
        session.query(Meeting)
        .filter_by(town=pdf.town, board=pdf.board, meeting_date=pdf.meeting_date)
        .one_or_none()
    )
    if meeting is None:
        meeting = Meeting(
            town=pdf.town,
            board=pdf.board,
            meeting_date=pdf.meeting_date,
            meeting_type=_extract_meeting_type(pdf.text),
            google_drive_url=_extract_google_drive_url(pdf.text),
            raw_text=pdf.text,
        )
        session.add(meeting)
        session.flush()
    else:
        meeting.meeting_type = _extract_meeting_type(pdf.text)
        meeting.google_drive_url = _extract_google_drive_url(pdf.text)
        meeting.raw_text = pdf.text

    meeting.source_pdf_path = _store_source_pdf(pdf.path, meeting.id)

    records_by_key = {(record.agenda_section, record.item_number): record for record in meeting.agenda_items}
    for item in items:
        key = (item.agenda_section, item.item_number)
        # A new row is only added once fully populated: the project lookup
        # autoflushes, and application_id etc. are NOT NULL.
        record = records_by_key.pop(key, None) or AgendaItemRecord(
            meeting_id=meeting.id,
            agenda_section=item.agenda_section,
            item_number=item.item_number,
        )
        _refresh_item_record(session, record, item)
        session.add(record)

    # Whatever is left was on file but is no longer in the agenda.
    for stale_record in records_by_key.values():
        session.delete(stale_record)

    _delete_orphan_projects(session)
    return len(items)


def ingest_directory(directory: Path) -> int:
    """Parse every agenda PDF under `directory` and upsert it into Postgres.

    Re-ingesting a meeting already on file updates its agenda_items in place
    (see _ingest_meeting). Each PDF is committed on its own, so one failure
    doesn't lose the rest of the batch. Returns the number of PDFs ingested.
    """
    ingested_count = 0
    with SessionLocal() as session:
        for pdf in _read_agenda_pdfs(directory):
            try:
                item_count = _ingest_meeting(session, pdf)
                session.commit()
            except SQLAlchemyError as e:
                session.rollback()
                print(f"failed {pdf.path.name}: {e}", file=sys.stderr)
                continue

            print(f"ingested {pdf.path.name}: {pdf.town}/{pdf.board} {pdf.meeting_date} ({item_count} items)")
            ingested_count += 1

    return ingested_count


def ingest_town(town: str) -> int:
    """Crawl-mode counterpart to ingest_directory: discover a town's current
    agenda PDFs via its CivicPlus AgendaCenter page, download them, and feed
    them through the exact same pipeline manual mode uses (avoids duplicating
    the parsing/extraction/scoring logic). Requires that town's
    *_CRAWL_AUTHORIZED=true (api/config.py) — enforced by ingestion/fetch.py,
    which also performs the robots.txt check and rate limit on every fetch.
    """
    if town not in TOWN_AGENDA_URLS:
        raise ValueError(
            f"no crawler is configured for town={town!r}. Supported towns: "
            f"{', '.join(sorted(TOWN_AGENDA_URLS))}. (Montclair's agenda platform "
            "disallows automated access in its own robots.txt — ingest it manually.)"
        )

    listing_url = TOWN_AGENDA_URLS[town]
    html = fetch_url(listing_url, town).decode("utf-8")
    meetings = parse_agenda_center(html, listing_url, town)
    if not meetings:
        raise ValueError(f"found no Planning/Zoning agenda items on {listing_url}")

    with tempfile.TemporaryDirectory() as tmpdir_name:
        tmpdir = Path(tmpdir_name)
        # Same-(board, date) documents each get their own file; ingest_directory
        # keeps the one with more content (see _read_agenda_pdfs).
        for index, meeting in enumerate(meetings):
            pdf_bytes = fetch_url(meeting.pdf_url, town)
            text = _extract_pdf_text_from_bytes(pdf_bytes)

            # The AgendaCenter row's own date is more trustworthy than
            # whatever _extract_meeting_date finds inside the PDF: a doc can
            # be posted under one date's row while its own text is about a
            # different date entirely (e.g. a cancellation notice for an
            # earlier meeting, re-posted under a later slot). Trusting the
            # content date there would silently overwrite the *other*
            # meeting's real data via the (town, board, date) upsert key —
            # found live on Fairfield's AgendaCenter. Skip rather than guess.
            try:
                content_date = _extract_meeting_date(text)
            except ValueError:
                content_date = None
            if content_date != meeting.meeting_date:
                print(
                    f"skipping {meeting.pdf_url}: row says {meeting.meeting_date}, "
                    f"document content says {content_date} — not a normal agenda for this date",
                    file=sys.stderr,
                )
                continue

            board_dir = tmpdir / meeting.board
            board_dir.mkdir(parents=True, exist_ok=True)
            dest = board_dir / f"{town}_{meeting.meeting_date.isoformat()}_{index}.pdf"
            dest.write_bytes(pdf_bytes)

        return ingest_directory(tmpdir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest agenda PDFs into Postgres, from a local directory or by crawling.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dir",
        type=Path,
        help="directory containing planning/ and/or zoning/ subdirectories of agenda PDFs",
    )
    mode.add_argument(
        "--crawl",
        metavar="TOWN",
        help="crawl a town's AgendaCenter directly (requires written permission + <TOWN>_CRAWL_AUTHORIZED=true)",
    )
    args = parser.parse_args()

    if args.dir is not None:
        if not args.dir.is_dir():
            print(f"error: {args.dir} is not a directory", file=sys.stderr)
            sys.exit(1)
        count = ingest_directory(args.dir)
        print(f"done: ingested {count} meeting(s)")
        return

    try:
        count = ingest_town(args.crawl)
    except (CrawlNotAuthorizedError, RobotsDisallowedError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"done: crawled and ingested {count} meeting(s) for {args.crawl}")


if __name__ == "__main__":
    main()

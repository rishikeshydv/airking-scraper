"""Discovers agenda PDFs from a town's CivicPlus AgendaCenter listing page —
the authorized-crawl-mode counterpart to downloading PDFs by hand. Every
fetch this feeds still goes through ingestion/fetch.py's per-town
authorization gate, robots.txt check, and rate limit; this module is pure
HTML parsing only (no I/O), per CLAUDE.md's Python code style.

Newark, Bloomfield, Fairfield, and Livingston all run the same CivicPlus
AgendaCenter platform with identical markup — confirmed by fetching each
live listing page. Montclair is deliberately absent: its agendas are hosted
on ecode360.com, a third-party platform (General Code) whose own robots.txt
disallows the /documents path they're served under. Permission from
Montclair Township doesn't override that platform operator's own policy, so
Montclair stays manual-ingestion-only until that's resolved directly with
General Code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

# Confirmed live and clear of robots.txt disallow rules for this path
# (checked 2026-08-16 — see docs/ARCHITECTURE.md's ingestion-modes section).
TOWN_AGENDA_URLS: dict[str, str] = {
    "newark": "https://www.newarknj.gov/AgendaCenter",
    "bloomfield": (
        "https://www.bloomfieldtwpnj.com/AgendaCenter/Search/"
        "?term=&CIDs=4,5,&startDate=&endDate=&dateRange=&dateSelector="
    ),
    "fairfield": (
        "https://www.fairfieldtownshipnj.gov/AgendaCenter/Search/"
        "?term=&CIDs=6,3,&startDate=&endDate=&dateRange=&dateSelector="
    ),
    "livingston": (
        "https://www.livingstonnj.org/AgendaCenter/Search/"
        "?term=&CIDs=2,3,&startDate=&endDate=&dateRange=&dateSelector="
    ),
}


@dataclass
class ScrapedMeeting:
    town: str
    board: str
    meeting_date: date
    pdf_url: str


def _resolve_board(category_name: str) -> str | None:
    name = category_name.lower()
    if "planning" in name:
        return "planning"
    if "zoning" in name:
        return "zoning"
    return None


def parse_agenda_center(html: str, page_url: str, town: str) -> list[ScrapedMeeting]:
    """Parse a CivicPlus AgendaCenter listing page into one ScrapedMeeting per
    (meeting date, agenda PDF). Only the Planning/Zoning categories are kept —
    other categories on the same page (Board of Health, Township Council, …)
    are out of scope and skipped, matching the five-town/two-board scope in
    docs/TOWN_FORMATS.md.
    """
    soup = BeautifulSoup(html, "html.parser")
    meetings: list[ScrapedMeeting] = []

    for panel in soup.select("[id^='category-panel-']"):
        heading = panel.find_previous("h2")
        board = _resolve_board(heading.get_text(strip=True)) if heading else None
        if board is None:
            continue

        for row in panel.select("tr.catAgendaRow"):
            date_label = row.select_one("strong[aria-label^='Agenda for ']")
            pdf_link = row.select_one("a.pdf")
            if date_label is None or pdf_link is None or not pdf_link.get("href"):
                continue

            meeting_date = datetime.strptime(
                date_label["aria-label"].removeprefix("Agenda for "), "%B %d, %Y"
            ).date()
            meetings.append(
                ScrapedMeeting(
                    town=town,
                    board=board,
                    meeting_date=meeting_date,
                    pdf_url=urljoin(page_url, pdf_link["href"]),
                )
            )

    return meetings

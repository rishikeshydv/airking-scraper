"""robots.txt-aware fetcher for the (default-off) authorized crawl mode.

Manual ingestion (`ingest --dir <path>`) is the default mode — see
docs/ARCHITECTURE.md's "ingestion modes" section. Automated fetching for a
given town is refused unless that town's `<TOWN>_CRAWL_AUTHORIZED` setting is
set, which is documented as requiring written permission from the town, in
addition to (not instead of) a clean robots.txt check performed on every
fetch. This module implements only the compliance machinery (the
authorization gate, the robots.txt check, the rate limit) — the actual page
scraping lives in ingestion/scrape.py.
"""

import time
import urllib.robotparser
from urllib.parse import urlparse

import httpx

from api.config import settings

USER_AGENT = "AirKingLeadTracker/0.1 (contact: leads@airkinghvac.com)"
MIN_REQUEST_INTERVAL_SECONDS = 2.0

_last_request_at: float | None = None
_robots_parsers: dict[str, urllib.robotparser.RobotFileParser] = {}

# Montclair is deliberately absent: its agenda platform (ecode360.com)
# disallows automated access to the path its agendas live under, in its own
# robots.txt — no amount of town-level permission changes that.
_CRAWL_AUTHORIZED_BY_TOWN: dict[str, bool] = {
    "newark": settings.newark_crawl_authorized,
    "bloomfield": settings.bloomfield_crawl_authorized,
    "fairfield": settings.fairfield_crawl_authorized,
    "livingston": settings.livingston_crawl_authorized,
}


class CrawlNotAuthorizedError(RuntimeError):
    """Raised when an automated fetch is attempted without that town's *_CRAWL_AUTHORIZED=true."""


class RobotsDisallowedError(RuntimeError):
    """Raised when robots.txt disallows fetching the requested URL."""


def _wait_for_rate_limit() -> None:
    global _last_request_at
    if _last_request_at is not None:
        elapsed = time.monotonic() - _last_request_at
        remaining = MIN_REQUEST_INTERVAL_SECONDS - elapsed
        if remaining > 0:
            time.sleep(remaining)
    _last_request_at = time.monotonic()


def _load_robots_parser(robots_url: str) -> urllib.robotparser.RobotFileParser:
    """Fetch and parse one host's robots.txt, rate-limited like any other request.

    RobotFileParser.read() does its own bare urllib fetch with no User-Agent
    header. Some of these town sites reject that (e.g. newarknj.gov), and
    RobotFileParser's documented fail-safe on a 403 is "assume disallow
    all" — which silently blocks a page robots.txt actually allows. Fetch
    it ourselves with the same descriptive User-Agent as every other
    request, and hand the text to the parser directly.
    """
    _wait_for_rate_limit()
    response = httpx.get(robots_url, headers={"User-Agent": USER_AGENT}, timeout=30.0)

    parser = urllib.robotparser.RobotFileParser()
    if response.status_code == 200:
        parser.parse(response.text.splitlines())
    elif response.status_code == 404:
        # A missing robots.txt means no restriction. A parser with nothing
        # parsed into it refuses everything, so allow-all must be explicit.
        parser.allow_all = True
    else:
        message = (
            f"robots.txt at {robots_url} returned HTTP {response.status_code}; "
            "refusing to crawl without a readable robots.txt"
        )
        if response.status_code == 403:
            message += (
                ". A 403 usually means the site blocks automated clients (bot protection), "
                "which a different User-Agent won't fix. Download the PDFs by hand and use `ingest --dir`."
            )
        raise RobotsDisallowedError(message)
    return parser


def _check_robots_txt(url: str) -> None:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    # One fetch per host per run; the check itself still runs for every URL.
    if robots_url not in _robots_parsers:
        _robots_parsers[robots_url] = _load_robots_parser(robots_url)

    if not _robots_parsers[robots_url].can_fetch(USER_AGENT, url):
        raise RobotsDisallowedError(f"robots.txt at {robots_url} disallows fetching {url}")


def fetch_url(url: str, town: str) -> bytes:
    """Fetch a URL under authorized-crawl-mode compliance rules.

    Raises CrawlNotAuthorizedError unless `town`'s *_CRAWL_AUTHORIZED setting
    is true, and RobotsDisallowedError if the target's robots.txt disallows
    it. Requests are rate-limited to at most one every
    MIN_REQUEST_INTERVAL_SECONDS, shared across all towns — a stricter global
    cap trivially satisfies each site's own per-domain rate limit.
    """
    if not _CRAWL_AUTHORIZED_BY_TOWN.get(town, False):
        raise CrawlNotAuthorizedError(
            f"Automated fetching for {town!r} is disabled. Manual ingestion "
            "(`ingest --dir <path>`) is the default mode and requires no network "
            f"access. Set {town.upper()}_CRAWL_AUTHORIZED=true only with written "
            "permission from that town — see docs/ARCHITECTURE.md's ingestion "
            "modes section."
        )

    _check_robots_txt(url)
    _wait_for_rate_limit()

    response = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
    response.raise_for_status()
    return response.content

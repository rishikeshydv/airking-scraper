import json
from dataclasses import asdict
from pathlib import Path

import pytest

from ingestion.parse_header import parse_pdf

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "ingestion" / "fixtures"
PDF_DIR = FIXTURES_DIR / "pdfs"
EXPECTED_DIR = FIXTURES_DIR / "expected"

FIXTURE_PDFS = sorted(PDF_DIR.rglob("*.pdf"))


def test_fixtures_present() -> None:
    assert len(FIXTURE_PDFS) >= 5


@pytest.mark.parametrize("pdf_path", FIXTURE_PDFS, ids=lambda p: p.stem)
def test_parse_matches_fixture(pdf_path: Path) -> None:
    town = pdf_path.stem.split("_", 1)[0]
    board = pdf_path.parent.name
    expected = json.loads((EXPECTED_DIR / f"{pdf_path.stem}.json").read_text())
    actual = [asdict(item) for item in parse_pdf(pdf_path, town, board)]
    assert actual == expected

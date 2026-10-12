"""Claude call: project_text -> derived fields.

Per CLAUDE.md, this is the only module allowed to call the Claude API — the
frontend and the rest of ingestion never do.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass

import anthropic

from api.config import settings
from ingestion.scoring import BUILDING_TYPES

MODEL = "claude-opus-5"

# Failures worth retrying on the next ingest. Auth and bad-request errors are
# deliberately not here: they mean a broken setup and should stop the run.
_TRANSIENT_API_ERRORS = (
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "building_type": {"anyOf": [{"type": "string", "enum": sorted(BUILDING_TYPES)}, {"type": "null"}]},
        "stories": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "unit_count": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "square_footage": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "is_ground_up": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
        "involves_demolition": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
        "zone": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "variance_types": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
    "required": [
        "building_type",
        "stories",
        "unit_count",
        "square_footage",
        "is_ground_up",
        "involves_demolition",
        "zone",
        "variance_types",
        "confidence",
    ],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = (
    "You extract structured land-use project facts from New Jersey planning/zoning "
    "agenda text, for an HVAC contractor's lead-scoring pipeline. Extract only what "
    "the text actually states — leave a field null rather than guess. confidence is "
    "your own 0-1 estimate of how well-supported this extraction is by the text. "
    f"building_type must be one of: {', '.join(sorted(BUILDING_TYPES))}. "
    "variance_types must be the bare variance TYPE CODE(s) mentioned in the text — "
    "a lowercase letter optionally followed by a number, e.g. 'c', 'd', 'd1', 'd5', "
    "'d6' — not a description of what the variance is for. New Jersey land-use text "
    "states these explicitly (e.g. \"11 'c' variances for...\", \"a D1 (Use) Variance "
    "and C Variances for...\", \"Class C Bulk variances\"). If several variances of the "
    "same code appear, list that code once."
)


@dataclass
class FieldExtraction:
    building_type: str | None
    stories: int | None
    unit_count: int | None
    square_footage: int | None
    is_ground_up: bool | None
    involves_demolition: bool | None
    zone: str | None
    variance_types: list[str]
    confidence: float | None
    model_version: str | None


def _empty_extraction() -> FieldExtraction:
    return FieldExtraction(
        building_type=None,
        stories=None,
        unit_count=None,
        square_footage=None,
        is_ground_up=None,
        involves_demolition=None,
        zone=None,
        variance_types=[],
        confidence=None,
        model_version=None,
    )


def extract_fields(project_text: str, *, client: anthropic.Anthropic | None = None) -> FieldExtraction:
    """Extract derived fields from one agenda item's project_text.

    Returns an all-null extraction (no Claude call) when project_text is
    blank — several towns' agenda formats (Fairfield's memorializations) print
    no project narrative at all, and there's nothing to extract from silence.
    Also returns all-null (model_version None) on a transient API failure or an
    unusable reply, so the item still ingests and is retried next time.
    """
    text = project_text.strip()
    if not text:
        return _empty_extraction()

    client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}},
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
    except _TRANSIENT_API_ERRORS as e:
        print(f"extraction skipped, will retry on next ingest: {e}", file=sys.stderr)
        return _empty_extraction()

    try:
        data = json.loads(next(block.text for block in response.content if block.type == "text"))
        return FieldExtraction(
            building_type=data["building_type"],
            stories=data["stories"],
            unit_count=data["unit_count"],
            square_footage=data["square_footage"],
            is_ground_up=data["is_ground_up"],
            involves_demolition=data["involves_demolition"],
            zone=data["zone"],
            variance_types=data["variance_types"],
            confidence=data["confidence"],
            model_version=response.model,
        )
    except (StopIteration, json.JSONDecodeError, KeyError) as e:
        print(f"extraction skipped, unusable model reply ({type(e).__name__}): {e}", file=sys.stderr)
        return _empty_extraction()

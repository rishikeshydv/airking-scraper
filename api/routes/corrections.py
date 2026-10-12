"""POST /agenda-items/{id}/corrections — the API's only write path.

A correction stores an override next to the extracted value; it never
changes the extracted value, so re-ingestion can keep refreshing that while
the override wins everywhere it is displayed or scored. Sending a null value
clears the correction.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.db import get_db
from api.models import AgendaItem
from api.routes.agenda_items import AgendaItemOut, FieldValue
from ingestion.scoring import BUILDING_TYPES

router = APIRouter()

DerivedField = Literal[
    "building_type",
    "stories",
    "unit_count",
    "square_footage",
    "is_ground_up",
    "involves_demolition",
    "zone",
    "variance_types",
]


class CorrectionIn(BaseModel):
    field: DerivedField
    value: FieldValue
    # Who made the correction; required unless the correction is being cleared.
    corrected_by: str | None = None


def validated_value(field: DerivedField, value: FieldValue) -> FieldValue:
    """Check a correction's value against its field's type, raising 422 when it doesn't fit."""
    if value is None:
        return None

    if field == "building_type":
        if value not in BUILDING_TYPES:
            raise HTTPException(422, f"building_type must be one of: {', '.join(sorted(BUILDING_TYPES))}")
    elif field in ("stories", "unit_count", "square_footage"):
        # bool is an int subclass in Python, so rule it out explicitly.
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise HTTPException(422, f"{field} must be a non-negative whole number")
    elif field in ("is_ground_up", "involves_demolition"):
        if not isinstance(value, bool):
            raise HTTPException(422, f"{field} must be true or false")
    elif field == "zone":
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(422, "zone must be non-empty text")
        return value.strip()
    elif field == "variance_types":
        if not isinstance(value, list):
            raise HTTPException(422, "variance_types must be a list of variance codes such as ['c', 'd1']")
    return value


@router.post("/agenda-items/{item_id}/corrections", response_model=AgendaItemOut)
def correct_agenda_item(item_id: int, correction: CorrectionIn, db: Session = Depends(get_db)) -> AgendaItemOut:
    item = db.get(AgendaItem, item_id)
    if item is None:
        raise HTTPException(404, f"agenda item {item_id} not found")

    value = validated_value(correction.field, correction.value)
    corrected_by = (correction.corrected_by or "").strip()
    if value is not None and not corrected_by:
        raise HTTPException(422, "corrected_by is required when setting a correction")

    is_clearing = value is None
    setattr(item, f"{correction.field}_override", value)
    setattr(item, f"{correction.field}_corrected_by", None if is_clearing else corrected_by)
    setattr(item, f"{correction.field}_corrected_at", None if is_clearing else func.now())
    item.recompute_score()

    db.commit()
    db.refresh(item)
    return AgendaItemOut.from_item(item)

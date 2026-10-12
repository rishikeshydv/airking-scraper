"""GET /agenda-items — the read-mostly REST API's main list/filter endpoint.

Filters and default sort mirror docs/PROD-SPEC.md's core sales-lead flow and
docs/ARCHITECTURE.md's state-management section: town, board, tier, agenda
section, date range, ground-up-only, and a text search across project_text
and applicant name — nothing beyond that documented filter set. Default sort
is hvac_score descending (best leads first), with sort=date for latest meeting
first; state/county are a frontend-only
drill-down toward town (docs/PROD-SPEC.md — all 5 towns share one state and
county today), not separate filters here.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, computed_field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.db import get_db
from api.models import AgendaItem, Meeting

router = APIRouter()


class MeetingSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    town: str
    board: str
    meeting_date: date
    meeting_type: str | None
    google_drive_url: str | None
    source_pdf_path: str | None = Field(exclude=True)

    @computed_field
    @property
    def source_pdf_url(self) -> str | None:
        return f"/meetings/{self.id}/pdf" if self.source_pdf_path else None


class AgendaItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    meeting: MeetingSummaryOut
    project_id: int | None
    agenda_section: str | None
    item_number: int
    application_id: str
    premises: str
    block: str
    lots: list[str]
    ward: str
    applicant: str
    attorney: str | None
    project_text: str
    variances_raw: str | None
    building_type: str | None
    stories: int | None
    unit_count: int | None
    square_footage: int | None
    is_ground_up: bool | None
    involves_demolition: bool | None
    zone: str | None
    variance_types: list[str]
    extraction_confidence: float | None
    hvac_tier: str | None
    hvac_score: int | None


@router.get("/agenda-items", response_model=list[AgendaItemOut])
def list_agenda_items(
    town: str | None = Query(None, description="e.g. newark, bloomfield"),
    board: str | None = Query(None, description="planning | zoning"),
    tier: str | None = Query(None, description="A | B | C | D"),
    section: str | None = Query(None, description="agenda_section, exact match"),
    date_from: date | None = None,
    date_to: date | None = None,
    ground_up: bool | None = Query(None, description="true to show only ground-up projects"),
    q: str | None = Query(None, description="text search across project_text and applicant"),
    sort: Literal["score", "date"] = Query("score", description="score = highest hvac_score first; date = latest meeting first"),
    db: Session = Depends(get_db),
) -> list[AgendaItem]:
    query = db.query(AgendaItem).join(Meeting)

    if town is not None:
        query = query.filter(Meeting.town == town)
    if board is not None:
        query = query.filter(Meeting.board == board)
    if tier is not None:
        query = query.filter(AgendaItem.hvac_tier == tier)
    if section is not None:
        query = query.filter(AgendaItem.agenda_section == section)
    if date_from is not None:
        query = query.filter(Meeting.meeting_date >= date_from)
    if date_to is not None:
        query = query.filter(Meeting.meeting_date <= date_to)
    if ground_up:
        query = query.filter(AgendaItem.is_ground_up.is_(True))
    if q:
        pattern = f"%{q}%"
        query = query.filter(or_(AgendaItem.project_text.ilike(pattern), AgendaItem.applicant.ilike(pattern)))

    if sort == "score":
        # Unscored items (unknown building type) sink to the bottom.
        query = query.order_by(AgendaItem.hvac_score.desc().nulls_last(), Meeting.meeting_date.desc(), AgendaItem.id.desc())
    else:
        query = query.order_by(Meeting.meeting_date.desc(), AgendaItem.id.desc())

    return query.all()

"""GET /meetings/{id} — a single meeting, including raw_text for verifying
derived fields back against the source agenda (CLAUDE.md priority #1).

GET /meetings/{id}/pdf serves the source PDF itself back — see
ingestion/ingest.py's _store_source_pdf for why manual-mode PDFs need this
(no network fetch means no URL of their own).
"""

import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, computed_field
from sqlalchemy.orm import Session

from api.config import settings
from api.db import get_db
from api.models import Meeting

router = APIRouter()


class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    town: str
    board: str
    meeting_date: datetime.date
    meeting_type: str | None
    document_center_id: str | None
    source_url: str | None
    google_drive_url: str | None
    raw_text: str
    ingested_at: datetime.datetime
    source_pdf_path: str | None = Field(exclude=True)

    @computed_field
    @property
    def source_pdf_url(self) -> str | None:
        return f"/meetings/{self.id}/pdf" if self.source_pdf_path else None


@router.get("/meetings/{meeting_id}", response_model=MeetingOut)
def get_meeting(meeting_id: int, db: Session = Depends(get_db)) -> Meeting:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="meeting not found")
    return meeting


@router.get("/meetings/{meeting_id}/pdf")
def get_meeting_pdf(meeting_id: int, db: Session = Depends(get_db)) -> FileResponse:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None or meeting.source_pdf_path is None:
        raise HTTPException(status_code=404, detail="source PDF not available for this meeting")

    pdf_path = Path(settings.pdf_storage_dir) / meeting.source_pdf_path
    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="source PDF not available for this meeting")

    return FileResponse(pdf_path, media_type="application/pdf")

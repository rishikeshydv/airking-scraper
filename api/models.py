from __future__ import annotations

import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db import Base


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (
        UniqueConstraint("town", "board", "meeting_date", name="uq_meetings_town_board_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Five towns in scope (see docs/TOWN_FORMATS.md); `board` is generalized as
    # "planning"/"zoning" across all of them rather than Newark's own CPB/ZBA
    # naming, matching ingestion/parse_header.py's (town, board) dispatch key.
    town: Mapped[str]
    board: Mapped[str]
    meeting_date: Mapped[datetime.date] = mapped_column(index=True)
    meeting_type: Mapped[str | None]
    # Populated only by authorized-crawl-mode fetches; always null for manual
    # ingestion (no network access to newarknj.gov in that mode).
    document_center_id: Mapped[str | None]
    source_url: Mapped[str | None]
    # Path (relative to settings.pdf_storage_dir) of the source PDF copied in
    # at ingest time, so the API can serve it back — see
    # GET /meetings/{id}/pdf. Null for meetings ingested before this existed.
    source_pdf_path: Mapped[str | None]
    google_drive_url: Mapped[str | None]
    raw_text: Mapped[str]
    ingested_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    agenda_items: Mapped[list["AgendaItem"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )


class Project(Base):
    """One row per real-world project, keyed on block+lot, linking the
    agenda_items where it reappears across meetings (docs/ARCHITECTURE.md)."""

    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("block", "lots", name="uq_projects_block_lots"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    block: Mapped[str]
    lots: Mapped[list[str]] = mapped_column(ARRAY(String))

    agenda_items: Mapped[list["AgendaItem"]] = relationship(back_populates="project")


class AgendaItem(Base):
    __tablename__ = "agenda_items"
    __table_args__ = (
        UniqueConstraint(
            "meeting_id", "agenda_section", "item_number", name="uq_agenda_items_meeting_section_item"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"))
    agenda_section: Mapped[str | None]
    item_number: Mapped[int]
    application_id: Mapped[str]
    premises: Mapped[str]
    # Singular block/multiple lots, per docs/ARCHITECTURE.md's data model — no
    # fixture item across all 5 towns has ever carried more than one block.
    block: Mapped[str]
    lots: Mapped[list[str]] = mapped_column(ARRAY(String))
    ward: Mapped[str]
    applicant: Mapped[str]
    attorney: Mapped[str | None]
    project_text: Mapped[str]
    variances_raw: Mapped[str | None]

    # Null when block is empty (nothing to link on) — see ingestion/ingest.py.
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))

    # Derived fields, extracted from project_text by Claude
    # (ingestion/extract_fields.py) and stored with one confidence score and
    # model version covering the whole extraction — not per field, matching
    # docs/ARCHITECTURE.md's "stored with a confidence score and model
    # version" (singular).
    building_type: Mapped[str | None]
    stories: Mapped[int | None]
    unit_count: Mapped[int | None]
    square_footage: Mapped[int | None]
    is_ground_up: Mapped[bool | None]
    involves_demolition: Mapped[bool | None]
    zone: Mapped[str | None]
    variance_types: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    extraction_confidence: Mapped[float | None]
    extraction_model_version: Mapped[str | None]

    # Computed deterministically from the derived fields above
    # (ingestion/scoring.py) — not Claude output, so no confidence/model_version.
    hvac_tier: Mapped[str | None]
    hvac_score: Mapped[int | None] = mapped_column(index=True)

    meeting: Mapped[Meeting] = relationship(back_populates="agenda_items")
    project: Mapped[Project | None] = relationship(back_populates="agenda_items")

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db import Base
from ingestion.scoring import hvac_score, hvac_tier

# Fields Claude extracts from project_text; each can carry a manual correction.
DERIVED_FIELDS = (
    "building_type",
    "stories",
    "unit_count",
    "square_footage",
    "is_ground_up",
    "involves_demolition",
    "zone",
    "variance_types",
)


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

    # Manual corrections (docs/ARCHITECTURE.md): one nullable override per derived
    # field, plus who set it and when. Null means "no correction". Ingestion
    # writes only the raw columns above, never these.
    building_type_override: Mapped[str | None]
    building_type_corrected_by: Mapped[str | None]
    building_type_corrected_at: Mapped[datetime.datetime | None]
    stories_override: Mapped[int | None]
    stories_corrected_by: Mapped[str | None]
    stories_corrected_at: Mapped[datetime.datetime | None]
    unit_count_override: Mapped[int | None]
    unit_count_corrected_by: Mapped[str | None]
    unit_count_corrected_at: Mapped[datetime.datetime | None]
    square_footage_override: Mapped[int | None]
    square_footage_corrected_by: Mapped[str | None]
    square_footage_corrected_at: Mapped[datetime.datetime | None]
    is_ground_up_override: Mapped[bool | None]
    is_ground_up_corrected_by: Mapped[str | None]
    is_ground_up_corrected_at: Mapped[datetime.datetime | None]
    involves_demolition_override: Mapped[bool | None]
    involves_demolition_corrected_by: Mapped[str | None]
    involves_demolition_corrected_at: Mapped[datetime.datetime | None]
    zone_override: Mapped[str | None]
    zone_corrected_by: Mapped[str | None]
    zone_corrected_at: Mapped[datetime.datetime | None]
    variance_types_override: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    variance_types_corrected_by: Mapped[str | None]
    variance_types_corrected_at: Mapped[datetime.datetime | None]

    # Computed deterministically from the derived fields above
    # (ingestion/scoring.py) — not Claude output, so no confidence/model_version.
    hvac_tier: Mapped[str | None]
    hvac_score: Mapped[int | None] = mapped_column(index=True)

    meeting: Mapped[Meeting] = relationship(back_populates="agenda_items")
    project: Mapped[Project | None] = relationship(back_populates="agenda_items")

    def effective(self, field: str) -> Any:
        """The corrected value of a derived field when there is one, else the extracted value."""
        override = getattr(self, f"{field}_override")
        return getattr(self, field) if override is None else override

    def has_correction(self) -> bool:
        """True when any derived field carries a manual correction."""
        return any(getattr(self, f"{field}_override") is not None for field in DERIVED_FIELDS)

    def recompute_score(self) -> None:
        """Set hvac_tier/hvac_score from the effective (corrected-if-present) field values."""
        building_type = self.effective("building_type")
        stories = self.effective("stories")
        is_ground_up = self.effective("is_ground_up")
        square_footage = self.effective("square_footage")
        variance_types = self.effective("variance_types")

        self.hvac_tier = hvac_tier(building_type, stories)
        self.hvac_score = hvac_score(self.hvac_tier, is_ground_up, square_footage, variance_types)

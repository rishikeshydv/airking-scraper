from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Later files win, so .env.development overrides a plain .env.
    model_config = SettingsConfigDict(env_file=(".env", ".env.development"), extra="ignore")

    database_url: str = "postgresql+psycopg://newark:newark@localhost:5433/newark_agenda_tracker"
    anthropic_api_key: str = ""
    # Per-town authorized-crawl gates — each requires written permission from
    # that town in addition to a clean robots.txt (see docs/ARCHITECTURE.md's
    # ingestion-modes section). Montclair has no flag: its agenda platform
    # (ecode360.com) disallows automated access in its own robots.txt.
    newark_crawl_authorized: bool = False
    bloomfield_crawl_authorized: bool = False
    fairfield_crawl_authorized: bool = False
    livingston_crawl_authorized: bool = False
    # Where ingested source PDFs are copied so the API can serve them back —
    # see GET /meetings/{id}/pdf. Manual-mode PDFs otherwise have no stable
    # URL at all (no network fetch, no AgendaCenter link).
    pdf_storage_dir: str = "storage/pdfs"
    frontend_origin: str = "http://localhost:3000"

    @field_validator("database_url")
    @classmethod
    def use_psycopg3_driver(cls, url: str) -> str:
        """Railway hands out plain postgresql:// URLs; SQLAlchemy needs the psycopg3 driver named."""
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


settings = Settings()

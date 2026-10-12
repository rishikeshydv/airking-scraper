"""Shared fixtures for the database-backed tests.

They run only when TEST_DATABASE_URL points at a scratch database — the
fixture drops and recreates every table in it, so never point it at real data.
"""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from api.db import Base


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("set TEST_DATABASE_URL to a scratch database to run database tests")

    engine = create_engine(database_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    yield sessionmaker(bind=engine, autoflush=False, autocommit=False)

    Base.metadata.drop_all(engine)
    engine.dispose()

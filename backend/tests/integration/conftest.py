"""DB-backed tests. Skipped as a whole unless TEST_DATABASE_URL is set; schema comes from Alembic."""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
BACKEND_DIR = Path(__file__).resolve().parents[2]
INTEGRATION_DIR = Path(__file__).resolve().parent

UTC = timezone.utc


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if TEST_DATABASE_URL:
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL is not set")
    for item in items:
        if INTEGRATION_DIR in item.path.parents:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    from app.db.models import Base

    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    from app.db.models import Base
    from app.services.seed import seed

    tables = ", ".join(table.name for table in reversed(Base.metadata.sorted_tables))
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    session = Session(engine, expire_on_commit=False)
    seed(session)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    from app.config import settings
    from app.db.session import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    # Not used as a context manager on purpose: that keeps the lifespan (notifier worker) out of the tests.
    test_client = TestClient(app, headers={"X-API-Key": settings.API_KEY})
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def event(
    event_id: str,
    customer_id: str = "cus_asha",
    meter: str = "api_calls",
    quantity: int = 1,
    occurred_at: datetime | str = "2026-02-20T10:00:00Z",
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "customer_id": customer_id,
        "meter": meter,
        "quantity": quantity,
        "occurred_at": occurred_at.isoformat() if isinstance(occurred_at, datetime) else occurred_at,
    }


def events(prefix: str, count: int, **overrides: Any) -> list[dict[str, Any]]:
    return [event(f"evt_{prefix}_{i}", **overrides) for i in range(count)]

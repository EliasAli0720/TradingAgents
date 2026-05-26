from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tradingagents.api.config import get_api_settings


class Base(DeclarativeBase):
    pass


def create_db_engine(database_url: str | None = None):
    url = database_url or get_api_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine_kwargs = {}
    if url.startswith("sqlite") and ":memory:" in url:
        engine_kwargs["poolclass"] = StaticPool

    db_engine = create_engine(
        url,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
        **engine_kwargs,
    )

    if url.startswith("sqlite"):

        @event.listens_for(db_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return db_engine


engine = create_db_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    from tradingagents.api import models  # noqa: F401

    Base.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session

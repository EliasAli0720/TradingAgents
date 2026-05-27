from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine, event, inspect, text
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
    from tradingagents.api.model_catalog_repository import LLMModelCatalogRepository

    Base.metadata.create_all(engine)
    ensure_additive_schema(engine)
    with SessionLocal() as session:
        LLMModelCatalogRepository(session).ensure_seeded()
        session.commit()


def ensure_additive_schema(db_engine) -> None:
    inspector = inspect(db_engine)
    if "user_model_settings" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("user_model_settings")}
    if "encrypted_api_key" not in columns:
        with db_engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE user_model_settings ADD COLUMN encrypted_api_key TEXT")
            )
    # Reverse the prior bad migration that pointed minimax-cn at the
    # Anthropic-compatible endpoint. The OpenAI-compatible LLM client we
    # use expects /v1.
    if {"llm_provider", "backend_url"}.issubset(columns):
        with db_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE user_model_settings "
                    "SET backend_url = 'https://api.minimaxi.com/v1' "
                    "WHERE llm_provider = 'minimax-cn' "
                    "AND backend_url = 'https://api.minimaxi.com/anthropic'"
                )
            )


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session

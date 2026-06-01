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
    table_names = set(inspector.get_table_names())

    if "analysis_runs" in table_names:
        run_columns = {column["name"] for column in inspector.get_columns("analysis_runs")}
        timestamp_type = (
            "TIMESTAMP WITH TIME ZONE"
            if db_engine.dialect.name == "postgresql"
            else "DATETIME"
        )
        run_additions = {
            "priority": "INTEGER NOT NULL DEFAULT 0",
            "attempt_count": "INTEGER NOT NULL DEFAULT 0",
            "max_attempts": "INTEGER NOT NULL DEFAULT 2",
            "current_phase": "VARCHAR",
            "progress_percent": "INTEGER",
            "dispatched_at": timestamp_type,
            "heartbeat_at": timestamp_type,
            "lease_expires_at": timestamp_type,
        }
        with db_engine.begin() as connection:
            for column_name, column_definition in run_additions.items():
                if column_name not in run_columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE analysis_runs ADD COLUMN "
                            f"{column_name} {column_definition}"
                        )
                    )
            if "updated_at" not in run_columns:
                if db_engine.dialect.name == "postgresql":
                    connection.execute(
                        text(
                            "ALTER TABLE analysis_runs ADD COLUMN "
                            "updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
                        )
                    )
                else:
                    connection.execute(
                        text("ALTER TABLE analysis_runs ADD COLUMN updated_at DATETIME")
                    )
                    connection.execute(
                        text(
                            "UPDATE analysis_runs "
                            "SET updated_at = created_at "
                            "WHERE updated_at IS NULL"
                        )
                    )

    if "analysis_memory_entries" in table_names:
        memory_columns = {
            column["name"] for column in inspector.get_columns("analysis_memory_entries")
        }
        memory_additions = {
            "raw_return": "FLOAT",
            "alpha_return": "FLOAT",
            "holding_days": "INTEGER",
            "reflection": "TEXT",
        }
        with db_engine.begin() as connection:
            for column_name, column_definition in memory_additions.items():
                if column_name not in memory_columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE analysis_memory_entries ADD COLUMN "
                            f"{column_name} {column_definition}"
                        )
                    )

    if "users" in table_names:
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "language" not in user_columns:
            with db_engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE users ADD COLUMN language VARCHAR NOT NULL DEFAULT 'zh'")
                )

    if "broker_credentials" in table_names:
        broker_columns = {
            column["name"] for column in inspector.get_columns("broker_credentials")
        }
        broker_additions = {
            "auth_type": "VARCHAR NOT NULL DEFAULT 'oauth'",
            "app_key_enc": "TEXT",
            "app_secret_enc": "TEXT",
        }
        with db_engine.begin() as connection:
            for column_name, column_definition in broker_additions.items():
                if column_name not in broker_columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE broker_credentials ADD COLUMN "
                            f"{column_name} {column_definition}"
                        )
                    )

    if "user_model_settings" not in table_names:
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

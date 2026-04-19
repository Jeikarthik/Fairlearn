"""Database connection — production-ready with connection pooling.

- Postgres is the primary database (with JSONB, indexes, pooling)
- SQLite supported for development/testing ONLY
"""
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
database_url = settings.database_url

is_sqlite = database_url.startswith("sqlite")

if is_sqlite:
    if database_url.startswith("sqlite:///") and not database_url.endswith(":memory:"):
        raw_path = Path(database_url.removeprefix("sqlite:///"))
        if not raw_path.is_absolute():
            raw_path = (Path.cwd() / raw_path).resolve()
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        database_url = f"sqlite:///{raw_path.as_posix()}"

    engine_kwargs = {
        "future": True,
        "connect_args": {"check_same_thread": False},
    }
    if database_url.endswith(":memory:"):
        engine_kwargs["poolclass"] = StaticPool
else:
    # Production: PostgreSQL with connection pooling
    engine_kwargs = {
        "future": True,
        "poolclass": QueuePool,
        "pool_size": 10,        # Concurrent connections
        "max_overflow": 20,     # Burst connections
        "pool_timeout": 30,     # Wait timeout
        "pool_recycle": 1800,   # Recycle connections every 30 min
        "pool_pre_ping": True,  # Verify connections are alive
    }

engine = create_engine(database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


# Enable WAL mode for SQLite (if applicable) — better concurrent reads
if is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

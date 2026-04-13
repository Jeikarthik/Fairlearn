from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
database_url = settings.database_url

if database_url.startswith("sqlite:///"):
    raw_path = Path(database_url.removeprefix("sqlite:///"))
    if not raw_path.is_absolute():
        raw_path = (Path.cwd() / raw_path).resolve()
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{raw_path.as_posix()}"

connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine_kwargs = {"future": True, "connect_args": connect_args}
if database_url.endswith(":memory:"):
    engine_kwargs["poolclass"] = StaticPool

engine = create_engine(database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

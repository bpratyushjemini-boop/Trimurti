"""
NARAD Database Abstraction & Multi-Dialect Persistence Engine.
Seamlessly abstracts SQLite (local / private mode) and PostgreSQL (cloud persistence mode).
Features:
  - Connection pooling (pool_size, max_overflow, pool_pre_ping) for PostgreSQL
  - Thread-safe connect_args for SQLite
  - Cross-dialect schema inspection & automated lightweight migrations
  - Dialect introspection & health verification
"""

import logging
from typing import Tuple, Dict, Any
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

logger = logging.getLogger("narad.db")

# 1. Determine Dialect and Connection Engine Parameters
is_sqlite = "sqlite" in settings.DATABASE_URL.lower()

engine_kwargs: Dict[str, Any] = {
    "echo": settings.DEBUG,
}

if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # Production PostgreSQL Pooling Configuration
    engine_kwargs["pool_size"] = getattr(settings, "DATABASE_POOL_SIZE", 10)
    engine_kwargs["max_overflow"] = getattr(settings, "DATABASE_MAX_OVERFLOW", 20)
    engine_kwargs["pool_timeout"] = getattr(settings, "DATABASE_POOL_TIMEOUT", 30)
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 3600

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=engine
)

Base = declarative_base()


def get_db():
    """FastAPI dependency that provides a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_dialect() -> str:
    """Return active database engine dialect ('sqlite', 'postgresql', etc.)."""
    try:
        return engine.dialect.name
    except Exception:
        return "sqlite" if is_sqlite else "postgresql"


def is_postgres() -> bool:
    """True if active database is PostgreSQL."""
    return get_db_dialect() == "postgresql"


def check_db_readiness() -> Tuple[bool, str]:
    """Verify database connectivity with active ping query."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "connected"
    except Exception as e:
        logger.error(f"[DB] Readiness check failed: {e}")
        return False, f"unreachable: {str(e)}"


def init_db():
    """Initialize database tables and run cross-dialect schema migrations."""
    from app.db import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Cross-dialect column migration for Smriti memory fields
    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        if "smriti_memories" in existing_tables:
            existing_cols = {col["name"] for col in inspector.get_columns("smriti_memories")}
            
            new_cols = [
                ("source", "VARCHAR(64) DEFAULT 'conversation'"),
                ("confidence", "FLOAT DEFAULT 1.0"),
                ("importance", "FLOAT DEFAULT 0.5"),
                ("status", "VARCHAR(32) DEFAULT 'ACTIVE'"),
                ("scope", "VARCHAR(32) DEFAULT 'LOCAL'"),
                ("device_origin", "VARCHAR(64) DEFAULT 'mac'"),
                ("last_used_at", "DATETIME" if is_sqlite else "TIMESTAMP"),
                ("expires_at", "DATETIME" if is_sqlite else "TIMESTAMP"),
                ("times_used", "INTEGER DEFAULT 0"),
                ("metadata_json", "TEXT"),
            ]
            
            with engine.connect() as conn:
                for col_name, col_def in new_cols:
                    if col_name not in existing_cols:
                        logger.info(f"[DB] Migrating smriti_memories: adding column {col_name}")
                        conn.execute(text(f"ALTER TABLE smriti_memories ADD COLUMN {col_name} {col_def}"))
                conn.commit()
    except Exception as e:
        logger.warning(f"[DB] Schema migration notice: {e}")

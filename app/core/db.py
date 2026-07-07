"""SQLAlchemy engine/session factory and schema bootstrap.

The only database-wiring module. Callers receive an ``Engine`` or a
``sessionmaker`` built here; no module reads ``PG_DSN`` itself (that is
``Settings``' job — the DSN is passed in). Schema is applied from the
canonical ``.sql`` file with the ``/* EMBEDDING_DIM */`` placeholder
substituted at apply time, so the same DDL serves any embedding width.

Constitution trade-off: in-script ``CREATE TABLE IF NOT EXISTS`` via
``apply_schema`` instead of Alembic. Not a production migration layer.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# The placeholder the canonical SQL file carries in place of a literal
# vector dimension. Substituted with Settings.embedding_dim at apply time.
_EMBEDDING_DIM_PLACEHOLDER = "/* EMBEDDING_DIM */"
# Strips full-line and trailing ``--`` comments. Applied before splitting
# on ``;`` so a semicolon inside a comment cannot split a statement.
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")


def make_engine(dsn: str) -> Engine:
    """Build a SQLAlchemy engine for ``dsn`` (e.g. ``Settings.pg_dsn``)."""
    return create_engine(dsn, future=True)


def get_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory bound to ``engine``."""
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def ensure_pgvector_extension(engine: Engine) -> None:
    """Create the pgvector extension if it is not already present."""
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


def apply_schema(engine: Engine, sql_path: Path, *, embedding_dim: int) -> None:
    """Apply the DDL in ``sql_path`` after substituting the dim placeholder.

    Substitutes ``/* EMBEDDING_DIM */`` with ``embedding_dim``, strips
    ``--`` line comments (so a ``;`` inside a comment cannot split a
    statement), then executes each ``;``-delimited statement in one
    transaction. Idempotent because the DDL uses ``IF NOT EXISTS``.
    """
    raw_sql = sql_path.read_text(encoding="utf-8")
    substituted = raw_sql.replace(_EMBEDDING_DIM_PLACEHOLDER, str(embedding_dim))
    stripped = _LINE_COMMENT_RE.sub("", substituted)
    statements = [stmt.strip() for stmt in stripped.split(";") if stmt.strip()]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))

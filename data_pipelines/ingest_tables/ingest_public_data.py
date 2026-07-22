"""Ingest the starter complaints CSV into the Postgres ``complaints`` table.

RAG v0, structured side. Reads ``data/samples/complaints_sample.csv`` as
delivered (no cleaning, no normalisation — Safeguard), applies the
canonical schema, and UPSERTs one row per ``complaint_id``.

The starter sample contains duplicate ``complaint_id``s; the UPSERT
collapses them to one row each (last write wins) and the run logs the
dedup count so the collapse is visible, not silent (Safeguard 4).

Run:
    python -m data_pipelines.ingest_tables.ingest_public_data
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from loguru import logger
from sqlalchemy import Engine, text

from app.core.config import Settings, get_settings
from app.core.db import apply_schema, ensure_pgvector_extension, make_engine
from app.core.logging import configure_logging
from data_pipelines.starter_corpus import CANONICAL_COLUMNS, iter_complaint_rows

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CSV = _PROJECT_ROOT / "data" / "samples" / "complaints_sample.csv"
_SCHEMA_SQL = _PROJECT_ROOT / "data_pipelines" / "schema" / "0001_create_tables.sql"

# UPSERT keyed on complaint_id. Every column except the conflict key is
# refreshed from the incoming row, so a re-run converges to the CSV state.
_UPDATE_COLUMNS = tuple(c for c in CANONICAL_COLUMNS if c != "complaint_id")
_INSERT_SQL = text(
    "INSERT INTO complaints ("
    + ", ".join(CANONICAL_COLUMNS)
    + ") VALUES ("
    + ", ".join(f":{c}" for c in CANONICAL_COLUMNS)
    + ") ON CONFLICT (complaint_id) DO UPDATE SET "
    + ", ".join(f"{c} = EXCLUDED.{c}" for c in _UPDATE_COLUMNS)
)


def _require_file(path: Path, remediation: str) -> None:
    """Abort loudly if ``path`` is missing or empty (Operation 1 guard)."""
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(f"Required artifact missing or empty: {path}\n{remediation}")


def _bootstrap_schema(engine: Engine, settings: Settings) -> None:
    ensure_pgvector_extension(engine)
    apply_schema(engine, _SCHEMA_SQL, embedding_dim=settings.embedding_dim)


def ingest(engine: Engine, csv_path: Path) -> tuple[int, int, int]:
    """UPSERT every CSV row into ``complaints``.

    Returns ``(rows_read, unique_ids, rows_in_table)``. Raises on any row
    with an empty ``complaint_id`` (the primary key must be present).
    """
    rows = list(iter_complaint_rows(csv_path))
    for row in rows:
        if not row["complaint_id"]:
            raise ValueError("encountered a CSV row with an empty complaint_id")
    unique_ids = len({row["complaint_id"] for row in rows})

    with engine.begin() as conn:
        conn.execute(_INSERT_SQL, rows)
        rows_in_table = conn.execute(text("SELECT count(*) FROM complaints")).scalar_one()

    return len(rows), unique_ids, int(rows_in_table)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest the starter complaints CSV.")
    parser.add_argument("--csv-path", type=Path, default=_DEFAULT_CSV)
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_format)

    _require_file(
        args.csv_path,
        "Run: python -m data_pipelines.ingest_tables.build_starter_sample",
    )

    start = time.perf_counter()
    engine = make_engine(settings.pg_dsn)
    try:
        _bootstrap_schema(engine, settings)
        rows_read, unique_ids, rows_in_table = ingest(engine, args.csv_path)
    finally:
        engine.dispose()

    duration_ms = round((time.perf_counter() - start) * 1000)
    duplicates = rows_read - unique_ids
    if duplicates:
        logger.warning(
            "ingest_csv.dedup",
            event="ingest_csv.dedup",
            rows_read=rows_read,
            unique_complaint_ids=unique_ids,
            duplicates_collapsed=duplicates,
        )
    logger.info(
        "ingest_csv.done",
        event="ingest_csv.done",
        rows_read=rows_read,
        unique_complaint_ids=unique_ids,
        rows_in_table=rows_in_table,
        duration_ms=duration_ms,
    )
    print(
        f"complaints: read {rows_read} rows, {unique_ids} unique complaint_id "
        f"({duplicates} duplicates collapsed), {rows_in_table} rows in table."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

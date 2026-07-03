"""Chunk and embed the starter reference docs into Postgres.

RAG v0, document side. For each ``data/raw_docs/*.txt`` file:

- ``title`` = first non-empty line; ``section`` = "" (header-aware
  extraction is a later task).
- Split the whole file into fixed-size character chunks (the naive
  chunker — the ``--- 8< ---`` markers are intentionally ignored).
- Embed chunks in batches of 32 via ``LLMService.embed`` and write both
  ``docs`` and ``doc_embeddings`` in one transaction per file.

Idempotent: UPSERT on ``(source_file, chunk_index)`` for ``docs`` and on
``doc_id`` for ``doc_embeddings``. Re-running re-embeds and overwrites.

Run:
    python -m data_pipelines.ingest_docs.embed_starter_docs
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

from loguru import logger
from sqlalchemy import Engine, text

from app.api.main import build_http_client
from app.core.config import Settings, get_settings
from app.core.db import apply_schema, ensure_pgvector_extension, make_engine
from app.core.logging import configure_logging
from app.services.llm_service import LLMService
from data_pipelines.starter_corpus import chunk_text

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DOCS_DIR = _PROJECT_ROOT / "data" / "raw_docs"
_SCHEMA_SQL = _PROJECT_ROOT / "data_pipelines" / "schema" / "0001_create_tables.sql"
_EMBED_BATCH_SIZE = 32

_UPSERT_DOC = text(
    "INSERT INTO docs (source_file, title, section, chunk_index, raw_text) "
    "VALUES (:source_file, :title, :section, :chunk_index, :raw_text) "
    "ON CONFLICT (source_file, chunk_index) DO UPDATE SET "
    "title = EXCLUDED.title, section = EXCLUDED.section, raw_text = EXCLUDED.raw_text "
    "RETURNING id"
)
_UPSERT_EMBEDDING = text(
    "INSERT INTO doc_embeddings (doc_id, embedding) "
    "VALUES (:doc_id, (:embedding)::vector) "
    "ON CONFLICT (doc_id) DO UPDATE SET embedding = EXCLUDED.embedding"
)


def _title_of(content: str) -> str:
    for line in content.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _vector_literal(vector: list[float]) -> str:
    """Render a vector in pgvector's text form: ``[0.1,0.2,...]``."""
    return "[" + ",".join(str(v) for v in vector) + "]"


async def _embed_in_batches(llm: LLMService, chunks: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(chunks), _EMBED_BATCH_SIZE):
        batch = chunks[start : start + _EMBED_BATCH_SIZE]
        try:
            vectors.extend(await llm.embed(batch))
        except Exception:
            logger.error(
                "embed_docs.batch_failed",
                event="embed_docs.batch_failed",
                batch_start_index=start,
                batch_size=len(batch),
            )
            raise
    return vectors


async def _ingest_file(engine: Engine, llm: LLMService, path: Path) -> int:
    content = path.read_text(encoding="utf-8")
    title = _title_of(content)
    # Skip zero-length / whitespace-only chunks; index the kept ones
    # contiguously so (source_file, chunk_index) stays gap-free.
    chunks = [c for c in chunk_text(content) if c.strip()]
    if not chunks:
        raise ValueError(f"{path.name} produced no non-empty chunks")

    vectors = await _embed_in_batches(llm, chunks)

    with engine.begin() as conn:
        for chunk_index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            doc_id = conn.execute(
                _UPSERT_DOC,
                {
                    "source_file": path.name,
                    "title": title,
                    "section": "",
                    "chunk_index": chunk_index,
                    "raw_text": chunk,
                },
            ).scalar_one()
            conn.execute(
                _UPSERT_EMBEDDING,
                {"doc_id": doc_id, "embedding": _vector_literal(vector)},
            )
    logger.info(
        "embed_docs.file_done",
        event="embed_docs.file_done",
        source_file=path.name,
        chunks=len(chunks),
    )
    return len(chunks)


async def ingest(engine: Engine, llm: LLMService, docs_dir: Path) -> int:
    total = 0
    for path in sorted(docs_dir.glob("*.txt")):
        total += await _ingest_file(engine, llm, path)
    return total


def _require_docs(docs_dir: Path) -> list[Path]:
    files = sorted(docs_dir.glob("*.txt"))
    missing = [p for p in files if p.stat().st_size == 0]
    if not files or missing:
        raise SystemExit(
            f"No usable .txt files in {docs_dir}\n"
            "Run: python -m data_pipelines.ingest_docs.fetch_starter_docs"
        )
    return files


async def _run(settings: Settings, docs_dir: Path) -> tuple[int, int]:
    engine = make_engine(settings.pg_dsn)
    # Only the embedding client is needed here; complete() is never called.
    embed_client = build_http_client(settings, settings.embedding_provider)
    llm = LLMService(settings, embed_client, embed_client)
    try:
        ensure_pgvector_extension(engine)
        apply_schema(engine, _SCHEMA_SQL, embedding_dim=settings.embedding_dim)
        n_files = len(sorted(docs_dir.glob("*.txt")))
        chunks = await ingest(engine, llm, docs_dir)
    finally:
        await embed_client.aclose()
        engine.dispose()
    return n_files, chunks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chunk and embed the starter docs.")
    parser.add_argument("--docs-dir", type=Path, default=_DEFAULT_DOCS_DIR)
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_format)
    _require_docs(args.docs_dir)

    start = time.perf_counter()
    n_files, chunks = asyncio.run(_run(settings, args.docs_dir))
    duration_ms = round((time.perf_counter() - start) * 1000)

    logger.info(
        "embed_docs.done",
        event="embed_docs.done",
        files=n_files,
        chunks=chunks,
        duration_ms=duration_ms,
    )
    print(f"docs: embedded {chunks} chunks from {n_files} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

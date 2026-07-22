"""RetrievalService acceptance tests (Task 2, Operations 8-9).

These require a live Postgres + pgvector instance and are marked
``network`` so they are skipped by default (Constitution: DB-dependent
tests are network-marked). Run against the docker-compose ``db`` with:

    docker compose -f infra/docker-compose.yml up -d db
    poetry run pytest tests/test_retrieval_service.py -m network -q

The suite seeds a tiny deterministic fixture (a stub ``LLMService`` that
returns fixed vectors, so no Ollama is needed) and asserts the four
acceptance-criteria scenarios.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.db import (
    apply_schema,
    ensure_pgvector_extension,
    get_sessionmaker,
    make_engine,
)
from app.services.retrieval_service import ComplaintRow, DocumentChunk, RetrievalService

pytestmark = pytest.mark.network

_SCHEMA_SQL = (
    Path(__file__).resolve().parents[1] / "data_pipelines" / "schema" / "0001_create_tables.sql"
)
_TEST_DIM = 3


class _StubLLM:
    """Returns a fixed unit vector per query — deterministic, no network."""

    def __init__(self, vector: list[float]) -> None:
        self._vector = vector

    async def embed(
        self, inputs: list[str], *, model: str | None = None, request_id: str | None = None
    ) -> list[list[float]]:
        return [self._vector for _ in inputs]


@pytest.fixture
def seeded_service() -> RetrievalService:
    dsn = os.environ.get("PG_DSN", "postgresql+psycopg://app:app@localhost:5432/app")
    engine = make_engine(dsn)
    ensure_pgvector_extension(engine)
    apply_schema(engine, _SCHEMA_SQL, embedding_dim=_TEST_DIM)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM doc_embeddings"))
        conn.execute(text("DELETE FROM docs"))
        conn.execute(text("DELETE FROM complaints"))
        # Two doc chunks: one clearly nearer the query vector [1,0,0].
        conn.execute(
            text(
                "INSERT INTO docs (id, source_file, title, section, chunk_index, raw_text) "
                "VALUES (1, 'overdraft_faq.txt', 'Overdraft', '', 0, 'overdraft fee text'), "
                "(2, 'credit_card_fees.txt', 'Cards', '', 0, 'apr text')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO doc_embeddings (doc_id, embedding) VALUES "
                "(1, '[1,0,0]'), (2, '[0,1,0]')"
            )
        )
        # Complaints across two products, two dates for ordering.
        conn.execute(
            text(
                "INSERT INTO complaints (complaint_id, date_received, product, narrative) VALUES "
                "('A', '2024-01-01', 'Credit card', 'charged a late fee'), "
                "('B', '2024-06-01', 'Credit card', 'late fee again'), "
                "('C', '2024-03-01', 'Mortgage', 'escrow issue')"
            )
        )
    return RetrievalService(
        get_sessionmaker(engine), _StubLLM([1.0, 0.0, 0.0]), embedding_dim=_TEST_DIM
    )


async def test_retrieve_docs_returns_at_most_top_k_cosine_ascending(
    seeded_service: RetrievalService,
) -> None:
    results = await seeded_service.retrieve_docs("overdraft fee", top_k=1)
    assert len(results) == 1
    assert isinstance(results[0], DocumentChunk)
    # Query vector [1,0,0] is nearest doc 1 (embedding [1,0,0]).
    assert results[0].source_file == "overdraft_faq.txt"
    assert results[0].score == pytest.approx(1.0)


async def test_retrieve_docs_orders_by_similarity(seeded_service: RetrievalService) -> None:
    results = await seeded_service.retrieve_docs("overdraft fee", top_k=5)
    assert [r.source_file for r in results] == ["overdraft_faq.txt", "credit_card_fees.txt"]
    assert results[0].score >= results[1].score


async def test_retrieve_complaints_filters_by_product(seeded_service: RetrievalService) -> None:
    results = await seeded_service.retrieve_complaints("late fee", top_k=10, product="Credit card")
    assert all(isinstance(r, ComplaintRow) for r in results)
    assert {r.product for r in results} == {"Credit card"}
    # Newest first: B (2024-06) before A (2024-01).
    assert [r.complaint_id for r in results] == ["B", "A"]


async def test_retrieve_complaints_ilike_keyword(seeded_service: RetrievalService) -> None:
    results = await seeded_service.retrieve_complaints(
        "late fee", top_k=10, product="Credit card", narrative_keyword="again"
    )
    assert [r.complaint_id for r in results] == ["B"]

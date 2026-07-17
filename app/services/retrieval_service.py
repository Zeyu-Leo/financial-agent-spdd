"""RetrievalService — the application's interface to the two corpora.

Two methods only (the v0 contract Task 3 codes against):

- ``retrieve_docs``: dense vector similarity over ``docs`` ⨝
  ``doc_embeddings``. Embeds the query via ``LLMService`` and orders by
  pgvector cosine distance ascending; ``score = 1 - cosine_distance``.
- ``retrieve_complaints``: exact ``product`` match + optional single
  ``narrative_keyword`` ILIKE substring over ``complaints``, newest
  first. The ``query`` argument is logged but NOT used for filtering in
  v0 (reserved for a later embedding-ranked path).

Provider/SQL details stay inside this facade; callers receive typed
Pydantic projections, never raw SQL rows. All SQL uses bound parameters.

The ``DocumentChunk`` / ``ComplaintRow`` models live here for Task 2;
Task 3 moves them to ``app/core/state.py`` and re-exports.
"""

from __future__ import annotations

import time
from datetime import date

from loguru import logger
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.logging import get_request_id
from app.services.llm_service import LLMService


class DocumentChunk(BaseModel):
    chunk_id: int
    source_file: str
    title: str
    section: str
    chunk_index: int
    raw_text: str
    score: float


class ComplaintRow(BaseModel):
    complaint_id: str
    date_received: date
    product: str
    sub_product: str | None
    issue: str | None
    sub_issue: str | None
    company: str | None
    state: str | None
    narrative: str | None
    company_response: str | None
    consumer_disputed: str | None


_RETRIEVE_DOCS_SQL = text(
    "SELECT d.id AS chunk_id, d.source_file, d.title, d.section, "
    "d.chunk_index, d.raw_text, "
    "1 - (e.embedding <=> (:query_vec)::vector) AS score "
    "FROM docs d JOIN doc_embeddings e ON e.doc_id = d.id "
    "ORDER BY e.embedding <=> (:query_vec)::vector ASC "
    "LIMIT :top_k"
)

_COMPLAINT_COLUMNS = (
    "complaint_id, date_received, product, sub_product, issue, sub_issue, "
    "company, state, narrative, company_response, consumer_disputed"
)


def _vector_literal(vector: list[float]) -> str:
    """Render a query vector in pgvector's text form: ``[0.1,0.2,...]``."""
    return "[" + ",".join(str(v) for v in vector) + "]"


class RetrievalService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        llm: LLMService,
        *,
        embedding_dim: int,
    ) -> None:
        self._session_factory = session_factory
        self._llm = llm
        self._embedding_dim = embedding_dim

    async def retrieve_docs(
        self,
        query: str,
        *,
        top_k: int = 5,
        request_id: str | None = None,
    ) -> list[DocumentChunk]:
        rid = request_id or get_request_id()
        start = time.perf_counter()
        # Embed the query (LLMService validates the vector dimension).
        vectors = await self._llm.embed([query], request_id=rid)
        query_vec = _vector_literal(vectors[0])
        with self._session_factory() as session:
            rows = (
                session.execute(_RETRIEVE_DOCS_SQL, {"query_vec": query_vec, "top_k": top_k})
                .mappings()
                .all()
            )
        results = [DocumentChunk(**row) for row in rows]
        logger.info(
            "retrieve_docs",
            event="retrieve_docs",
            request_id=rid,
            top_k=top_k,
            result_count=len(results),
            duration_ms=round((time.perf_counter() - start) * 1000),
        )
        return results

    async def retrieve_complaints(
        self,
        query: str,
        *,
        top_k: int = 10,
        product: str | None = None,
        narrative_keyword: str | None = None,
        request_id: str | None = None,
    ) -> list[ComplaintRow]:
        rid = request_id or get_request_id()
        start = time.perf_counter()
        # query is part of the v0 contract but is not used for filtering
        # or ranking; it is logged only (reserved for the v1 path).
        clauses: list[str] = []
        params: dict[str, object] = {"top_k": top_k}
        if product:
            clauses.append("product = :product")
            params["product"] = product
        if narrative_keyword:
            clauses.append("narrative ILIKE :narrative_keyword")
            params["narrative_keyword"] = f"%{narrative_keyword}%"
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        stmt = text(
            f"SELECT {_COMPLAINT_COLUMNS} FROM complaints{where} "
            "ORDER BY date_received DESC LIMIT :top_k"
        )
        with self._session_factory() as session:
            rows = session.execute(stmt, params).mappings().all()
        results = [ComplaintRow(**row) for row in rows]
        logger.info(
            "retrieve_complaints",
            event="retrieve_complaints",
            request_id=rid,
            top_k=top_k,
            product=product,
            has_keyword=narrative_keyword is not None,
            result_count=len(results),
            duration_ms=round((time.perf_counter() - start) * 1000),
        )
        return results

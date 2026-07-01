# Week 2 — From Foundations to Naive RAG

You shipped Week 1: `Settings`, `LLMService`, structured logging
with `request_id`. The agent can call an LLM but it doesn't yet
*retrieve* anything. This week the corpus lands.

## What you're getting this week

- `.spdd_specs/tasks/Task_2_Ingestion.trainee.md` — your
  Monday brief.
- On Sunday: the destination canvas `Task_2_Ingestion.md`.

## What this week introduces

1. **The `complaints` and `docs` tables** plus a
   `doc_embeddings` pgvector table.
2. **Two ingestion scripts** — one for the public CSV
   (`ingest_public_data.py`) and one for the markdown corpus
   (`embed_starter_docs.py`).
3. **`RetrievalService`** with two methods (`retrieve_docs`,
   `retrieve_complaints`).

You're building a *deliberately simple* RAG this week. It will
appear to work. Future weeks may revisit retrieval choices —
trust that there are reasons we're keeping this week's surface
small.

## Why we did it this way

- **Why fixed-size chunking, not section-aware?** Because
  section-aware needs a doc parser, and we want you to feel the
  recall failure of fixed-size chunking before you invest in
  better. Skip the lesson and you optimise the wrong thing
  next time.
- **Why `apply_schema` with string substitution, not Alembic?**
  Trade-off documented in the constitution under "Risks &
  Trade-offs". Pedagogical simplicity here, *not* a pattern to
  copy to production.
- **Why upsert on `complaint_id` and not just insert?**
  Because the ingestion script must be idempotent. Re-running
  it on the same CSV must not double-count.

## Common Week-2 pitfalls

| Pitfall | What it looks like | The fix |
|---|---|---|
| String-formatting SQL | `f"WHERE product = '{product}'"`. | Use SQLAlchemy `text()` with bound params. The constitution forbids string-built SQL anywhere it accepts user input. |
| Embedding dim drift | Ingest writes 768-dim vectors; later code reads 1536. | The schema's `/* EMBEDDING_DIM */` placeholder is the contract; `apply_schema` substitutes from `Settings.embedding_dim`. Pick one and stick with it. |
| Returning ORM objects from `RetrievalService` | Session lifetime escapes the service; tests start failing for opaque reasons. | Project to `DocumentChunk` / `ComplaintRow` Pydantic models inside the service, before returning. |
| Forgetting `request_id: str \| None = None` | Public service methods miss the param; structured logs lose correlation. | Required by the Week-1 logging contract. Every public method takes it. |

## Wednesday self-check

- [ ] *Risks noticed* covers deduplication of `(source_file,
      chunk_index)` pairs, embedding drift, and PII handling
      for the `narrative` column.
- [ ] *Trade-offs accepted* names fixed-size vs section-aware
      chunking, `IF NOT EXISTS` schema vs migrations, ILIKE vs
      full-text search.
- [ ] *Class diagram* shows `RetrievalService → SQLAlchemy
      session_factory → Postgres`, plus `LLMService` injection
      for embeddings.
- [ ] *Operations* numbered. Schema filename pinned to
      `0001_create_tables.sql` (the destination naming will
      assume this).

## What Sunday will reveal

The destination canvas pins the exact `RetrievalService`
signatures the rest of the curriculum depends on, including
parameters you may not have written yet, and the ILIKE / ORDER
BY clauses inside the SQL. Expect a small reconciliation diff:
your `__init__` may be missing an `embedding_dim` argument, or
your `retrieve_complaints` may be missing a positional argument.

## Going further (optional reading)

- A primer on pgvector index types — HNSW vs IVFFlat — and
  when each wins. (You're not building an index this week, but
  the choice matters for Week 6.)
  [pgvector Official Indexing Documentation](https://github.com/pgvector/pgvector#indexing)
- The Anthropic / OpenAI cookbook chapters on chunking
  strategies. Fixed-size chunking fails frequently compared to
  section-aware chunking.
  [Pinecone: Chunking Strategies for LLM Applications](https://www.pinecone.io/learn/chunking-strategies/)
- The CFPB consumer complaints data dictionary so you
  understand what an `Issue` value actually means.
  [CFPB Consumer Complaint Database Data Dictionary](https://cfpb.github.io/api/ccdb/data_dictionary.html)
- **SQL Injection in the Age of AI:** String-formatting SQL
  like `f"WHERE product = '{product}'"` is forbidden; use
  SQLAlchemy `text()` with bound params.
  [SQLAlchemy: Using Textual SQL safely](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html)

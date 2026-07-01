# Task 2 — Ingestion (REASONS Canvas, trainee edition)

> **Trainee-edition posture.** This is the canvas you receive on
> Day 1 of Week 2. Sections you must complete before generating
> code are marked **TODO(trainee)**. Do not consult
> `Task_2_Ingestion.md` (the destination state) until your mentor
> signs off this canvas.
>
> **Maps to:** Learning Plan Week 2 — *Retrieval-Augmented
> Generation, the Naive Way*.
> **Depends on:** `Task_1_Foundations.trainee.md` (LLMService + Settings).
> **Unblocks:** `Task_3_Orchestration.trainee.md`.

---

## Requirements

### Analysis context

**Domain keywords scanned:** RAG, fixed-size chunking, embeddings,
pgvector ANN search, CFPB complaints CSV, ILIKE filter,
narrative_keyword. **Existing artifacts:**
`data/samples/complaints_sample.csv`,
`data/raw_docs/*.txt`, the `LLMService.embed` method (Task 1).
**Prior tasks read:** Tasks 0–1.

**Strategic direction:** ship the *naive* RAG path first. Fixed-size
chunks, raw column values, single-keyword ILIKE on narrative.
The naivety is intentional and **pedagogical**: a later task will
quantify how naive it is by running an evaluation that reveals
the data weaknesses. Resist the urge to over-engineer here.

**TODO(trainee) — Risks noticed.** Before drafting code, list
**at least three** risks specific to this naive RAG implementation
and how your design mitigates each. Hint domains: deduplication,
embedding-dim coupling to the chosen embedding model, the retrieval
interface being load-bearing for the next task, ILIKE performance
on a 1k row corpus.

### Why this task exists

The agent needs *something* to retrieve from. Tasks 3+ will all
call `RetrievalService.retrieve_docs` and
`RetrievalService.retrieve_complaints`; this task ships those two
methods backed by Postgres + pgvector. The naive shape is the
deliberate choice: a later week will measure its faults and
decide whether to upgrade.

### Acceptance criteria (Given/When/Then)

- **Given** a fresh `complaints` table and the starter CSV at
  `data/samples/complaints_sample.csv`,
  **when** `python -m data_pipelines.ingest_tables.ingest_public_data`
  runs,
  **then** the table contains one row per unique `complaint_id`
  from the CSV, with all CFPB columns populated and no NULL
  `complaint_id`.
- **Given** a fresh `docs` + `doc_embeddings` schema and the three
  starter `.txt` files,
  **when** `python -m data_pipelines.ingest_docs.embed_starter_docs`
  runs,
  **then** every chunk is present in `docs` and every chunk has a
  matching embedding row in `doc_embeddings` with the right vector
  dimension.
- **Given** a populated corpus,
  **when** `RetrievalService.retrieve_docs(query="overdraft fee",
  top_k=3)` is called,
  **then** it returns at most 3 `DocumentChunk` records, sorted by
  cosine distance ascending.
- **Given** a populated corpus,
  **when** `RetrievalService.retrieve_complaints(query="late fee",
  product="Credit card", narrative_keyword="late fee")` is
  called,
  **then** it returns up to 10 `ComplaintRow` records that match
  the filters (ILIKE on `narrative` for the keyword), sorted by
  `date_received` desc.

---

## Entities

| Entity | Spec |
|---|---|
| `complaints_sample.csv` | Existing read-only artifact at `data/samples/`. |
| `raw_docs/*.txt` | Three existing read-only artifacts. Each contains 2 sections delimited by lines containing `--- 8< ---`. |
| `complaints` table | Postgres table mirroring the CSV columns. SQL in Root Architecture. |
| `docs` table | One row per chunk. `source_file`, `title`, `section`, `chunk_index`, `raw_text`. |
| `doc_embeddings` table | One row per chunk; `embedding vector(EMBEDDING_DIM)`. |
| `DocumentChunk` (Pydantic) | App-side projection of `docs` ⨝ `doc_embeddings`. |
| `ComplaintRow` (Pydantic) | App-side projection of `complaints`. |
| `RetrievalService` | Two methods only: `retrieve_docs`, `retrieve_complaints`. |

### Class diagram — TODO(trainee)

> Per the *SPDD discipline* norm, ship a `classDiagram` here that
> shows: tables (`complaints`, `docs`, `doc_embeddings`),
> Pydantic projections (`ComplaintRow`, `DocumentChunk`),
> `RetrievalService` and which tables it reads. Show the FK from
> `doc_embeddings.doc_id` → `docs.id`.

---

## Approach

### Design decisions

1. **Fixed-size chunking, not section-aware.** Split each `.txt`
   file into ~600-character chunks with ~100-character overlap.
   Yes, this ignores the `--- 8< ---` markers. Yes, that's the
   point. (Character splitting, not tokenizer-based; we want
   the chunker readable in 10-20 lines of Python.)
2. **Single-keyword ILIKE filter.** `retrieve_complaints` accepts
   one optional `narrative_keyword: str` — a single literal
   substring. No multi-keyword OR. No regex.
3. **Cosine distance ANN.** `retrieve_docs` runs
   `ORDER BY embedding <=> :query_vec` on `doc_embeddings`.
   `k` defaults to 5.
4. **One ingest entrypoint per corpus.**
   `data_pipelines/ingest_tables/ingest_public_data.py` for the CSV;
   `data_pipelines/ingest_docs/embed_starter_docs.py` for the docs.
   Both are idempotent (`UPSERT` on `complaint_id`; `DELETE+INSERT`
   on `(source_file, chunk_index)`).
5. **Service constructed in `app/api/main.py` lifespan.** Same
   pattern as `LLMService` from Task 1. Stored on
   `app.state.services.retrieval`.

### TODO(trainee) — Trade-offs accepted

> List **at least three** trade-offs your design makes. The shape
> "we accept X because Y, even though Z" works. Hint topics:
> chunking strategy, ILIKE performance, embedding model choice
> (768-dim vs 1536-dim), idempotency vs re-run cost.

---

## Structure

### File layout

```
data_pipelines/
├── ingest_tables/
│   ├── __init__.py
│   └── ingest_public_data.py     # CSV -> complaints table
├── ingest_docs/
│   ├── __init__.py
│   └── embed_starter_docs.py     # txt -> docs + doc_embeddings
├── schema/
│   └── 0001_create_tables.sql    # complaints, docs, doc_embeddings, pgvector
└── starter_corpus.py             # shared chunking + parsing helpers

app/services/
├── retrieval_service.py          # RetrievalService class
└── ...

app/core/
├── db.py                         # SQLAlchemy session factory; reads PG_DSN
└── ...
```

### Method signatures (the contract)

```python
# app/core/db.py
def make_engine(dsn: str) -> Engine: ...
def get_sessionmaker(engine: Engine) -> sessionmaker[Session]: ...
def ensure_pgvector_extension(engine: Engine) -> None: ...
def apply_schema(engine: Engine, sql_path: Path, *, embedding_dim: int) -> None: ...

# app/services/retrieval_service.py
class RetrievalService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        llm: LLMService,
        *,
        embedding_dim: int,
    ) -> None: ...

    async def retrieve_docs(
        self,
        query: str,
        *,
        top_k: int = 5,
        request_id: str | None = None,
    ) -> list[DocumentChunk]: ...

    async def retrieve_complaints(
        self,
        query: str,
        *,
        top_k: int = 10,
        product: str | None = None,
        narrative_keyword: str | None = None,
        request_id: str | None = None,
    ) -> list[ComplaintRow]: ...
```

> The `narrative_keyword: str | None` (singular, optional) shape is
> the v0 contract. **Do not change it.** Future tasks may evolve
> this signature; that evolution must follow the project's *SPDD
> discipline* norm (canvas first, then code), and is out of scope
> for this Task.
>
> The `query: str` parameter on `retrieve_complaints` is part of
> the v0 contract but is NOT used for filtering or ranking in v0.
> It is reserved for the v1 evolution path (a future task may add
> embedding-based complaint ranking). Log it; do not branch on
> it. Tests should not assert that `query` changes the result
> set.
>
> The `request_id: str | None = None` argument is the carrier for
> the structured-logging contract Task 1 introduced — every public
> service method takes one so the caller can propagate the ID
> without it leaking through arbitrary kwargs.

---

## Operations (strict execution order)

> The first 3 steps are pinned. Steps 4+ are **TODO(trainee)** —
> derive them from your Approach. Your mentor will sign off the
> full Operations list before you generate code.

1. **Apply the schema** in
   `data_pipelines/schema/0001_create_tables.sql`. Make it idempotent
   (`CREATE … IF NOT EXISTS`) so re-running is safe.
2. **Implement `app/core/db.py`** with the four helpers in
   *Method signatures*: `make_engine`, `get_sessionmaker`,
   `ensure_pgvector_extension`, and `apply_schema`. The
   `apply_schema` helper substitutes a `/* EMBEDDING_DIM */`
   placeholder so the same SQL works for both 768-d and 1536-d
   embeddings.
3. **Implement `data_pipelines/starter_corpus.py`** with a chunker
   helper (fixed-size with overlap) and a CSV reader that yields
   `dict`s in the canonical column order.

4. **TODO(trainee) — implement
   `data_pipelines/ingest_tables/ingest_public_data.py`** with an
   idempotent UPSERT on `complaint_id`.
5. **TODO(trainee) — implement
   `data_pipelines/ingest_docs/embed_starter_docs.py`** that
   chunks and embeds, then writes both `docs` and `doc_embeddings`
   in one transaction per file.
6. **TODO(trainee) — implement `RetrievalService`** for both
   methods. Use SQLAlchemy `text()` with bound params; never
   string-format SQL.
7. **TODO(trainee) — wire `RetrievalService` into
   `ServicesContainer`** (extend the dataclass from Task 1).
8. **TODO(trainee) — write tests**: a unit test for the chunker,
   a SQL-shape test for each `retrieve_*` method using a fixture
   loaded into the test DB.
9. **Update `README.md` *Data prep* section** with the two ingest
   commands plus the `complaints` row count and `docs` chunk count
   you observe after a fresh run. Drop a one-line "what you'll see"
   so a fresh trainee knows the expected scale.
10. **Verify** by running `pytest`, `ruff`, `mypy --strict`, and
    a manual `python -c "import asyncio; from app.api.main import …;
    print(asyncio.run(svc.retrieve_docs('overdraft', top_k=3)))"`.

---

## Norms

- All SQL goes through `text(...)` with bound parameters.
- Ingest scripts log every step (`event="ingest_csv_row"`,
  `event="embed_chunk"`, etc.) with row counts and durations.
- Both ingest scripts are idempotent.
- `RetrievalService` returns *typed* projections, never raw SQL
  rows.
- Embedding dim must equal `Settings.embedding_dim`. A mismatch
  is a hard fail at insert time.

---

## Safeguards

1. **No alternate vector store.** pgvector only.
2. **No alternate database.** Postgres only.
3. **No live CFPB scraping.** The starter CSV is the entire
   corpus.
4. **No silent dedup loss.** If two CSV rows share a
   `complaint_id`, `UPSERT` keeps the last; surface a warning log
   so the trainee sees the dedup count.
5. **No mutation of `data/samples/` or `data/raw_docs/`.** Read
   only.

---

> **Spec drift watch.** When your implementation diverges from
> this canvas (e.g. you find that the chunker needs to handle a
> trailing-whitespace case the spec didn't mention), edit this
> canvas FIRST in the same PR.

# Financial Helpdesk Agent

A Dockerised, LangGraph-based agent that answers consumer-finance questions
grounded in CFPB public data.

**Current stage: Week 4 — Prompts & conversation compression.** The `app`
container exposes `/healthz`, `/readyz`, and `POST /agent/query`. The LangGraph
flow combines parallel RAG retrieval, Scenario extraction, prompt-template
rendering, conversation-history compression, and LLM reasoning.

## Quickstart

```bash
cp .env.example .env
./auto/start.sh                      # docker compose up --build
curl http://localhost:8000/healthz   # → {"status": "ok"}
curl http://localhost:8000/readyz    # → 200 {"status":"ready",...} or 503 if the provider is unreachable
curl -X POST http://localhost:8000/agent/query \
  -H "Content-Type: application/json" \
  -d '{"question":"My bank charged an overdraft fee but my account never went negative"}'
```

`auto/start.sh` wraps `docker compose -f infra/docker-compose.yml up --build`.

## Project layout

```text
app/
  ├── api/main.py                # FastAPI entrypoint, request-id middleware, /healthz + /readyz + /agent/query
  ├── core/
  │   ├── config.py              # Settings (pydantic-settings) + cached get_settings()
  │   ├── graph.py               # LangGraph runner + history compression orchestration
  │   ├── logging.py             # configure_logging, request_id ContextVar, redaction, truncation
  │   ├── state.py               # AgentState TypedDict + domain model re-exports
  │   ├── exceptions.py          # LLMProviderError, LLMOutputValidationError
  │   └── services_container.py  # ServicesContainer (DI bundle)
  ├── services/
  │   ├── llm_client.py          # LLMHTTPClient (httpx wrapper, injectable transport)
  │   └── llm_service.py         # LLMService: complete / embed / check_liveness, retries
  └── tools/                     # Retrieval, Scenario, analysis, and synthesis tools
infra/                           # Dockerfile.app + docker-compose.yml
auto/                            # Local helper scripts (start.sh)
tests/                           # Unit/integration tests for config, graph, tools, API, and services
.spdd_specs/                     # SPDD specs (architecture + weekly tasks)
```

## Local development

Requires Python 3.11+ and [Poetry](https://python-poetry.org/).

```bash
poetry install --all-extras          # --all-extras pulls the dev group (pytest, ruff, mypy)
poetry run pytest -q                  # unit tests; no network/DB needed (httpx MockTransport)
poetry run ruff check .
poetry run mypy --strict --explicit-package-bases app
```

All three (pytest / ruff / mypy --strict) must pass before a PR. Tests
that need a live Postgres/provider are marked `network` and skipped by
default; run them with `poetry run pytest -m network`.

## Data prep (RAG v0 ingestion)

The starter corpus (`data/samples/complaints_sample.csv` and
`data/raw_docs/*.txt`) is already on disk. Two idempotent scripts load it
into Postgres + `pgvector`. The one-shot helper brings up the database,
drops any stale tables, and runs both scripts:

```bash
./auto/ingest.sh              # fresh rebuild (drops tables first)
./auto/ingest.sh --no-reset   # keep existing rows (idempotent UPSERT only)
```

Or run the steps by hand (the CSV script needs only Postgres; the docs
script also needs a running Ollama for embeddings):

```bash
docker compose -f infra/docker-compose.yml up -d db      # Postgres + pgvector
python -m data_pipelines.ingest_tables.ingest_public_data # CSV  -> complaints
python -m data_pipelines.ingest_docs.embed_starter_docs   # txt  -> docs + doc_embeddings
```

Reach for `--no-reset` on the helper (or the manual steps) only when you
want to layer onto existing rows; the default fresh rebuild also clears
any leftover rows a `pytest -m network` run seeded into the tables.

**What you'll see:** the CSV has 1,000 rows but only **400 unique
`complaint_id`s** (whole-row duplicates), so the idempotent UPSERT lands
**400 rows** in `complaints` and logs a `duplicates_collapsed=600`
warning — this is expected, not data loss. The docs script produces
**18 chunks** across the three files (naive 600-char/100-overlap
chunking), one `doc_embeddings` row per chunk. Both scripts are safe to
re-run.

### The canonical Ollama path

Ollama is the canonical local provider (`LLM_PROVIDER=ollama`); OpenRouter is
an optional escape hatch. Install Ollama, then pull the models referenced in
`.env`:

```bash
ollama pull gemma3:27b          # OLLAMA_CHAT_MODEL (synthesis)
ollama pull qwen3.5:4b          # OLLAMA_OPS_MODEL (tagger / safety / judge, later weeks)
ollama pull nomic-embed-text    # EMBEDDING_MODEL (768-dim, see EMBEDDING_DIM)
curl http://localhost:11434/api/tags   # confirm the daemon is up (this is what /readyz probes)
```

To use OpenRouter instead: set `LLM_PROVIDER=openrouter` and `OPENROUTER_API_KEY`
in `.env`. `Settings` raises at startup if the key is missing under that provider.

### Reaching Ollama from inside Docker

Inside the `app` container, `localhost` means the container — not your host —
so `OLLAMA_BASE_URL=http://localhost:11434` cannot reach a host-side Ollama and
`/readyz` returns `503`. On Docker Desktop (macOS/Windows) point the container
at the host gateway instead:

```yaml
# infra/docker-compose.yml → services.app
environment:
  - OLLAMA_BASE_URL=http://host.docker.internal:11434
extra_hosts:
  - "host.docker.internal:host-gateway"   # required on Linux; no-op on Docker Desktop
```

Also ensure Ollama listens beyond loopback (`OLLAMA_HOST=0.0.0.0:11434`) so the
container's connection (arriving via the host gateway IP) is accepted. Running
the app directly with `uvicorn` on the host needs neither change — `localhost`
works there.

## Health endpoints

| Endpoint       | Returns                                                                               | Notes                                                                                                                                                             |
| -------------- | ------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /healthz` | `200 {"status": "ok"}`                                                                | Pure liveness; touches no dependency.                                                                                                                             |
| `GET /readyz`  | `200 {"status":"ready","chat_provider":...,"embedding_provider":...}` / `503 {"error_code","message","request_id"}` | Single short-timeout probe of the configured chat provider; **no retry**. |

Every response echoes an `X-Request-Id` header (reused from the request or a
fresh UUIDv4), bound into the logging ContextVar for the request's lifetime.

## Agent Orchestration (Week 4)

Graph topology (current baseline):

```text
START
  -> ingest_input
  -> history_compression_phase
  -> scenario_phase
  -> retrieve_phase
  -> analysis_phase
  -> synthesis_phase
  -> END
```

`scenario_phase` extracts and validates intent with one bounded retry before
retrieval. `retrieve_phase` then runs document and Scenario-filtered structured
complaint retrieval in parallel. `analysis_phase` creates grounded analysis
notes. Prompt text is versioned under
`app/core/prompts/` and rendered through `PromptService` with Jinja
`StrictUndefined`. Structured extractions are constrained with the Pydantic
JSON Schema at the provider boundary (`format` for Ollama, strict
`response_format=json_schema` for compatible OpenAI-style providers) and
validated again locally. Qwen falls back to provider JSON mode plus the same
local Pydantic validation. Safety models are defined, but runtime safety
enforcement is intentionally reserved for the later safety task.

Quick endpoint example:

```bash
curl -X POST http://localhost:8000/agent/query \
  -H "Content-Type: application/json" \
  -d '{"question":"My bank charged an overdraft fee but my account never went negative"}'
```

Run a fast smoke cycle before PRs:

```bash
./scripts/smoke.sh
```

## Logging

`LOG_FORMAT=json` emits one JSON object per record with at least `timestamp`,
`level`, `request_id`, `event` (and `duration_ms` where applicable);
`LOG_FORMAT=text` emits a readable key-value line. Secrets (`Authorization`,
`*_api_key`, …) are redacted at the logging layer and prompts are truncated to
500 chars with a `_truncated: true` flag — never log raw provider headers.

## Configuration

All environment variables are declared in `.env.example`; copy it to `.env`.
Key settings: `CHAT_PROVIDER` (default `ollama`), `EMBEDDING_PROVIDER`, `PG_DSN`, `LOG_FORMAT`,
`OPENROUTER_API_KEY` (required only under `openrouter`), and the
Ollama/embedding model fields. `config.py` is the only module permitted to read
the environment; everything else receives a `Settings` instance. `.env` is
git-ignored and never committed.

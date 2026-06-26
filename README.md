# Financial Helpdesk Agent

A Dockerised, LangGraph-based agent that answers consumer-finance questions
grounded in CFPB public data.

**Current stage: Week 0 — environment only.** The `app` container exposes a
single `/healthz` probe; the `db` container runs PostgreSQL with `pgvector`
but is empty. There is no agent yet.

## Quickstart

```bash
cp .env.example .env
./auto/start.sh                      # docker compose up --build
curl http://localhost:8000/healthz   # → {"status": "ok"}
```

`auto/start.sh` wraps `docker compose -f infra/docker-compose.yml up --build`.

## Project layout

```text
app/                    # FastAPI app (just /healthz at Week 0)
  ├── api/main.py       # FastAPI entrypoint + /healthz
  ├── core/config.py    # Settings (pydantic-settings)
  ├── services/         # (empty — Week 1+)
  └── tools/            # (empty — Week 3+)
infra/                  # Dockerfile.app + docker-compose.yml
auto/                   # Local helper scripts (start.sh)
tests/                  # Pytest suites (test_health.py)
.spdd_specs/            # SPDD specs (architecture + weekly tasks)
```

## Local development

```bash
poetry install --all-extras   # --all-extras pulls the dev group (pytest, ruff, mypy)
poetry run ruff check .
poetry run pytest -q
poetry run mypy app
```

## Health endpoints

| Endpoint | Returns | Notes |
|---|---|---|
| `GET /healthz` | `200 {"status": "ok"}` | Liveness only; does not check the database. |

## Configuration

All environment variables are declared in `.env.example`; copy it to `.env`.
Key settings: `LLM_PROVIDER` (default `ollama`), `PG_DSN`, `LOG_FORMAT`, and
the Ollama/embedding model fields. `.env` is git-ignored and never committed.

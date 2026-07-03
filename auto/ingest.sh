#!/usr/bin/env bash
# Prepare the RAG v0 corpus: bring up Postgres, drop any stale tables,
# then ingest the CSV (complaints) and embed the docs (docs + embeddings).
#
# Run from anywhere; paths resolve relative to the repo root.
#
#   auto/ingest.sh              # fresh rebuild (drops tables first)
#   auto/ingest.sh --no-reset   # keep existing rows (idempotent UPSERT only)
#
# The embed step needs a running Ollama with the embedding model pulled
# (ollama pull nomic-embed-text); the CSV step needs only Postgres.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

COMPOSE="docker compose -f infra/docker-compose.yml"
RESET=1
for arg in "$@"; do
  case "$arg" in
    --no-reset) RESET=0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

echo "==> Starting Postgres (waiting for healthy)..."
$COMPOSE up -d --wait db

if [[ "$RESET" -eq 1 ]]; then
  echo "==> Dropping stale tables (fresh rebuild)..."
  # DROP+recreate rather than TRUNCATE: safe on a fresh DB, clears any
  # leftover test-fixture rows, and lets the ingest scripts rebuild the
  # schema at the current EMBEDDING_DIM.
  $COMPOSE exec -T db psql -U app -d app \
    -c "DROP TABLE IF EXISTS doc_embeddings, docs, complaints CASCADE;"
fi

echo "==> Ingesting complaints CSV -> complaints table..."
poetry run python -m data_pipelines.ingest_tables.ingest_public_data

echo "==> Embedding docs -> docs + doc_embeddings (needs Ollama)..."
poetry run python -m data_pipelines.ingest_docs.embed_starter_docs

echo "==> Row counts:"
$COMPOSE exec -T db psql -U app -d app -c \
  "SELECT 'complaints' AS table, count(*) FROM complaints
   UNION ALL SELECT 'docs', count(*) FROM docs
   UNION ALL SELECT 'doc_embeddings', count(*) FROM doc_embeddings;"

echo "==> Done."

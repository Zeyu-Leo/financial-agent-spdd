#!/usr/bin/env bash
# Bring up the full local stack (app + db) and rebuild images.
# Run from anywhere; paths resolve relative to the repo root.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

docker compose -f infra/docker-compose.yml up --build

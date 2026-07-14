#!/usr/bin/env bash
# Task 3 smoke checks: health, readiness, and agent query happy path.
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"

pass() {
  echo "PASS: $1"
}

fail() {
  echo "FAIL: $1"
  exit 1
}

check_healthz() {
  local out
  if ! out="$(curl -fsS "$BASE_URL/healthz")"; then
    fail "/healthz request failed"
  fi
  echo "$out" | grep -q '"status":"ok"' || fail "/healthz payload mismatch"
  pass "/healthz"
}

check_readyz() {
  local out
  if ! out="$(curl -fsS "$BASE_URL/readyz")"; then
    fail "/readyz request failed"
  fi
  echo "$out" | grep -q '"status":"ready"' || fail "/readyz payload mismatch"
  pass "/readyz"
}

check_agent_query() {
  local out
  if ! out="$(curl -fsS -X POST "$BASE_URL/agent/query" \
      -H "Content-Type: application/json" \
      -d '{"question":"My bank charged an overdraft fee but my account never went negative"}')"; then
    fail "/agent/query request failed"
  fi
  echo "$out" | grep -q '"final_answer":"' || fail "/agent/query missing final_answer"
  echo "$out" | grep -q '"retrieved_doc_ids":\[' || fail "/agent/query missing retrieved_doc_ids"
  pass "/agent/query"
}

main() {
  check_healthz
  check_readyz
  check_agent_query
}

main "$@"

"""Shared corpus helpers: the RAG v0 chunker and the complaints CSV reader.

Both ingest scripts import from here so the naive chunking strategy and
the canonical column order live in exactly one place.

The chunker is deliberately a flat fixed-size character splitter — no
section awareness, no sentence/tokenizer splitting. It ignores the
``--- 8< ---`` markers in the raw docs on purpose; section-aware
chunking is a later task's deliverable (RAG v1).
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

# Canonical CFPB column order — matches complaints_sample.csv, the
# `complaints` table, and the ComplaintRow projection.
CANONICAL_COLUMNS: tuple[str, ...] = (
    "complaint_id",
    "date_received",
    "product",
    "sub_product",
    "issue",
    "sub_issue",
    "company",
    "state",
    "narrative",
    "company_response",
    "consumer_disputed",
)

DEFAULT_CHUNK_SIZE = 600
DEFAULT_CHUNK_OVERLAP = 100


def chunk_text(
    text: str,
    *,
    size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split ``text`` into fixed-size character windows with overlap.

    Windows are ``size`` characters wide and advance by ``size - overlap``
    each step, so consecutive chunks share ``overlap`` characters. Empty
    input yields ``[]``; input shorter than ``size`` yields a single chunk.
    """
    if size <= 0:
        raise ValueError("chunk size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be in the range [0, size)")
    if not text:
        return []
    step = size - overlap
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        # Stop once this window already reaches the end, so we never emit
        # a trailing chunk that lies entirely within the prior overlap.
        if end >= len(text):
            break
        start += step
    return chunks


def iter_complaint_rows(csv_path: Path) -> Iterator[dict[str, str]]:
    """Yield one dict per CSV row, keyed by ``CANONICAL_COLUMNS``.

    Values are returned as raw strings (no normalisation — Safeguard);
    missing cells become empty strings. Duplicate ``complaint_id`` rows
    are yielded as-is; deduplication is the ingest script's job (UPSERT).
    """
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield {col: (row.get(col) or "") for col in CANONICAL_COLUMNS}

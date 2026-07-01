"""Build the starter consumer-complaints CSV used by the rest of the project.

This script is intentionally the *only* code you need at this stage. It does
exactly one job: pull a small, balanced slice of CFPB Consumer Complaint
Database rows from the public API and write a single CSV to disk.

It is **not** part of the agent. It is a one-shot data-prep tool whose output
unblocks every later week of the learning plan.

What it produces
----------------
``data/samples/complaints_sample.csv`` containing roughly 1,000 rows with:

- ``complaint_id``           - stable identifier from CFPB
- ``date_received``          - ISO date the consumer submitted the complaint
- ``product``                - one of the four selected categories
- ``sub_product``            - finer category from CFPB's taxonomy
- ``issue``                  - top-level issue label
- ``sub_issue``              - finer issue label
- ``company``                - responding company
- ``state``                  - 2-letter US state code (may be empty)
- ``narrative``              - free-text complaint description
- ``company_response``       - how the company resolved it
- ``consumer_disputed``      - whether the consumer disputed the response

Why this design
---------------
The plan stratifies across four products on purpose. The CFPB database is
dominated by credit-reporting complaints (over 80%); a naive random sample
would not exercise the agent's retrieval over a realistic mix of finance
topics. Picking four distinct, narrative-rich products keeps the dataset
small enough to run on a laptop while still letting later weeks build
metadata filters and hybrid search that *actually matter*.

How to run
----------
::

    python -m data_pipelines.ingest_tables.build_starter_sample

It only needs ``httpx`` and ``pandas``. No database, no Docker, no agent code.

Important constraints (from the project spec)
---------------------------------------------
- Fail loudly. If the API returns fewer rows than requested for a given
  product, raise rather than silently writing an unbalanced file.
- Do not normalise, deduplicate, or LLM-tag anything yet. Week 6 of the
  learning plan is *deliberately* the place where curation is taught, after
  evaluation has shown the v0 quality cost of skipping it.
- Do not download the multi-GB bulk export. Pagination via ``frm`` and
  ``size`` is what keeps this safe to run anywhere.
"""

from __future__ import annotations

import csv
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

CFPB_SEARCH_URL = (
    "https://www.consumerfinance.gov/data-research/consumer-complaints/"
    "search/api/v1/"
)

# Page size for each API call. The API caps page size, and small pages keep
# the response time predictable. 100 is a good compromise between throughput
# and per-request stability on a residential connection.
PAGE_SIZE = 100

# Per-product target. Four products at 250 rows each yields a stratified
# sample of about 1,000 rows. Adjust here, not in dozens of places later.
ROWS_PER_PRODUCT = 250

# Date window. Keeping this to one calendar year produces a corpus that is
# both recent (so language and issue labels match what users would ask
# today) and stable (so re-running the script tomorrow gives a near-identical
# slice).
DATE_RECEIVED_MIN = "2024-01-01"
DATE_RECEIVED_MAX = "2024-12-31"

# Four products chosen for breadth of consumer-finance scenarios while
# avoiding the dominant credit-reporting category which would skew the mix.
# These names must match CFPB's product taxonomy exactly; mismatched names
# silently return zero rows.
PRODUCTS: tuple[str, ...] = (
    "Credit card",
    "Checking or savings account",
    "Mortgage",
    "Debt collection",
)

# CFPB source field name -> our output column name. Renaming
# ``complaint_what_happened`` to ``narrative`` matches how every later step
# of the project (chunking, RAG, evaluation) refers to it.
FIELD_MAP: dict[str, str] = {
    "complaint_id": "complaint_id",
    "date_received": "date_received",
    "product": "product",
    "sub_product": "sub_product",
    "issue": "issue",
    "sub_issue": "sub_issue",
    "company": "company",
    "state": "state",
    "complaint_what_happened": "narrative",
    "company_response": "company_response",
    "consumer_disputed": "consumer_disputed",
}


@dataclass(frozen=True)
class FetchPlan:
    """Single fetch task: one product, one row target, one date window."""

    product: str
    target_rows: int
    date_min: str
    date_max: str


class CFPBClient:
    """Thin wrapper around the CFPB search API.

    The wrapper exists for two coaching reasons:

    1. It puts every header, query parameter, and pagination rule in one
       place, so a junior reader can see the full request contract.
    2. It defines a clear error contract: any non-2xx response, any
       unexpected payload shape, or any short page raises. The script
       should *never* silently move on after an HTTP failure.
    """

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def iter_rows(self, plan: FetchPlan) -> Iterator[dict[str, Any]]:
        """Yield raw ``_source`` records for one ``FetchPlan`` until target."""

        yielded = 0
        offset = 0
        while yielded < plan.target_rows:
            page_size = min(PAGE_SIZE, plan.target_rows - yielded)
            params: dict[str, str] = {
                "size": str(page_size),
                "frm": str(offset),
                "no_aggs": "true",
                "no_highlight": "true",
                # ``has_narrative=true`` is the single most important filter:
                # without a narrative there is nothing for RAG to chunk on.
                "has_narrative": "true",
                "date_received_min": plan.date_min,
                "date_received_max": plan.date_max,
                "product": plan.product,
                # Note: we deliberately do NOT pass ``format=json``. The API
                # spec says any ``format`` value disables ``frm``/``size``
                # pagination and turns the response into a download stream.
                # The ``Accept`` header is enough to get JSON back.
            }
            response = self._client.get(
                CFPB_SEARCH_URL,
                params=params,
                headers={"Accept": "application/json"},
                timeout=30.0,
            )
            response.raise_for_status()

            payload = response.json()
            hits_block = payload.get("hits")
            if not isinstance(hits_block, dict):
                raise RuntimeError(
                    "CFPB response missing 'hits' object; payload shape "
                    "changed and the script needs updating."
                )
            hits = hits_block.get("hits")
            if not isinstance(hits, list):
                raise RuntimeError(
                    "CFPB response 'hits.hits' is not a list; "
                    "payload shape changed."
                )
            if not hits:
                # Server says there are no more matching rows. We stop here
                # rather than retrying; the caller decides whether the
                # under-fetch is acceptable.
                return

            for hit in hits:
                source = hit.get("_source") if isinstance(hit, dict) else None
                if not isinstance(source, dict):
                    raise RuntimeError(
                        "CFPB hit missing '_source' object; payload shape "
                        "changed."
                    )
                yield source
                yielded += 1
                if yielded >= plan.target_rows:
                    return

            offset += page_size

            # Be polite: short pause between pages so a single laptop is not
            # hammering a public API. The CFPB API has no documented rate
            # limit but courtesy keeps the door open.
            time.sleep(0.25)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _output_path() -> Path:
    return _project_root() / "data" / "samples" / "complaints_sample.csv"


def _select_columns(source: dict[str, Any]) -> dict[str, Any]:
    """Return only the fields we keep, renamed to our output schema.

    Returns a dict with the *output* column names, so callers don't have to
    remember CFPB's own field names.
    """

    return {output_name: source.get(api_name) for api_name, output_name in FIELD_MAP.items()}


def _normalise_date(value: str | None) -> str | None:
    """Trim CFPB's ``2024-05-08T12:00:00-05:00`` to ``2024-05-08``.

    This is the *only* normalisation we do at this stage. It is safe because
    CFPB only reports day-level resolution; the time part is always noon and
    carries no real information. Removing it keeps the CSV human-readable
    and avoids confusing the eye when scanning the file.
    """

    if not isinstance(value, str) or not value:
        return value
    return value.split("T", 1)[0]


def fetch_sample() -> list[dict[str, Any]]:
    """Fetch the full stratified sample as a list of output-shaped dicts."""

    plans = [
        FetchPlan(
            product=product,
            target_rows=ROWS_PER_PRODUCT,
            date_min=DATE_RECEIVED_MIN,
            date_max=DATE_RECEIVED_MAX,
        )
        for product in PRODUCTS
    ]

    rows: list[dict[str, Any]] = []
    with httpx.Client(http2=False, follow_redirects=True) as client:
        api = CFPBClient(client)
        for plan in plans:
            print(f"[fetch] product={plan.product!r} target={plan.target_rows}")
            collected = 0
            for source in api.iter_rows(plan):
                row = _select_columns(source)
                row["date_received"] = _normalise_date(row.get("date_received"))
                rows.append(row)
                collected += 1
            print(f"[fetch] product={plan.product!r} collected={collected}")
            if collected < plan.target_rows:
                # Success-or-die: the spec promises a balanced sample; if the
                # API can't satisfy the plan we stop here so the user
                # decides whether to widen the date window or drop a product.
                raise RuntimeError(
                    f"Only {collected} rows available for product "
                    f"{plan.product!r} in window "
                    f"{plan.date_min}..{plan.date_max}, expected "
                    f"{plan.target_rows}. Widen the window or pick a "
                    f"different product."
                )
    return rows


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    """Write ``rows`` to ``path`` with a stable column order."""

    if not rows:
        raise RuntimeError("Refusing to write an empty CSV.")

    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(FIELD_MAP.values())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict[str, Any]], path: Path) -> None:
    """Print a small balance check so the human can sanity-check the slice."""

    by_product: dict[str, int] = {}
    for row in rows:
        product = row.get("product") or "<missing>"
        by_product[product] = by_product.get(product, 0) + 1

    dates = sorted(
        d for d in (row.get("date_received") for row in rows) if isinstance(d, str)
    )
    size_kb = path.stat().st_size / 1024 if path.exists() else 0.0

    print()
    print(f"Wrote {len(rows)} rows to {path} ({size_kb:.1f} KiB)")
    print("Rows per product:")
    for product, count in sorted(by_product.items()):
        print(f"  {count:>4}  {product}")
    if dates:
        print(f"Date range: {dates[0]} -> {dates[-1]}")


def main() -> int:
    target_path = _output_path()
    print(f"Building starter complaint sample at {target_path}")
    rows = fetch_sample()
    write_csv(rows, target_path)
    print_summary(rows, target_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

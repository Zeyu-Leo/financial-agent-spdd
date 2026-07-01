"""Build the starter consumer-finance reference docs used by RAG v0.

This script is the document-side counterpart to ``build_starter_sample.py``.
It pulls a small, hand-picked set of CFPB "Ask CFPB" Q&A pages and writes
clean ``.txt`` files into ``data/raw_docs/``. These files become the RAG
corpus that the agent retrieves *from* in later weeks.

What it produces
----------------
Three text files in ``data/raw_docs/``:

- ``overdraft_faq.txt``               - bank account overdraft basics
- ``credit_card_fees.txt``            - APR, grace periods, interest mechanics
- ``mortgage_servicing_policy.txt``   - servicer vs lender, escrow accounts

Each file follows the same simple structure::

    Title: <human-readable topic>
    Sources:
      - <url 1>
      - <url 2>

    --- 8< ---  <question 1>
    <last reviewed: <date>>
    <body text>

    --- 8< ---  <question 2>
    ...

The ``--- 8< ---`` markers are intentionally chosen so the Week 6 chunker
can split on section boundaries instead of fixed character windows.

Why this design
---------------
The capstone spec deliberately forbids live PDF/HTML *scraping* during the
early weeks because PDF/HTML extraction is the kind of work that silently
swallows two weeks of project time. This script is the safe escape hatch:
a one-shot, mentor-curated list of stable URLs, fetched once and saved as
plain text. After this script runs, the rest of the project never touches
the network for documents again.

The script extracts content using a deliberately small regex slice rather
than pulling in BeautifulSoup. The CFPB Q&A page template is stable enough
that this works, and keeping the dependency surface to ``httpx`` only is a
coaching choice: junior readers see exactly which bytes flow in and which
flow out.

How to run
----------
::

    python -m data_pipelines.ingest_docs.fetch_starter_docs

Important constraints (from the project spec)
---------------------------------------------
- Fail loudly if any URL returns non-200, returns unexpected HTML, or
  produces an empty body. We do *not* silently write half-empty files.
- Do not normalise the prose. CFPB's "Tip:" callouts and warning boxes are
  real consumer guidance and should make it into RAG. The only thing we
  drop is the page's English/Spanish language switcher and the related-
  questions footer, both of which are CFPB site chrome and not consumer
  finance content.
- Do not extend the URL list at runtime. Mentor-curated, period. If the
  team needs broader coverage, the conversation belongs in the spec, not
  in this script.
"""

from __future__ import annotations

import html
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

# Per-topic source set. The coaching point: each topic has *two* URLs, so
# any single broken page produces a clear, localised error rather than
# silently truncating one topic's coverage. Picking exactly two also
# matches the spec's "3-5 clean .txt files of 500-ish words each" goal
# without us needing to chase length on a single short Q&A.
TOPIC_SOURCES: dict[str, tuple[tuple[str, str], ...]] = {
    "overdraft_faq.txt": (
        (
            "Overdraft fundamentals",
            "https://www.consumerfinance.gov/ask-cfpb/what-is-an-overdraft-en-1035/",
        ),
        (
            "What to do when charged an overdraft fee",
            "https://www.consumerfinance.gov/ask-cfpb/what-can-i-do-if-my-bank-charged-me-a-fee-for-overdrawing-my-account-en-1037/",
        ),
    ),
    "credit_card_fees.txt": (
        (
            "Credit card interest rates and APR",
            "https://www.consumerfinance.gov/ask-cfpb/what-is-a-credit-card-interest-rate-what-does-apr-mean-en-44/",
        ),
        (
            "Credit card grace periods",
            "https://www.consumerfinance.gov/ask-cfpb/what-is-a-grace-period-en-47/",
        ),
    ),
    "mortgage_servicing_policy.txt": (
        (
            "Mortgage lender vs mortgage servicer",
            "https://www.consumerfinance.gov/ask-cfpb/whats-the-difference-between-a-mortgage-lender-and-a-mortgage-servicer-en-198/",
        ),
        (
            "Mortgage escrow and impound accounts",
            "https://www.consumerfinance.gov/ask-cfpb/what-is-an-escrow-or-impound-account-en-140/",
        ),
    ),
}

# Title-cased human label per output file, used in the file header.
TOPIC_TITLES: dict[str, str] = {
    "overdraft_faq.txt": "Overdraft basics and consumer rights",
    "credit_card_fees.txt": "Credit card fees, interest, and grace periods",
    "mortgage_servicing_policy.txt": "Mortgage servicing, escrow, and accountability",
}

# Minimum body length in characters per fetched page. The CFPB's shortest
# Q&A pages are ~400 chars; anything below 200 is almost certainly a
# template error or a redirect we should fail on.
MIN_BODY_CHARS = 200

SECTION_DELIMITER = "--- 8< ---"


@dataclass(frozen=True)
class FetchedSection:
    """One Q&A page after extraction and cleaning."""

    section_title: str
    source_url: str
    question: str
    last_reviewed: str | None
    body: str


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _output_dir() -> Path:
    return _project_root() / "data" / "raw_docs"


# Match the page's <main class="ask-cfpb-page--answer ...">..</main> wrapper.
# Two patterns because the class list ordering is not contractual.
_MAIN_RE = re.compile(
    r'<main\b[^>]*\bask-cfpb-page--answer\b[^>]*>(?P<inner>.*?)</main>',
    re.DOTALL,
)
_H1_RE = re.compile(r'<h1\b[^>]*>(?P<text>.*?)</h1>', re.DOTALL)
_LAST_REVIEWED_RE = re.compile(
    r'last\s*reviewed:\s*([A-Z]{3,9}\s+\d{1,2},?\s*\d{4})',
    re.IGNORECASE,
)
# CFPB's footer always begins with this exact H2 (the apostrophe is a
# Unicode right single quote U+2019, hence the explicit alternation).
_FOOTER_RE = re.compile(
    r"<h2\b[^>]*>\s*Don[\u2019']t\s+see\s+what\s+you",
    re.IGNORECASE,
)
# Tags we discard wholesale before stripping the rest. Scripts and styles
# only; we keep nav/aside *content* removal to the boilerplate cut, not to
# tag-level filtering, because the answer prose itself sometimes lives
# inside <aside class="o-tip"> "Tip" callouts that are real consumer
# guidance, not chrome.
_DROP_TAGS_RE = re.compile(
    r'<(script|style)\b[^>]*>.*?</\1>',
    re.DOTALL | re.IGNORECASE,
)
_TAG_RE = re.compile(r'<[^>]+>')
_LANGUAGE_SWITCHER_RE = re.compile(
    r'^\s*English\s*\n\s*Espa[nñ]ol\s*\n+',
    re.IGNORECASE,
)


def _strip_tags(html_fragment: str) -> str:
    text = _DROP_TAGS_RE.sub('', html_fragment)
    text = _TAG_RE.sub('', text)
    text = html.unescape(text)
    return text


def _normalise_whitespace(text: str) -> str:
    # Collapse runs of spaces/tabs but preserve paragraph breaks.
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\s*\n\s*', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _extract(section_title: str, source_url: str, html_text: str) -> FetchedSection:
    main_match = _MAIN_RE.search(html_text)
    if not main_match:
        raise RuntimeError(
            f"CFPB page at {source_url} did not contain the expected "
            "<main class='ask-cfpb-page--answer'> wrapper. The page "
            "template may have changed; the URL list needs review."
        )
    main_inner = main_match.group("inner")

    h1_match = _H1_RE.search(main_inner)
    if not h1_match:
        raise RuntimeError(
            f"CFPB page at {source_url} did not contain an <h1>. The page "
            "template may have changed."
        )
    question = _normalise_whitespace(_strip_tags(h1_match.group("text")))

    footer_match = _FOOTER_RE.search(main_inner)
    if not footer_match:
        raise RuntimeError(
            f"CFPB page at {source_url} did not contain the related-"
            "questions footer; the cut point for body extraction is "
            "missing. The page template may have changed."
        )

    body_html = main_inner[h1_match.end(): footer_match.start()]
    body_text = _normalise_whitespace(_strip_tags(body_html))
    body_text = _LANGUAGE_SWITCHER_RE.sub('', body_text)
    body_text = body_text.strip()

    if len(body_text) < MIN_BODY_CHARS:
        raise RuntimeError(
            f"CFPB page at {source_url} produced only {len(body_text)} "
            f"characters of body text (minimum: {MIN_BODY_CHARS}). The "
            "extraction selectors may need updating."
        )

    last_reviewed_match = _LAST_REVIEWED_RE.search(html_text)
    last_reviewed = last_reviewed_match.group(1) if last_reviewed_match else None

    return FetchedSection(
        section_title=section_title,
        source_url=source_url,
        question=question,
        last_reviewed=last_reviewed,
        body=body_text,
    )


def _fetch(client: httpx.Client, url: str) -> str:
    response = client.get(
        url,
        headers={
            # A descriptive UA is good citizenship on public APIs and helps
            # if the CFPB ever needs to identify abusive bots.
            "User-Agent": (
                "financial-agent-capstone/0.0.0 (data prep; "
                "https://www.consumerfinance.gov/data-research/)"
            ),
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=20.0,
    )
    response.raise_for_status()
    return response.text


def _format_file(file_name: str, sections: list[FetchedSection]) -> str:
    title = TOPIC_TITLES[file_name]
    lines: list[str] = []
    lines.append(f"Title: {title}")
    lines.append("Sources:")
    for section in sections:
        lines.append(f"  - {section.source_url}")
    lines.append("")

    for section in sections:
        lines.append(f"{SECTION_DELIMITER}  {section.section_title}")
        lines.append(f"Question: {section.question}")
        if section.last_reviewed:
            lines.append(f"Last reviewed: {section.last_reviewed}")
        lines.append("")
        lines.append(section.body)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def fetch_all() -> dict[str, list[FetchedSection]]:
    """Return a mapping of output file name -> ordered list of sections."""

    out: dict[str, list[FetchedSection]] = {file_name: [] for file_name in TOPIC_SOURCES}
    with httpx.Client(follow_redirects=True) as client:
        for file_name, sources in TOPIC_SOURCES.items():
            for section_title, source_url in sources:
                print(f"[fetch] {file_name} <- {source_url}")
                html_text = _fetch(client, source_url)
                section = _extract(section_title, source_url, html_text)
                out[file_name].append(section)
                # Be polite between requests on a public site.
                time.sleep(0.5)
    return out


def write_files(grouped: dict[str, list[FetchedSection]], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for file_name, sections in grouped.items():
        if not sections:
            raise RuntimeError(
                f"No sections were collected for {file_name}; refusing "
                "to write an empty file."
            )
        target = output_dir / file_name
        target.write_text(_format_file(file_name, sections), encoding="utf-8")
        written[file_name] = target
    return written


def print_summary(written: dict[str, Path]) -> None:
    print()
    print(f"Wrote {len(written)} reference docs to {written[next(iter(written))].parent}:")
    for file_name in sorted(written):
        path = written[file_name]
        text = path.read_text(encoding="utf-8")
        word_count = len(text.split())
        print(f"  {word_count:>4} words  {file_name}  ({path.stat().st_size} B)")


def main() -> int:
    print(f"Fetching CFPB starter docs into {_output_dir()}")
    grouped = fetch_all()
    written = write_files(grouped, _output_dir())
    print_summary(written)
    return 0


if __name__ == "__main__":
    sys.exit(main())

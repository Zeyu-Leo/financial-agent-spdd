# Task 5 — Evaluation (REASONS Canvas, trainee edition)

> **Trainee-edition posture.** This canvas describes the FIRST
> offline evaluation pipeline. The destination state in
> `Task_5_Evaluation.md` includes refinements (judge-stability
> repeats, comparison reports, threshold tuning) that emerged from
> the rehearsal; you ship the FIRST version of the evaluation
> pipeline and discover the stability problems yourself. Sections marked **TODO(trainee)**
> are the work you complete.
>
> **Maps to:** Learning Plan Week 5 — *Evaluation, Tracing &
> CI/CD*.
> **Depends on:** `Task_4_Prompts.trainee.md`.
> **Unblocks:** `Task_6_DataQuality.trainee.md`, `Task_7_Safety.trainee.md`.

---

## Requirements

### Analysis context

**Domain keywords scanned:** offline evaluation, LLM-as-judge,
scenarios YAML, faithfulness, task_success, observability,
OTel tracing, threshold gate, CI. **Existing artifacts:** the
four-node agent (Task 3), the prompt templates (Task 4), the
FastAPI endpoint. **Prior tasks read:** Tasks 0–4.

**Strategic direction:** a 3-step Unix-y CLI pipeline:
`batch → judge → compare`. Scenarios are version-controlled
YAML, runs are JSONL, judged outputs are JSONL with extra
columns, reports are markdown. The judge is an LLM with a
fixed rubric prompt.

**TODO(trainee) — Risks noticed.** List **at least three** risks
specific to LLM-as-judge evaluation. Hint domains: judge
non-determinism even at temperature 0, judge bias on long
evidence, threshold gate masking real regressions, scenario
coverage vs corpus characteristics.

### Why this task exists

We have a working agent. We don't yet have a way to know
whether a code or prompt change made it better or worse. Task 5
ships the offline evaluation pipeline that turns that question
into a measurable answer.

### Acceptance criteria (Given/When/Then)

- **Given** `data_pipelines/eval/test_scenarios.yaml` containing
  ≥10 functional scenarios (each with `id`, `user_question`,
  `tags`, optional `notes`, `category: functional`),
  **when** `python -m data_pipelines.eval.run_agent_batch
  --scenarios … --out runs/<ts>.jsonl` is run,
  **then** every scenario produces one JSONL line with at
  minimum `scenario_id`, `request_id`, `final_answer`,
  `retrieved_doc_ids`, `retrieved_complaint_ids`,
  `analysis_notes`, `latency_ms`.
- **Given** a fresh JSONL of run records,
  **when** `python -m data_pipelines.eval.llm_as_judge
  --in runs/<ts>.jsonl --out runs/<ts>.judged.jsonl` is run,
  **then** every line gains
  `faithfulness_score`, `task_success_score`,
  `safety_handling_score` (each in `[0.0, 1.0]`), a `notes`
  string, and a `failure_source_label` from the canonical enum.
- **Given** a judged JSONL,
  **when** `python -m data_pipelines.eval.report --in
  runs/<ts>.judged.jsonl --out reports/<ts>.md` is run,
  **then** the report contains average scores overall and
  per-tag plus a per-scenario table with score, label, and a
  one-line `notes` excerpt.
- **Given** any failed scenario,
  **when** the judged JSONL is inspected,
  **then** the `failure_source_label` is one of
  `{retrieval_miss, bad_chunk_boundary, missing_metadata,
  csv_field_noise, prompt_or_reasoning_issue,
  safety_policy_gap}`.
- **Given** the agent runs in production-like conditions,
  **when** `LANGSMITH_API_KEY` (or `PHOENIX_COLLECTOR_ENDPOINT`)
  is set,
  **then** every `/agent/query` call emits a trace whose root
  span carries the `request_id`.

---

## Entities

| Entity | Spec |
|---|---|
| `test_scenarios.yaml` | Canonical scenario set. List of records: `id`, `user_question`, `tags`, optional `notes`, `category` (`functional` only at this stage). |
| Run record | Single JSONL line per scenario. |
| Judged record | Run record extended with the four score fields + `failure_source_label`. |
| `report.md` | Human-readable summary. Markdown only. |
| `failure_source_label` | One of `retrieval_miss`, `bad_chunk_boundary`, `missing_metadata`, `csv_field_noise`, `prompt_or_reasoning_issue`, `safety_policy_gap`. |
| Tracing provider | `langsmith` or `phoenix`; pick exactly one. |

### Class diagram — TODO(trainee)

> Per the *SPDD discipline* norm, ship a `classDiagram` showing
> `TestScenarios` (`<<yaml file>>`), `ScenarioYaml`, `RunRecord`,
> `JudgedRecord`, the three CLIs (`run_agent_batch`,
> `llm_as_judge`, `report`), and a `Thresholds` class for the CI
> gate. Show that `JudgedRecord` *extends* `RunRecord`.

---

## Approach

### Design decisions

1. **Three CLI tools, three stages.** `run_agent_batch` →
   `llm_as_judge` → `report`. Each takes JSONL in and writes JSONL
   (or markdown) out. No shared state, no orchestrator.
2. **Scenarios as YAML, not code.** A junior engineer should be
   able to add a scenario without touching Python.
3. **Rubric in a prompt template.** `app/core/prompts/judge_rubric.j2`
   — a Jinja template loaded by the same `PromptService` from Task 4.
4. **Failure-source label is from a closed enum.** The judge picks
   the **single most likely** label. No "other"; no free-form text.
5. **Tracing via OpenTelemetry** wrapped by the chosen provider's
   SDK. Initialised in `app.api.main.lifespan`; absence of API key
   = a no-op exporter.

### TODO(trainee) — Trade-offs accepted

> List **at least three** trade-offs your design accepts. Hints:
> single LLM judge vs ensemble, JSONL vs Parquet for runs,
> markdown report vs HTML dashboard, threshold gate placement.

---

## Structure

### File layout

```
data_pipelines/eval/
├── __init__.py
├── test_scenarios.yaml
├── run_agent_batch.py    # batch runner
├── llm_as_judge.py        # judge
├── report.py              # markdown report (single run)
└── compare_reports.py     # markdown report (run-vs-run delta;
                           # diff two judged JSONLs and gate
                           # on thresholds via exit code)

app/observability/
└── tracing.py             # OTel exporter + span helpers (called from app, not eval)

app/core/prompts/
└── judge_rubric.j2        # the LLM-as-judge prompt
```

> Tracing helpers live under `app/observability/` because the
> spans are emitted from the *running agent* (the LangGraph
> nodes call them); the eval pipeline only *consumes* the
> resulting trace IDs to embed in reports. Keeping the
> instrumentation next to the app keeps the import direction
> one-way: `eval` imports from `app`, never the other way.

### Run record JSONL shape

```json
{
  "scenario_id": "q-overdraft-positive-balance",
  "request_id": "uuid",
  "user_question": "...",
  "tags": ["overdraft", "checking_or_savings"],
  "category": "functional",
  "final_answer": "...",
  "retrieved_doc_ids": ["overdraft_faq.txt#0"],
  "retrieved_complaint_ids": ["1234567"],
  "analysis_notes": "...",
  "latency_ms": 1234
}
```

### Judged record JSONL shape

```json
{
  "...": "...all fields from RunRecord...",
  "faithfulness_score": 0.8,
  "task_success_score": 1.0,
  "safety_handling_score": 1.0,
  "notes": "Cited overdraft_faq.txt section 1; no hallucinated terms.",
  "failure_source_label": "prompt_or_reasoning_issue"
}
```

---

## Operations (strict execution order)

> The first 2 steps are pinned. Steps 3+ are **TODO(trainee)**.

1. **Author 10 functional scenarios** in
   `data_pipelines/eval/test_scenarios.yaml`. They must cover the
   three product types in your starter corpus. Include obvious
   passes and at least 2 expected hard cases.
2. **Author the judge rubric** in
   `app/core/prompts/judge_rubric.j2`. Each rubric paragraph
   (faithfulness, task success, safety handling) ends with a
   sentence asking the judge to return a JSON object with the four
   fields above.

3. **TODO(trainee) — implement `run_agent_batch.py`** as a CLI
   that reads YAML, calls the agent runner, and writes JSONL.
4. **TODO(trainee) — implement `llm_as_judge.py`** that reads
   JSONL and writes judged JSONL. Calls `LLMService.complete` with
   `temperature=0.0` and `response_format="json"`.
5. **TODO(trainee) — implement `report.py`** that reads judged
   JSONL and writes a markdown report.
6. **TODO(trainee) — implement `compare_reports.py`** that
   reads two judged JSONLs (baseline and candidate), emits a
   markdown report of per-metric deltas, and exits non-zero
   when a configured threshold is breached. The thresholds
   live in a small Pydantic config or a YAML; pick one and
   document.
7. **TODO(trainee) — wire tracing** via
   `app/observability/tracing.py`, initialised in the FastAPI
   lifespan. Selection is by *credential presence*, matching
   the AC: if `LANGSMITH_API_KEY` is set, use LangSmith; else
   if `PHOENIX_COLLECTOR_ENDPOINT` is set, use Phoenix; else
   no-op. (Don't add an explicit `TRACING_PROVIDER` env var —
   credentials are unambiguous and avoid a config drift class.)
8. **TODO(trainee) — write tests** for each CLI: golden-file tests
   for `run_agent_batch` with a stubbed agent, golden-file tests
   for `llm_as_judge` with a stubbed `LLMService`, and a snapshot
   test for `report`.
9. **Update `README.md`** with an *Evaluation* section that lists
   the three CLI commands and a one-line description of what each
   produces.
10. **Verify** by running the three CLIs end-to-end on a fresh agent
    run, then `pytest`, `ruff`, `mypy --strict`, and
    `./scripts/smoke.sh`.

---

## Norms

- All scenarios in YAML use lowercase-with-hyphens IDs prefixed by
  `q-`.
- `failure_source_label` is the *closed* enum above; no new labels
  without updating Root Architecture.
- Judge calls run at `temperature=0.0` and `response_format="json"`.
- Reports are markdown; never auto-generate HTML.
- Tracing uses one provider only; never both at the same time.

---

## Safeguards

1. **Do not edit `test_scenarios.yaml` to make the agent pass.**
   The scenarios are the contract, not the agent.
2. **Do not let the judge call the agent.** The judge sees a run
   record (not the live agent) so the score is reproducible.
3. **Do not commit any `runs/` or `reports/` artifacts.**
   `.gitignore` them.
4. **Do not silently bias the judge toward leniency** by tweaking
   the rubric prompt to favour a struggling agent. Edit the agent
   instead.
5. **Do not skip tracing** in CI runs that produce reports;
   reviewers need a trace URL to investigate failed scenarios.

---

> **Spec drift watch.** Eval pipelines are notorious drift sources
> because every scenario edit is a contract change. Whenever you
> add or remove a scenario or change the rubric, update the
> appropriate canvas section in the same PR.

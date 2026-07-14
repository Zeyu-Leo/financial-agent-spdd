# Task 4 — Prompts & Conversation Compression *(REASONS Canvas, trainee edition)*

> **Trainee-edition posture.** This canvas is intentionally
> under-specified in the prompt-content sections. The destination
> state in `Task_4_Prompts.md` ships canonical example prompts that
> took several iterations + a real production bug to converge; you
> will draft your own and then compare.
>
> **Maps to:** Learning Plan Week 4 — *Prompt Engineering, Context
> Engineering (Stage 1), Cognitive Load*.
> **Depends on:** `Task_3_Orchestration.trainee.md`.
> **Unblocks:** `Task_5_Evaluation.trainee.md`, `Task_7_Safety.trainee.md`,
> `Task_8_Extensions.trainee.md` (a future sub-task consumes the
> helper this Task introduces).
>
> **Heads-up.** This week wears two hats. The first half is
> "lift inline prompts into versioned templates" — straightforward
> refactor work. The second half is the first taste of **Context
> Engineering**: managing the *cognitive load* that a long
> conversation places on the LLM. We give you the framing and a
> concrete acceptance test; you design the helper.

---

## Requirements

### Analysis context

**Domain keywords scanned:** prompt template, Jinja2,
PromptService, Scenario, structured output, schema validation,
versioned prompts, **conversation history, cognitive load,
prompt-cache prefix**. **Existing artifacts:**
`LLMService.complete` (Task 1), four inline prompt strings
sprinkled across tools (Task 3),
`AgentState.conversation_history` field already plumbed
through Task 3. **Prior tasks read:** Tasks 0–3.

**Strategic direction.** Lift every inline prompt into a
versioned `*.j2` template loaded by a single `PromptService`.
Add a Scenario extraction step so the agent's intent is
structured *before* retrieval, and a SafetyDecision shape
(logic deferred to a future Task). Strict undefined: a missing
variable is a build error, not a silent empty string. **And:
introduce a thin `compress_history` helper that protects the
synthesis prompt from a runaway `conversation_history` list.
This is your first taste of Context Engineering — we call it
Stage 1.**

> **Topology note for this week.** The acceptance criteria
> below talk about placing the new compression node "between
> `ingest_input` and `safety_phase`." `safety_phase` is the
> node Task 7 will add; in your Week-3 graph it does not exist
> yet. For Week 4, place `history_compression_phase` (or
> whatever you name it) immediately after `ingest_input` and
> before whatever node currently runs first (typically
> `retrieve_phase`). Wiring `safety_phase` in front of it is
> Task 7's job.

**The cognitive-load problem (read this twice).** Your Week-3
agent already passes `conversation_history` through to the
synthesis prompt. The first turn is fine. The 10th turn
ships nine prior turns into the synthesis prompt every time.
That balloons token cost, erodes prompt-cache hit rates, and
sometimes exceeds the model's effective attention. Production
agents that work in a demo and bankrupt the prod budget by
month two are usually losing this exact battle.

**TODO(trainee) — Risks noticed.** List **at least four**
risks for this week. At minimum, cover one risk in each of:
*small-model JSON compliance / parsing brittleness*, *ambiguous
input mapping to wrong enum values*, *template-vs-runtime
coupling*, **and *unbounded conversation_history growth***.

### Why this task exists

By the end of Task 3 the agent works end-to-end but every prompt
is an ad-hoc string buried inside a node, **and the
`conversation_history` field flows through unbounded — a 20-turn
dialogue ships 20 turns into the synthesis prompt with zero
summarisation, zero caching, and zero cost discipline**. That is
fine for a hello-world graph; it is unmaintainable for an
evaluated, safety-critical agent. Task 4 introduces four things
at once:

1. **Versioned prompt templates** in `app/core/prompts/*.j2`,
   loaded through a single `PromptService`.
2. **Structured intermediate outputs** — most importantly the
   `Scenario` model that the analysis phase extracts from the
   user query.
3. **The contract for `SafetyDecision`** — defined here, tested
   here, but **not yet enforced** in the graph (a future Task
   enforces it).
4. **Stage-1 Context Engineering: a `compress_history` helper
   plus a graph node that calls it.** Above a configurable
   threshold (default 5 messages), the helper summarises the
   *older* turns into a single message and keeps the most recent
   turns verbatim. Below the threshold, it is a no-op so short
   conversations pay no LLM cost.

### Acceptance criteria (Given/When/Then)

- **Given** the application is running,
  **when** a developer changes the contents of
  `app/core/prompts/scenario_extraction.j2`,
  **then** restarting the app picks up the new template without
  code changes elsewhere.
- **Given** a user query "I was charged a $35 overdraft fee in
  California",
  **when** the analysis phase runs,
  **then** `AgentState.scenario` is populated with a
  `product_type` referring to a checking or savings account, an
  `issue_type` referring to overdrafts, `amount=35.0`,
  `jurisdiction="CA"` (or "California"), and `confidence` between
  `0.0` and `1.0`.
- **Given** the LLM returns malformed JSON for `Scenario`,
  **when** the scenario extraction tool runs,
  **then** it retries **once** with a simplified prompt; on
  second failure it raises `LLMOutputValidationError` carrying
  the raw output, and the `/agent/query` endpoint returns HTTP
  502 with a structured error.
- **Given** the synthesis prompt is rendered,
  **when** the LLM returns the answer,
  **then** the answer includes a footer "Sources" that lists at
  least one `(source_file)#chunk_index` reference and at least
  one `complaint_id` when either was retrieved.
- **Given** an `AgentState.conversation_history` of length 8 and
  a stubbed ops-class LLM returning the literal string
  `"compressed summary"`,
  **when** the graph runs,
  **then** the new node you add (between `ingest_input` and
  `safety_phase`) replaces the older messages with a single
  `system`-role message whose content begins with the literal
  prefix `"[summary of earlier turns] "` (note the trailing
  space) followed by the LLM's summary text, and keeps the
  *most recent* turns verbatim. The prefix string is part of
  the contract — downstream tooling may rely on the literal
  prefix to detect already-compressed histories. Tests should
  assert the prefix exactly. Naming, tail size, and node
  placement are your design — TODO(trainee) — but the prefix
  string and the behaviour must satisfy this acceptance test.
- **Given** an `AgentState.conversation_history` of length 3 (a
  short conversation),
  **when** the graph runs,
  **then** the new node is a no-op and the ops-class LLM is
  **not** called.

---

## Entities

| Entity | Spec |
|---|---|
| `PromptService` | Reads templates from `app/core/prompts/`, renders Jinja with strict undefined handling. |
| `Scenario` | Pydantic model defined in Root Architecture. **First implementation lands in this Task.** |
| `SafetyDecision` | Pydantic model defined in Root Architecture. Implemented but unused in graph until a future Task. |
| Templates | At minimum: `doc_summary.j2`, `scenario_extraction.j2`, `next_steps.j2`, `safety_classification.j2`, **plus one new template you author for compression** — pick a name. |
| `ScenarioExtractionTool` | Calls the LLM with `scenario_extraction.j2`, parses to `Scenario`, retries once on failure. |
| `LLMOutputValidationError` | From Task 1; raised here on persistent parse failure. |
| **Conversation-compression helper** | A pure async helper *(TODO(trainee): name and signature)* that takes the existing `conversation_history`, the current user query, an `LLMService`, a `PromptService`, and a config knob, and returns a new history list (plus, optionally, the summary text it produced). No-op below the threshold. Lives in `app/core/`, not `app/tools/`, because a future task will re-use it. |
| **History-compression graph node** | A new LangGraph node that calls the helper and writes the new history back into `AgentState`. *TODO(trainee): pick a name and decide where in the topology it belongs.* Read the *Cognitive-load problem* paragraph above before deciding. |

### Class diagram — TODO(trainee)

> Per the *SPDD discipline* norm, ship a `classDiagram` here
> showing: `PromptService`, `Templates` (as `<<dir>>`), `Scenario`,
> `SafetyDecision`, `ScenarioExtractionTool`,
> `LLMOutputValidationError`, **the new compression helper, the
> new graph node, and an arrow from the helper to `LLMService`
> (which model class? See Trade-offs)**. Show that
> `ScenarioExtractionTool` *uses* `PromptService` + `LLMService`
> and *raises* `LLMOutputValidationError`.

---

## Approach

### Design decisions

1. **Jinja2 with strict undefined.** Missing variables raise at
   render time. No "fail-soft" defaults that mask context
   bugs.
2. **One template per LLM call site.** Don't share a template
   across two callers; copies are cheap and make prompt drift
   visible per-feature.
3. **Schema-first structured output.** Each prompt that returns
   JSON ships its expected schema in the prompt body
   (`<schema>...</schema>`). The parser validates against the
   Pydantic model, not a hand-rolled regex.
4. **One bounded retry on parse failure.** The retry uses a
   simplified prompt — a stripped-down "respond with valid JSON
   matching this schema and nothing else" version. The second
   failure raises `LLMOutputValidationError`.
5. **Templates live with the runtime.** `app/core/prompts/`,
   not `data_pipelines/`, because the FastAPI app needs them at
   import time.
6. **Compression is a separate phase, not folded into another
   tool.** The `compress_history` step is its own concern: it
   may fail, it may no-op, it owns its own LLM call. Folding it
   into an existing node mixes failure modes.
7. **Compression uses a small, fast, *ops-class* model — not the
   synthesis model.** Summarising five short messages does not
   benefit from a 27B model; using one would 3-10x the cost. Pick
   the right knob from `Settings`.
8. **Decide what to do when the compression LLM call fails.**
   Compression is a cost optimisation. The agent's *answer
   quality* is unaffected if compression is skipped. Reason
   carefully: should an ops-LLM hiccup 502 the whole agent? Or
   should the graph layer catch and continue? Justify your
   choice in *Trade-offs accepted*.

### TODO(trainee) — Trade-offs accepted

> List **at least four** trade-offs your design accepts. Hints:
> Jinja vs f-strings vs PEP 750 templates, strict undefined vs
> ergonomics, schema-in-prompt vs separate JSON-mode setting,
> retry budget vs latency, **threshold-by-count vs
> threshold-by-tokens, fail-loud vs best-effort on compression
> failure, where to keep the verbatim tail (last 1? last 2? all
> messages with role=user?)**.

---

## Structure

### File layout

```
app/
├── core/
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── doc_summary.j2
│   │   ├── scenario_extraction.j2
│   │   ├── next_steps.j2
│   │   ├── safety_classification.j2
│   │   └── <your_compression_template>.j2  # TODO(trainee): pick a name
│   ├── prompt_service.py
│   ├── safety_policy.py     # CREATE: Scenario + SafetyDecision Pydantic models (+ stub evaluate)
│   ├── <your_compression_module>.py   # TODO(trainee): pick a filename
│   ├── config.py            # AMEND: add the threshold + tail knobs
│   ├── graph.py             # AMEND: add the compression phase node, wire its edges
│   └── state.py             # AMEND: re-export real Scenario, SafetyDecision (replacing Task 3 placeholders)
└── tools/
    └── scenario_extraction_tool.py    # new in this Task
```

### Method signatures (the contract)

```python
# app/core/prompt_service.py
class PromptService:
    def __init__(self, *, prompts_dir: Path | None = None) -> None: ...
    def render(self, template_name: str, **vars: Any) -> str: ...
```

### Template contracts — TODO(trainee)

> The destination state ships canonical example prompts that took
> several iterations to converge. **Draft yours first, then your
> mentor compares them with the destination versions.** For each
> template below, your draft must satisfy:
>
> - `scenario_extraction.j2`: input `{user_query, conversation_history}`;
>   output a JSON object matching the `Scenario` Pydantic model.
>   Must include disambiguation hints for ambiguous product types
>   (e.g. "overdraft" obviously implies a checking/savings account,
>   not a credit card — small ops models will get this wrong without
>   a hint).
> - `doc_summary.j2`: input `{user_query, retrieved_docs,
>   structured_results}`; output a freeform analysis paragraph that
>   names the most relevant 1–3 retrieved IDs.
> - `next_steps.j2`: input `{analysis_notes, retrieved_docs,
>   structured_results, scenario}`; output the user-facing answer
>   with a `Sources` footer listing every cited ID.
> - `safety_classification.j2`: input `{user_query}`; output a JSON
>   object matching the `SafetyDecision` Pydantic model. Used by a
>   future Task; implement now and unit-test, but do **not** wire
>   into the graph yet.
> - **Your compression template** (you pick the name; suggested:
>   something with `compress` or `summarise` in it): input
>   `{older_messages, current_user_query}`; output **one tight
>   paragraph of plain prose** — not JSON. Hard rules to encode in
>   the template: max 6 sentences; preserves concrete facts
>   (amounts, dates, jurisdictions, account types, company names);
>   does *not* invent new facts; speaks in third person about "the
>   user" and "the assistant"; falls back to a literal sentence
>   like "No prior context worth retaining." when the older turns
>   are empty of signal.

---

## Operations (strict execution order)

> The first 2 steps are pinned. Steps 3+ are **TODO(trainee)**.

1. **Implement `PromptService`** in `app/core/prompt_service.py`.
   Use `jinja2.Environment(loader=FileSystemLoader, undefined=StrictUndefined)`.
2. **Define `Scenario` and `SafetyDecision`** as Pydantic models
   in `app/core/safety_policy.py` (single file — both models live
   together because Task 7 will add the `SafetyPolicy.evaluate(...)`
   method beside them). Re-export both from `app/core/state.py`,
   replacing the Task 3 placeholders.

3. **TODO(trainee) — draft the four prompt templates** in
   `app/core/prompts/`. Iterate on `scenario_extraction.j2` against
   at least 5 example queries before declaring it done.
4. **TODO(trainee) — implement `ScenarioExtractionTool`** with the
   bounded-retry parsing logic. It is invoked in a new graph node
   `scenario_phase` that runs **after** `ingest_input` and **before**
   `retrieve_phase`.
5. **TODO(trainee) — replace the inline prompts** in Task 3's tools
   with `PromptService.render(...)` calls.
6. **TODO(trainee) — Stage-1 Context Engineering: conversation
   compression.**
   - Add two new knobs to `Settings`: a *threshold* (default 5)
     and a *keep-tail* count (default 2). Document them inline.
     Decide whether `0` should disable the feature.
   - Author your compression Jinja template and put it under
     `app/core/prompts/`.
   - Implement the compression helper in
     `app/core/<your_filename>.py`. Decide its signature; decide
     what to return when below the threshold; decide which
     `Settings` model name to call (`ollama_ops_model` /
     `openrouter_model` — *not* the synthesis model).
   - Add a new phase node to `app/core/graph.py`. Decide where
     in the topology it belongs (before or after which existing
     phase, and *why*). Wire its edges. Document your trade-off
     for what to do when the compression LLM call fails.
   - Verify the two new acceptance criteria above (length-8
     conversation produces a compressed message; length-3
     conversation does not call the LLM).
7. **TODO(trainee) — write tests**:
   `test_prompt_service.py` (rendering + strict-undefined),
   `test_scenario_extraction_tool.py` (happy path, malformed-JSON
   retry, second-failure-raises),
   `test_safety_decision_schema.py` (model validation),
   **`test_<your_compression_module>.py`** — at least four cases:
   below threshold (no-op, no LLM call), above threshold (success,
   verbatim tail preserved), threshold disabled, LLM error
   propagates as you decided.
8. **Update `README.md`** with a *Prompt templates* section listing
   each template's purpose and inputs. Reference `app/core/prompts/`
   as the canonical location for prompt edits. Add a short
   *Conversation compression* note linking to your helper and the
   two new `Settings` knobs.
9. **Verify** by running `pytest`, `ruff`, `mypy --strict`, and
   `./scripts/smoke.sh` (the smoke now exercises Scenario extraction
   under the hood; compression remains invisible to the API
   contract — that is by design).

---

## Norms

- All prompt files live in `app/core/prompts/` and use the `.j2`
  extension.
- Every prompt that produces structured output includes a
  `<schema>` block describing the expected JSON shape.
- `PromptService.render` returns a `str`; callers never
  pre-stringify variables.
- Jinja `StrictUndefined` is mandatory; a missing variable is a
  build-time error — even for your new compression template.
- Prompt edits are committed alongside any code change that
  changes the variables they receive.
- The compression helper calls the **ops-class** model, not the
  synthesis model. Tests must assert this (introspect the
  `model=` kwarg on the stub LLM call).

---

## Safeguards

1. **Do not silently swallow JSON parse failures.** One bounded
   retry, then raise `LLMOutputValidationError`.
2. **Do not let templates read filesystem paths from user
   input.** `PromptService.render` is the only entry point.
3. **Do not embed user PII into the prompt without redaction.**
   Tasks downstream rely on this; logging may capture rendered
   prompts.
4. **Do not change a template's variable names** without updating
   every caller in the same PR (`StrictUndefined` will surface this,
   but reviewers should also check).
5. **Do not store prompt-source strings outside `app/core/prompts/`.**
   This is the prompt registry; everything else is a copy.
6. **Do not couple the compression helper to `AgentState`.** A
   future task will re-use the helper from a different code path.
   Take a plain `list[dict[str, Any]]` (and friends), not the
   TypedDict.
7. **Do not silence compression failures inside the helper.** The
   helper raises; the *graph layer* may catch and continue (that is
   your trade-off to design and document). Putting the catch
   inside the helper hides it from future readers.
8. **Do not compress on every turn.** Below your chosen threshold,
   the helper is a no-op and makes zero LLM calls. A test must
   assert this.

---

> **Spec drift watch.** When your prompts evolve (and they will,
> after Task 5's evaluation surfaces failures), edit the relevant
> template AND this canvas's *Template contracts* section in the
> same PR.

> **Forward link to a future task.** A later sub-task will build
> on the helper you author this week — granular prompt-cache
> groups and entity resolution. The cleaner your helper's
> signature, the easier that future task is. Read the *Approach*
> design decisions above with that re-use in mind.

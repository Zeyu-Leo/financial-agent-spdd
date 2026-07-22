# Week 5 — Evaluation  *(the trap springs)*

You shipped Week 4: a working agent with versioned prompts,
intent extraction, and conversation compression. It looks
polished. It will demo well.

This week measures it. **Read the next paragraph carefully —
it's the most important paragraph of the curriculum.**

---

> *This week you build the evaluation pipeline. By Friday it
> will tell you that the system you shipped last week has a low
> task-success rate. **That is not a critique of your code — it
> is the curriculum's intended reveal.***
>
> *The Week-2 RAG was deliberately naive. The Week-4 prompts are
> good but cannot rescue weak retrieval. Week 5 measures the
> gap. Week 6 fixes it.*
>
> *Your job this week is not to defend last week's score. It is
> to build a fair, reproducible measurement so the cohort can
> fix the right thing in Week 6. The code you wrote is fine.
> The data needs work.*
>
> *Read the spec. Build the pipeline. Trust the process.*

---

## What you're getting this week

- `.spdd_specs/tasks/Task_5_Evaluation.trainee.md` — your
  Monday brief.
- On Sunday: `Task_5_Evaluation.md`, the destination.

## What this week introduces

A 3-step Unix-y CLI: **batch → judge → compare**. Plus tracing.

1. **`run_agent_batch.py`** — runs every scenario in
   `test_scenarios.yaml` against a live `/agent/query` endpoint
   and writes one JSONL row per scenario.
2. **`llm_as_judge.py`** — scores each batch row with an LLM
   judge. Per-scenario tags, per-tag aggregates, faithfulness
   and task_success metrics.
3. **`compare_reports.py`** — diffs two judged runs and emits
   a markdown report with thresholds gating CI.
4. **`app/observability/tracing.py`** — OpenTelemetry spans
   emitted from the running agent, consumed (URL-only) by the
   report.

## Why we did it this way

- **Why scenarios in YAML, runs in JSONL?** Because YAML is
  human-edited (one-time effort) and JSONL is machine-appended
  (one row per run). Different access patterns, different
  files.
- **Why an LLM-as-judge instead of automated metrics?**
  Because `BLEU` and `ROUGE` measure surface overlap, not
  whether the agent actually answered the question. The LLM
  judge sees the retrieved evidence + the answer + the user
  question and rates faithfulness and task_success against a
  rubric. Imperfect, but correlated with what humans actually
  care about.
- **Why median of 3 repeats per scenario?** Because at
  `temperature=0.0`, identical scenarios still produce
  different judge scores ~5% of the time. Median of 3
  stabilises the signal. Your `.trainee.md` leaves this as a
  TODO; the destination pins `--repeats 3` on Sunday.
- **Why a separate `compare_reports.py`?** Because v0-vs-v1 is
  the centerpiece of next week's narrative. The compare script
  must produce a markdown report you can paste into a PR.

## Common Week-5 pitfalls

| Pitfall | What it looks like | The fix |
|---|---|---|
| Judge calls itself recursively | A scenario asks "what is the agent's confidence?" and the judge LLM happens to be the same model the agent uses. | The judge runs against the *output* JSONL, not against the live agent. Order: batch → judge → compare. |
| Tracing in `data_pipelines/eval/` | You naturally put `tracing.py` next to `llm_as_judge.py`. | Tracing instruments the *running agent*. It belongs in `app/observability/`. The eval pipeline only consumes trace IDs to embed in the report. |
| Defending the score | Your PR description argues that the score should be passing. | Reframe. The score is a measurement, not a verdict. Next week is the verdict. |
| Skipping the threshold gate | "I'll add the CI gate later in Week 7." | The threshold gate ships *this* week as a CLI exit code. The CI YAML wraps it later. Build the foundation now. |

## Wednesday self-check

- [ ] *Risks noticed* covers judge stability, scenario-set
      coverage, and faithfulness-vs-task-success drift.
- [ ] *Trade-offs accepted* names LLM-judge vs heuristic
      metrics, median-of-N vs single-shot,
      threshold-as-CLI-exit-code vs threshold-in-CI-YAML.
- [ ] *Class diagram* shows the three-step pipeline and the
      `app/observability/tracing.py` boundary.
- [ ] *Operations* numbered. Includes a step to run the
      pipeline end-to-end against your Week-3 agent and capture
      the baseline judged JSONL.

## What Sunday will reveal

The destination canvas pins the exact `--repeats N` flag and
the median+stdev computation, the exact tracing module
location, and the CI threshold-gate exit codes. It also
introduces a small but important addition for next week — a
judge-independent metric. Your `.trainee.md` is silent on it on
purpose; if you propose something judge-independent yourself,
your mentor will tell you on Wednesday.

## Going further (optional reading)

- The OpenAI / Anthropic eval cookbook chapters most aligned
  with our LLM-judge rubric, which rates faithfulness and task
  success against a spec.
  [OpenAI Cookbook: Evaluating LLMs](https://cookbook.openai.com/examples/evaluation/how_to_eval_abstractive_summarization)
- Hugging Face's `lighteval` for industry context on how
  evaluation pipelines run at scale.
  [Hugging Face LightEval](https://github.com/huggingface/lighteval)
- OpenTelemetry's Python SDK docs — useful if you want to swap
  our shim for full instrumentation that emits spans consumed
  by trace ID.
  [OpenTelemetry Python SDK Documentation](https://opentelemetry.io/docs/languages/python/)
- A war story from somewhere on the internet about an eval
  set that drifted from prod reality and gave green-light to
  a broken release. Find one and write a one-paragraph
  reflection in your PR description.
- **Judge Instability at Temperature 0:** Even at `temperature=0`,
  identical scenarios produce different judge scores ~5% of the
  time, which is why this curriculum uses median-of-3 repeats.
  [Why LLMs are Non-Deterministic at Temperature 0](https://1vxpi.com/blog/temperature-0)

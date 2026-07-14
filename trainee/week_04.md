# Week 4 — Prompts & Conversation Compression  *(Context Engineering, Stage 1)*

You shipped Week 3: a working `POST /agent/query` with the four-node
graph. But every prompt is an unmaintainable string buried inside a
Python tool. This week you fix that — and you also learn the *first*
piece of vocabulary the industry calls **Context Engineering**.

> **Heads-up.** This is the first of two Context Engineering
> injections in the curriculum. Stage 1 (this week) is small and
> tactical: a LangGraph node that compresses long conversation
> histories. Stage 2 (Week 8 Sub-Task D) is the mature
> intent-driven version that closes the curriculum's biggest
> loop. Don't try to coach yourself Stage 2 vocabulary this week.
> The emotional payoff lands harder if Stage 2 lands when it's
> supposed to.

## What you're getting this week

- `.spdd_specs/tasks/Task_4_Prompts.trainee.md` — your Monday
  brief.
- On Sunday: `Task_4_Prompts.md`, the destination.

## What this week introduces

Three things, in order of priority:

1. **Versioned prompt templates** in `app/core/prompts/*.j2`,
   loaded through a single `PromptService` with strict-undefined
   Jinja. Replace the inline strings from Week 3.
2. **`Scenario` extraction** — a new node `scenario_phase` that
   runs *before* retrieval, extracts a `Scenario` JSON
   (product_type, issue_type, amount, jurisdiction, confidence),
   and routes the structured retrieval tool with intent.
3. **Stage-1 conversation compression** — a `compress_history`
   helper that the ingest_input phase calls when
   `len(conversation_history) > N`. It calls a small LLM with a
   `compress_history.j2` template, collapses the older messages
   into a single summary string, keeps the last few turns
   verbatim, and writes the compressed list back into
   `AgentState.conversation_history`.

A fourth concept (`SafetyDecision` Pydantic shape) is *defined*
this week but **not yet enforced** in the graph (Week 7 enforces
it).

## Why we did it this way

### On prompts (the easy half)

- **Why Jinja with strict-undefined?** Because a missing
  variable is a build error, not a silent empty string. This
  catches template/data-shape drift before it reaches
  production.
- **Why are prompts versioned in `app/core/prompts/`?** Because
  in Week 5 the eval pipeline regression-tests prompts the way
  unit tests regress code. Untracked prompts cannot be
  regressed.

### On `compress_history` (the new half — the part that actually coaches Context Engineering)

- **What problem does it solve?** Conversation history grows
  linearly per turn. By the 10th turn, the LLM is reading 9
  prior turns of context. That balloons token cost, destroys
  prompt-cache hit rates, and exceeds the model's effective
  attention. *This is the tax that takes a working agent from
  prototype to production-unaffordable.*
- **Why threshold at 5?** A practical heuristic. The first ~5
  turns are usually within a model's coherent attention window;
  the 6th turn is where degradation becomes measurable. Treat
  5 as a tunable, not a constant — put it in `Settings`.
- **Why keep the last two turns verbatim?** Because immediate
  context (the previous question and answer) is the most
  signal-dense and your reasoning depends on it. Summarising
  the *last* turn destroys grounded follow-up answers.
- **Why a tiny / ops-class LLM for the summary?** Because the
  summary is itself an LLM call. Using `gemma3:27b` to
  summarise *for* `gemma3:27b` doubles cost. The ops model
  (`qwen3.5:4b`) is fast and good enough to compress 5
  messages into a 200-token summary.
- **Why compress *before* the synthesis prompt is rendered?**
  Because the prompt template renders against
  `state["conversation_history"]`. Compress first, render
  second. The order matters for prompt-cache stability — and
  we revisit *exactly* this property in Week 8.

A concrete, frequently-asked question for energetic trainees:
*"Couldn't we cache the system-prompt prefix and skip the
compression?"* Caching and compression are **complementary**,
not competitive. Week 8 Sub-Task D covers the prompt-cache side
of the story (intent-driven cache groups, cost-saving headlines).
Wait. The pieces compose better when you arrive at Week 8 with
this week's `compress_history` already shipped.

## Common Week-4 pitfalls

| Pitfall | What it looks like | The fix |
|---|---|---|
| Compressing the last turn too | The summary swallows "I just bought a house in California", so the next answer doesn't know jurisdiction. | Keep the last two turns verbatim. The summary covers *older* messages only. |
| Calling the synthesis model for compression | $$$ + slow. | Use the ops model from `Settings`. |
| Compressing on every turn | A 3-turn conversation gets a useless 1-line summary that says "user said hi". | Threshold at 5; below that, no-op. |
| Forgetting strict-undefined on the new template | A missing `messages` variable renders as `""`. | The constitution sets `StrictUndefined` as the default for every Jinja template, including new ones. Loose templates tend to silently swallow data-shape drift. |
| Inline prompt strings still living in tools | A test file or a tool keeps a copy of a prompt. | The constitution Norm: `app/core/prompts/` is the prompt registry. Everything else is a copy that must be deleted. |

## Wednesday self-check

- [ ] *Risks noticed* covers Jinja undefined errors, JSON-parse
      failures on the Scenario shape, **and** the
      conversation-history blow-up problem the
      `compress_history` handler addresses.
- [ ] *Trade-offs accepted* names Jinja vs f-strings vs PEP 750
      templates, schema-in-prompt vs JSON-mode setting, retry
      budget vs latency, **and** threshold-at-N for compression
      vs always-compress vs never-compress.
- [ ] *Class diagram* shows `PromptService → templates`, the
      new `compress_history` helper as a separate function
      called from `ingest_input`, and the Scenario extraction
      tool with its bounded retry.
- [ ] *Operations* numbered. The compression step is its own
      pinned step in the Operations list. (You'll have to
      decide its placement; the destination canvas pins it
      explicitly on Sunday.)

## What Sunday will reveal

The destination canvas pins:

- The four prompt-template names with their input variables.
- The `Scenario` and `SafetyDecision` Pydantic shapes
  (collocated in `app/core/safety_policy.py`).
- The `ScenarioExtractionTool` with one bounded retry and the
  `LLMOutputValidationError` raise on second failure.
- The `compress_history` helper signature, threshold, and
  verbatim-tail policy.

Diff your Friday work against it Sunday. File a reconciliation
PR before Monday.

## Going further (optional reading)

- Anthropic's blog post on *context window engineering* — the
  industry term that motivates why this week matters.
  [Anthropic: Context Window Engineering](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering)
- A short note on token-counting (`tiktoken` or the Anthropic
  tokenizer endpoint), so you can measure your compression
  savings in tokens, not just characters.
  [OpenAI Tiktoken GitHub Repository](https://github.com/openai/tiktoken)
- The original LangGraph memory tutorial — it under-sells the
  problem. Read it; feel the gap; appreciate that *this*
  curriculum is the gap-filler.
  [LangGraph Memory and Checkpointing](https://langchain-ai.github.io/langgraph/concepts/memory/)
- **Jinja Strict-Undefined:** The constitution sets
  `StrictUndefined` as the default so a missing variable is
  a build error rather than a silent empty string.
  [Jinja2 API: StrictUndefined](https://jinja.palletsprojects.com/en/3.1.x/api/#jinja2.StrictUndefined)
- **Forward link:** when you reach Week 8 Sub-Task D, come back
  to this canvas's `compress_history` section. The two stages
  compose; reading them side-by-side is the moment you stop
  being an Agent Developer and start being a Context Engineer.

# Week 3 — From Naive RAG to LangGraph Orchestration

You shipped Week 2: a corpus in Postgres and a working
`RetrievalService` you've called manually from a `python -c`
one-liner. This week the *agent itself* lands.

> **Heads-up on compute, not a warning.** This is the first week
> the LLM is invoked from a real graph node, so a thin laptop will
> notice. Cursor is no longer available for this curriculum. Below
> are several paths ordered by cost-effectiveness; pick what fits your
> setup — the list does not negate whatever you already use.
>
> 1. **Company Copilot (default).** Apply for a GitHub Copilot or
>    similar company coding-plan seat if available.
> 2. **Opencode Go($5 1st Month, $10 following).** Low-cost
>    subscription. Models: DeepSeek V4, Mimo v2.5, Minimax 3.
>    The first month is $5; subsequent months are $10.
> 3. **Opencode Zen(Do not enable Billing).** Free, no billing
>    setup needed. Built-in models provide good performance.
> 4. **DeepSeek official top-up.** Direct API access, pay-as-you-go.
> 5. **Local Ollama / mlx-community-optiq.** Free and fully
>    offline, but slow. Switch `OLLAMA_CHAT_MODEL=qwen3.5:4b` in
>    `.env` if the default model swaps on a 16 GB Mac.
> 6. **Your existing Coding Plan subscription.** If you already
>    use Cline, Continue, Windsurf, or another plan, it works fine.
>
> Mention the path you picked in the Week 3 reconcile note. Full
> posture: `README.md` → "Provider posture",
> `.spdd_specs/tasks/Task_0_Environment.md` → "Compute paths".

## What you're getting this week

- `.spdd_specs/tasks/Task_3_Orchestration.trainee.md` — your
  Monday brief.
- On Sunday: `Task_3_Orchestration.md`, the destination.

## What this week introduces

By Friday, `POST /agent/query` returns a grounded answer.

1. **`AgentState` TypedDict** — flows between LangGraph nodes.
   Includes forward-compatibility fields (`safety_decision` and
   `scenario`) that stay `None` this week. Later tasks wire them.
2. **Four tool nodes** — `retrieve_docs_tool`,
   `retrieve_structured_tool`, `summarise_tool`,
   `synthesise_answer_tool`. Each is a *pure function* that
   returns a *partial* `AgentState`.
3. **`AgentRunner`** — keyword-only
   `run(*, user_query, session_id, conversation_history,
   request_id)`. The HTTP endpoint maps the API field
   (`question`) onto the runtime field (`user_query`).
4. **`scripts/smoke.starter.sh`** — three checks: `/healthz`,
   `/readyz`, `/agent/query` happy path. Adopt the starter
   script. **Do not** create a new smoke harness this week.

## Why we did it this way

- **Why a TypedDict and not a Pydantic model for
  `AgentState`?** Because LangGraph's reducer model integrates
  more naturally with TypedDicts. Pydantic remains the choice
  for DTOs at API boundaries — the two have different jobs.
- **Why `question` at the API and `user_query` inside?**
  Because the API field is named for the *user's* mental model
  ("question"), and the internal field is named for its *role*
  in the graph ("user_query"). Mapping at the boundary is
  intentional separation.
- **Why are `safety_decision` and `scenario` already on
  `AgentState` if they stay None?** Because adding them later
  churns the TypedDict and forces a chain of partial-state
  refactors. Forward-compat fields are cheap; backward
  refactors are not.
- **Why does retrieval run docs and complaints concurrently
  (`asyncio.gather`)?** Because Postgres can serve them in
  parallel and the latency win is large. With
  `return_exceptions=True`, partial failure still produces an
  answer.

## Common Week-3 pitfalls

| Pitfall | What it looks like | The fix |
|---|---|---|
| Mutating `AgentState` in place | A node assigns `state["foo"] = bar` and returns `state`. | Nodes return *partial* dicts. The reducer merges them. Mutation breaks LangGraph checkpointing. |
| Synthesising before retrieval | A node calls `LLMService.complete()` without checking `state.get("retrieved_docs")`. | The graph's edge order is the contract. Run synthesis only after retrieval lands. |
| Not setting `X-Request-Id` header | Logs are correlated; the response is not. The mismatch costs you debugging time later. | Middleware sets the header on every response, success or error. |
| Returning raw `AgentState` from the API | Internal fields leak. | Map to `AgentQueryResponse` Pydantic at the boundary. |

## Wednesday self-check

- [ ] *Risks noticed* lists at least three real risks: reducer
      ordering bugs, partial-failure handling, and the
      conversation-history blow-up that's coming next week
      (think about it now — it's the heart of Week 4).
- [ ] *Trade-offs accepted* covers TypedDict vs Pydantic for
      state, sequential vs parallel retrieval, partial-state
      vs full-state node returns.
- [ ] *Class + flow diagram* shows the four nodes, the
      `START → ingest_input → retrieve_phase → analysis_phase
      → synthesis_phase → END` topology, and the boundary
      between `AgentRunner` (engine) and `/agent/query` (API).
- [ ] *Operations* numbered, including the
      `scripts/smoke.starter.sh` adoption step.

## What Sunday will reveal

The destination canvas pins the keyword-only `AgentRunner.run`
signature, the `AgentQueryRequest.question` field constraints,
the structured 502 error body for `LLMProviderError`, and the
*shape* of conditional edges (Week 7 wires safety, Week 8 wires
complaint-letter branching) — they don't fire yet, but the
topology must be ready.

## Going further (optional reading)

- A walk-through of LangGraph's `StateGraph` reducer semantics
  under partial returns — why `TypedDict` is used over a
  Pydantic model for `AgentState`.
  [LangGraph Conceptual Guide: State & Reducers](https://langchain-ai.github.io/langgraph/concepts/low_level/)
- Anthropic's "agentic patterns" post — worth your reading
  even though we use LangGraph rather than naive agentic loops.
  [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- FastAPI's `BackgroundTasks` documentation — relevant when
  the feedback writeback lands later.
  [FastAPI Background Tasks Documentation](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- **Parallel Execution under the Hood:** Docs and complaints
  retrieved concurrently via `asyncio.gather` for a large
  latency win. Learn the patterns of async concurrency.
  [Python `asyncio` Task Groups and `gather`](https://docs.python.org/3/library/asyncio-task.html)

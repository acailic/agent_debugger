# Peaky Peek Launch Kit

**Status: DRAFT — nothing here has been published yet.** This file is the
distribution package for the main bet. The product is the strong part; the
missing part is people knowing it exists. Everything below is written to be
pasted, not rewritten from scratch.

One-line positioning (use everywhere, keep it identical):

> **Peaky Peek is a local-first flight recorder + audit console for AI agents:
> it captures every decision your agent makes and turns the trace into a
> deterministic trust report — verified claims, localized failures, and a
> verdict you can act on. No LLM judging the LLM, no data leaving your
> machine.**

Facts you may cite without checking (as of 2026-08-24):

- `pip install peaky-peek-server && peaky-peek --open` — server + UI in one
  package; `pip install peaky-peek` for the SDK alone
- SDK capture via decorator or context manager; adapters for LangChain,
  PydanticAI, OpenAI, CrewAI, AutoGen, LlamaIndex, Anthropic
- Audit engine: five operator questions (what / why / evidence / outcome /
  where-failed), six deterministic claim statuses (verified · partially
  verified · contradicted · unsupported · unverified · stale), explainable
  trust score, verdict card with stakes line and act / verify-first /
  do-not-act bands, failure narrative (symptom / mechanism / evidence / next
  inspection point)
- Research features: goal-drift score, success-flow deviation advisory,
  Who&When failure-localization harness, evidence-provenance graph with
  uncited-fact callouts, cross-session audit portfolio
- Debugging toolkit: replay with checkpoints, causal graph / root-cause
  analysis, session comparison, multi-agent swimlanes, stepper
- 3,100+ tests, CI on Python 3.10–3.12, 70% coverage gate
- Grounded in public research — notes on every paper in `docs/papers/`

---

## 1. Launch blog post (draft)

> Title: **Why I built a trust layer for AI agents**
> Publish on the personal blog first; everything else links here.

Agents fail quietly. That is the whole problem.

An agent run looks like a success from the outside: it made calls, it produced
an answer, it even sounds confident. Then, two days later, you find out it
wrote to the wrong database, or answered from a stale document when a fresh
one existed, or asserted something it had no evidence for at all. The trace
of *why* is usually gone — or worse, it's sitting in a pile of JSON logs
nobody will ever read.

I kept running into the same three gaps:

1. **Logs are not explanations.** A trace tells you what happened. It almost
   never tells you *which decision was the bad one*, or what evidence the
   agent actually had when it decided.
2. **"Evals" check outcomes, not reasoning.** A passing eval can hide a run
   that got the right answer through a chain of unsupported claims. You want
   to trust the process, not just the output.
3. **Observability tools trust the model to grade itself.** Half the agent
   observability market is "ask an LLM to summarize the LLM". For trust that's
   circular — the failure mode you're auditing for is exactly the failure mode
   of your auditor.

So I built [Peaky Peek](https://github.com/acailic/agent_debugger) — a
local-first flight recorder and audit console for AI agents.

## What it does

Instrument your agent with the SDK (decorator or context manager; adapters
exist for LangChain, PydanticAI, OpenAI, CrewAI, AutoGen, LlamaIndex and
Anthropic):

```python
from agent_debugger_sdk import trace_session

async with trace_session("support_agent") as ctx:
    policy = await lookup_policy("refunds")
    policy_id = await ctx.record_tool_result("lookup_policy", policy)
    await ctx.record_decision(
        reasoning="customer eligible per policy lookup",
        confidence=0.9,
        chosen_action="refund via payment provider",
        evidence_event_ids=[policy_id],
    )
```

Then open the console (`pip install peaky-peek-server && peaky-peek --open`)
and every session comes with an **audit report** that answers the five
questions an operator actually asks: what happened, why did it decide that,
what evidence did it rely on, what was the outcome, and where did it fail.

The part I care most about is **claim verification**. Every decision the agent
makes is treated as a claim, and each claim gets a deterministic status:

- **verified** — backed by a concrete successful tool result, user input, or
  retrieved document in the trace
- **partially verified** — carries evidence, but it doesn't resolve to a
  concrete fact
- **contradicted** — a confident decision whose downstream subtree failed;
  the agent was sure, and reality disagreed
- **unsupported** — confident assertion with zero evidence
- **unverified** — low-confidence assertion with zero evidence
- **stale** — grounded in evidence that a newer fact had already superseded
  at decision time, uncited

All of this is computed from captured event fields — no LLM calls, no
randomness, no cloud. The same run always produces the same report, which is
the property you need before "trust" means anything.

On top of that: an explainable trust score (weighted blend you can inspect,
not a black-box number), a verdict card that names what's at stake (read-only
scratch run vs. state-mutating production run) and the posture it implies
(act / verify-first / do-not-act), a goal-drift score, a success-flow advisory
that localizes the first divergence from a similar successful run, an
evidence-provenance graph that calls out facts that *existed but were never
cited*, and — new this week — a **failure narrative**: symptom, likely
mechanism, anchored evidence links, and the single best next inspection
point, with the confidence honestly capped when no cause could be localized.

## Who it's for

- Teams running agents in production who need to answer "why did it do that"
  after an incident, not during a rewrite
- Anyone building agent pipelines that touch state (writes, deploys, sends)
  where "it looked fine" isn't an acceptable audit answer
- People who, like me, don't want their agent traces uploaded to someone
  else's cloud to be graded by someone else's model

## The research bet

Most features map to a published paper, with notes in
[`docs/papers/`](https://github.com/acailic/agent_debugger/tree/main/docs/papers):
failure localization follows the Who&When line of work, the success-flow
advisory comes from OAT's flow-of-success attribution, trust bands from the
calibrated-trust literature, failure narratives from XAI work on coding-agent
failures. The value isn't implementing one paper — it's that the audit engine
is a place where these results compose on the same trace.

## What's next

The roadmap is public: minimal re-execution set (re-run the smallest sub-graph
to confirm or invalidate a suspect claim), replay clustering, and an external
accuracy number on the Who&When benchmark. The repo has 3,100+ tests and CI
across Python 3.10–3.12; the audit engine is deterministic by design and I'd
like to keep it that way.

If you're running agents and can't currently answer "what evidence did it
have when it decided that" — try it and tell me what breaks.
[GitHub](https://github.com/acailic/agent_debugger) ·
`pip install peaky-peek-server && peaky-peek --open`

---

## 2. Show HN

> Submit as **Show HN**, Tuesday–Thursday morning US time. The blog post URL
> is the link; the text below goes in the first self-comment, posted
> immediately after submitting.

**Title:** Show HN: Peaky Peek – Local-First Flight Recorder and Trust Reports for AI Agents

**First comment:**

I built this because agent traces tell you *what* happened but never *which
decision was the bad one*. Peaky Peek instruments your agent (decorators or
adapters for LangChain/PydanticAI/OpenAI/CrewAI/AutoGen/LlamaIndex/Anthropic),
records every decision with its evidence, and produces a deterministic audit
report per session:

- Every decision is a *claim* with a verification status computed from the
  trace: verified / partially verified / contradicted / unsupported /
  unverified / stale (e.g. "stale" = it acted on evidence a newer fact had
  already superseded).
- Failures are localized to a root-cause suspect with a causal chain, and the
  report includes a failure narrative: symptom, mechanism, evidence links
  back to events, and the best next inspection point.
- Explainable trust score + verdict card: same score reads differently for a
  read-only scratch run and a state-mutating production run
  (act / verify-first / do-not-act).
- Everything is deterministic — no LLM judging the LLM — and local-first:
  SQLite storage, no telemetry, no cloud. The audit of your agent doesn't
  itself become a data leak.

Also a research-flavored side: failure localization is benchmarked against
the Who&When annotated logs, first-divergence attribution follows the OAT
"flow of success" idea, and each paper note is in docs/papers/.

`pip install peaky-peek-server && peaky-peek --open` starts the console.
Happy to dig into how claim verification or the trust score works — both are
fully inspectable, which was the whole point.

## 3. Reddit — r/LocalLLaMA

> No link in the title. Post as text with links in the body. Same day as
> Show HN, morning US time.

**Title:** I built a local-first "flight recorder" for AI agents — deterministic trust reports, no cloud, no LLM-judges

**Body:**

Hey all — I kept hitting the same problem: agent runs look successful, then
you find out later the agent asserted things with zero evidence, or acted on
stale context when a fresh tool result existed. And the popular observability
tools upload your traces and have an LLM summarize them — which I don't want
anywhere near production traces.

So I built Peaky Peek (open source, MIT):

- SDK captures decisions + evidence via decorator/context manager (adapters:
  LangChain, PydanticAI, OpenAI, CrewAI, AutoGen, LlamaIndex, Anthropic)
- Per-session audit report: every decision classified as a claim with a
  deterministic status — verified, partially verified, contradicted,
  unsupported, unverified, or stale (cited evidence was superseded by a newer
  uncited fact)
- Failure localization with causal chains + a failure narrative (symptom,
  mechanism, evidence, next inspection point)
- Explainable trust score with named components + a verdict card (act /
  verify-first / do-not-act) that accounts for whether the run mutated state
- 100% local: SQLite + FastAPI + a React console. No telemetry.

The determinism is the point: same trace, same report, every time — so you
can diff runs and trust the diff.

Repo: https://github.com/acailic/agent_debugger
Quickstart: `pip install peaky-peek-server && peaky-peek --open`

Happy to answer how the claim verification or staleness detection works —
it's all structural analysis of the trace, no model calls.

## 4. Discord one-liners

> Post in #showcase / #projects channels, not support channels. One message,
> no thread spam.

**LangChain / LlamaIndex / AutoGen / CrewAI dev servers:**

> Built an open-source audit layer for agent runs: instruments the framework,
  classifies every decision as verified/unsupported/stale/contradicted from
  the trace itself (no LLM judge, fully local), localizes failures to a
  root-cause suspect, and gives each session an explainable trust score +
  verdict card. 3,100+ tests, MIT. Would love feedback from people running
  agents in prod: https://github.com/acailic/agent_debugger

**PydanticAI Discord (has a first-class adapter — lead with that):**

> Wrote a PydanticAI adapter for my agent audit tool: wrap your agent, every
  decision gets captured with evidence and classified deterministically
  (verified / partially verified / contradicted / unsupported / unverified /
  stale), failures localized to root-cause suspects with a readable narrative.
  Local-first, MIT, no LLM-in-the-loop grading:
  https://github.com/acailic/agent_debugger

## 5. Launch-day checklist

Order matters: blog first (it's the canonical URL), then HN, then Reddit ~1h
later so they don't cannibalize each other, then Discords in the evening.

- [ ] Blog post published (section 1) — read it once aloud first
- [ ] Repo README top matches the positioning line (first screen answers
      "what is this for me" in <10s)
- [ ] Repo has a screenshot/GIF of the audit verdict card + failure narrative
      near the top (record with the seeded demo: `make demo-seed`)
- [ ] Show HN submitted (section 2); first comment posted immediately
- [ ] r/LocalLLaMA post (section 3)
- [ ] Discord one-liners (section 4)
- [ ] Pin the blog link on the GitHub profile; unpin unrelated repos from the
      profile front page so the bet is the first thing visitors see
- [ ] Answer every comment within ~2h during the first 24h (set alarms);
      technical answers, no defensive tone, "good point, filed as an issue"
      is a great reply
- [ ] File every launch-day complaint as a GitHub issue the same day —
      launch feedback is free roadmap prioritization

## 6. After launch: compounding rules

- Every future blog post ties back to this repo (a feature deep-dive, a
  benchmark result, a postmortem story). No general AI essays until the
  distribution loop exists.
- Weekly cadence, not daily: one meaningful public artifact per week
  (post, release, benchmark run) compounds; fifteen parallel explorations
  don't.
- Success metric for the first 30 days: GitHub issues from strangers and one
  external PR. Stars are vanity; issues are signal.

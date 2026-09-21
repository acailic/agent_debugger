# Dapper, a Large-Scale Distributed Systems Tracing Infrastructure

Report: [dapper-2010-1](https://research.google.com/archive/papers/dapper-2010-1.pdf) (Google, 2010)

## Core Idea

The design that became the model for every distributed tracing system since (Zipkin, Jaeger, OpenTelemetry). Traces are trees of spans; instrumented services propagate trace context and emit span annotations. The paper derives three requirements — ubiquitous deployment, continuous monitoring, application-level transparency — and shows that annotated instrumentation beats black-box inference: a compared inference-based system "mistakenly attributed causality to unrelated events." It treats recording cost seriously (even sampling 1 in 1024 requests kept overhead below 0.01%) and records limited metadata with no payload data, protecting sensitive information by design.

## Why It Matters Here

The black-box recorder is Dapper for agents, and this report is its design brief. Propagate explicit causal identifiers — trace and span ids — across model calls, tool calls, and decisions, instead of inferring causality afterwards from text.

The instrumented-versus-inferred finding is the scientific argument for the core stance. Google measured inference-based monitoring attributing causality to unrelated events; an LLM judge reading logs after the fact is the same bet with weaker instrumentation. "No LLM judge in the attribution path" is not a preference, it is Dapper's lesson.

The safety policy transfers verbatim. Dapper records structure and limited metadata, not payloads, by default — the same posture the recorder's redaction takes, and one worth stating per event type rather than globally.

## Key Takeaways For The Repo

### 1. Causality should be propagated, not inferred

Trace and span ids on every recorded event make the causal chain a fact of capture. Deterministic attribution is then traversal, and the instrumented-versus-inferred comparison is its published defense against post-hoc LLM inference.

### 2. Instrument everywhere or the trace lies

Dapper's ubiquitous-deployment requirement is the argument for auto-patch adapters: any uninstrumented hop is a hole in the span tree, and session completeness diagnostics exist to catch exactly those.

### 3. No payload by default, per event type

Record structure and metadata, not payloads, with the policy documented per event type and redaction explicit per field. Safety by design, and cheaper events, from a system that ran at Google scale.

## Concrete Opportunities

- formalize the recorder's event schema as span trees with propagated trace/span ids, written identically by the SDK and the auto-patch adapters
- write the documented "no payload by default" policy per event type, Dapper-style, with redaction stated per field
- add trace-continuity checks to session completeness diagnostics: every span has a parent, no orphaned tool calls, no unparented decisions
- cite the instrumented-versus-inferred finding in docs wherever the no-LLM-judge stance is argued

## Caution

Dapper samples and drops — even its least-aggressive scheme kept 1 request in 1024 — and an audit console cannot sample: the run that matters is precisely the one a sampler would have dropped. Adopt the span model and the safety practice, not the sampling philosophy. And do not over-apply the overhead argument: Dapper optimizes always-on monitoring of millions of production requests, while this repo records fewer sessions completely.

## Best Next Experiment

Run a span-integrity checker over existing session bundles: every event carries trace and span ids, every tool call's span has a parent decision span, nothing is orphaned. A small script over recorded sessions, no new infrastructure — the gap rate it reports is the auto-patch adapter backlog.

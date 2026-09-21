# Getting Started with Peaky Peek

Debug AI agents with time-travel replay, decision trees, and audit reports. This guide takes about 5 minutes.

## 1. Install

There is one maintained installation path:

```bash
pip install peaky-peek-server
```

(Alternative for development: clone the repo, `pip install -e ".[dev]"` plus the server extras, then run the server with `uvicorn api.main:app --port 8000` — see the [integration guide](./integration.md).)

## 2. Start the Debugger

```bash
peaky-peek --open
```

This starts the server at http://localhost:8000 (the UI is also served at `/ui/`) and opens your browser. This exact launch path is verified end-to-end by `scripts/install_smoke.sh` — wheel install, keyless SDK trace, restart with the same data directory — see [docs/research/2026-09-20-install-smoke.md](../research/2026-09-20-install-smoke.md).

## 3. Instrument Your Agent

The SDK only delivers events when an endpoint is configured. `init(endpoint=...)` **without** an API key sends unauthenticated to your local server; with no endpoint at all the SDK stays inert (events recorded in memory, nothing sent).

```python
import asyncio
from agent_debugger_sdk import TraceContext, init

init(endpoint="http://localhost:8000")

async def main():
    async with TraceContext(agent_name="demo", framework="custom") as ctx:
        await ctx.record_decision(
            reasoning="User asked for weather",
            confidence=0.85,
            chosen_action="call_weather_api",
        )
        await ctx.record_tool_call("weather_api", {"city": "Seattle"})
        await ctx.record_tool_result("weather_api", result={"temp": 72})

asyncio.run(main())
```

## 4. Explore the UI

Refresh your browser — you'll see your first trace.

- **Trace**: timeline, decision tree, checkpoints (click events to inspect details)
- **Inspect**: audit panel with the trust report and verdict card
- **Analytics**: cost tracking and session analytics

## 5. Export Your Data

```bash
curl http://localhost:8000/api/sessions/<session-id>/export | jq . > trace.json
```

## Zero-Config Auto-Patching (No Code Changes)

Already have an agent using OpenAI or Anthropic SDK? No code changes needed:

```bash
PEAKY_PEEK_AUTO_PATCH=all python your_agent.py
```

Peaky Peek automatically captures all LLM calls and tool use and delivers them to the server (default `PEAKY_PEEK_SERVER_URL=http://localhost:8000`). Use `all` or a comma-separated adapter list such as `openai,anthropic`; any other value patches nothing.

## Operator Workflows

Three operator workflows are the maintained onboarding contract. Each is verified by a committed artifact — run it yourself from the repo root.

### (a) Capture → inspect in the UI

Record a traced session, open the console, and read the audit report: session list → session → Inspect tab → audit panel → click a finding's evidence link → the linked event is selected in the timeline with its detail open. Delayed responses show a loading state, not a crash.

Proving artifact: `scripts/browser_smoke.mjs` — a real headless-Chromium journey through the served UI that asserts each of those steps (run: `node scripts/browser_smoke.mjs` from the repo root; needs `frontend/dist` built and Playwright with chromium). The keyless capture path it rides on is proven by `tests/e2e/test_no_key_local_delivery.py`.

### (b) Checkpoint restore with provenance

Anchor a checkpoint mid-run, then restore it — via the SDK (`TraceContext.restore(checkpoint_id)`) or `POST /api/checkpoints/{id}/restore`. The restored session starts with a `session_restored` provenance marker carrying the restore token and the source checkpoint id; the source session is left untouched, and the post-checkpoint events are not copied.

Proving artifacts: `tests/e2e/test_semantic_restore_sdk.py` (SDK restore over a real server, provenance assertions over the operator HTTP API) and `scripts/browser_smoke.mjs` (asserts the restore boundary is visible as the first timeline event in the UI). Example code: `examples/05_checkpoint_replay.py`.

### (c) Incident → regression bundle

A captured incident becomes a pinned, deterministic test case: export the session as a sanitized, content-hashed bundle, review and commit it as a fixture, replay it through the current audit engine (no model calls, no re-execution), and compare candidate vs baseline runs to name exactly the regressed assertions.

Proving artifacts: `docs/guides/regression-lab.md` (the workflow narrative and CLI) with `tests/test_regression_lab.py` and `tests/test_regression_baseline.py` (export determinism, hash verification, runner and comparison semantics).

## Next Steps

- [How It Works](./how-it-works.md)
- [Architecture](./architecture.md)
- [Examples](../../examples/)

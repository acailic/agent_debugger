# Learning Guide

The detailed learning-oriented documentation lives under [`docs/`](../README.md), but the shortest useful summary is:

## What This Repo Has Taught So Far

- the project is strongest when treated as a trace-first debugger, not a generic observability tool
- one shared event model is the main architectural asset across SDK, API, storage, replay, and UI
- the live path and the durable path need different roles:
  - the buffer is for fan-out
  - the repository is the source of truth
- local-first execution is coherent today; cloud support is real but still a hardening track
- security and privacy features only count when they sit on ingestion and query paths, not just in helper modules
- the repo’s next value comes more from deeper replay, stronger seeded scenarios, and product hardening than from adding new concepts

## Best Starting Points

- [Progress](./progress.md)
- [How It Works](./how-it-works.md)
- [Architecture](./architecture.md)
- [Repo Overview](./repo-overview.md)
- [Lessons Learned](./lessons-learned.md)
- [Improvement Roadmap](../plans/improvement-roadmap.md)
- [Research Inspiration](../research/research-inspiration.md)

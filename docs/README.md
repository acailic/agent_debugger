# Documentation

This folder explains what this project is, how it works today, and what it still needs next.

## Start Here

- [Repo Overview](./repo-overview.md): what is in the repository, what already works, and what is still rough
- [Lessons Learned](./lessons-learned.md): what building the debugger so far has taught
- [How It Works](./how-it-works.md): the current runtime flow from trace capture to UI
- [Architecture](./architecture.md): system layers, major modules, and data flow
- [Console Workflows](./console-workflows.md): the debugger workflows that are implemented in the UI today
- [Improvement Roadmap](./improvement-roadmap.md): the most useful next improvements
- [Research Implementation Plan](./research-implementation-plan.md): how the paper-inspired features should be built in phases
- [Research Inspiration](./research-inspiration.md): papers influencing the design direction
- [Paper Notes](./papers/README.md): one note per paper, focused on what is actually useful here

## Useful Commands

- `venv/bin/python -m pytest -q`
- `cd frontend && npm run build`
- `venv/bin/python scripts/seed_demo_sessions.py`

## Suggested Reading Order

1. [Repo Overview](./repo-overview.md)
2. [How It Works](./how-it-works.md)
3. [Lessons Learned](./lessons-learned.md)
4. [Architecture](./architecture.md)
5. [Console Workflows](./console-workflows.md)
6. [Improvement Roadmap](./improvement-roadmap.md)
7. [Research Implementation Plan](./research-implementation-plan.md)
8. [Research Inspiration](./research-inspiration.md)
9. [Paper Notes](./papers/README.md)

## Documentation Principles

The docs try to stay honest about two things:

- what is implemented now
- what is still incomplete or rough

That distinction matters here. The core debugger path now works end to end. The remaining work is mainly cross-session comparison, live monitoring depth, benchmark coverage, and production hardening.

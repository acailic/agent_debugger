# Documentation

This folder explains what this project is, how it works today, and what it still needs next.

## Start Here

- [Progress](./progress.md): current implementation snapshot, recent repo progress, and what is still only partial
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
2. [Progress](./progress.md)
3. [How It Works](./how-it-works.md)
4. [Lessons Learned](./lessons-learned.md)
5. [Architecture](./architecture.md)
6. [Console Workflows](./console-workflows.md)
7. [Improvement Roadmap](./improvement-roadmap.md)
8. [Research Implementation Plan](./research-implementation-plan.md)
9. [Research Inspiration](./research-inspiration.md)
10. [Paper Notes](./papers/README.md)

## Documentation Principles

The docs try to stay honest about two things:

- what is implemented now
- what is partially implemented but not yet wired end to end
- what is still incomplete or rough

That distinction matters here. The core local debugger path now works end to end. The main remaining work is finishing the newer cloud/security path, deepening replay, and hardening the product for multi-user use.

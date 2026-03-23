# Documentation

This folder explains what the project is, how to integrate it, and how it works.

## Start Here

- [Intro](./intro.md): the plain-language explanation of the product
- [Integration](./integration.md): how to instrument your code locally
- [Progress](./progress.md): current implementation status
- [How It Works](./how-it-works.md): the runtime flow from trace capture to UI
- [Architecture](./architecture.md): system layers, modules, and data flow
- [Repo Overview](./repo-overview.md): what is in the repository

## Reference

- [Lessons Learned](./lessons-learned.md): what building the debugger so far has taught
- [Console Workflows](./console-workflows.md): the debugger workflows implemented in the UI
- [Improvement Roadmap](./improvement-roadmap.md): useful next improvements
- [Research Implementation Plan](./research-implementation-plan.md): how paper-inspired features should be built
- [Research Inspiration](./research-inspiration.md): papers influencing the design direction
- [Paper Notes](./papers/README.md): notes on specific papers
- [ADRs](./decisions/README.md): architecture decision records

## Useful Commands

```bash
# Run tests
python -m pytest -q

# Build frontend
cd frontend && npm run build

# Seed demo data
python scripts/seed_demo_sessions.py
```

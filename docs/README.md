# Documentation

This folder explains what the project is, how to integrate it, and how it works.

## Start Here

- [Intro](./guides/intro.md): the plain-language explanation of the product
- [Integration](./guides/integration.md): how to instrument your code locally
- [Progress](./guides/progress.md): current implementation status
- [How It Works](./guides/how-it-works.md): the runtime flow from trace capture to UI
- [Architecture](./guides/architecture.md): system layers, modules, and data flow
- [Repo Overview](./guides/repo-overview.md): what is in the repository

## Reference

- [Lessons Learned](./guides/lessons-learned.md): what building the debugger so far has taught
- [Console Workflows](./guides/console-workflows.md): the debugger workflows implemented in the UI
- [Improvement Roadmap](./plans/improvement-roadmap.md): useful next improvements
- [Research Implementation Plan](./research/research-implementation-plan.md): how paper-inspired features should be built
- [Research Inspiration](./research/research-inspiration.md): papers influencing the design direction
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

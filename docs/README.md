# Documentation

This folder explains what this project is, how it works today, and what it still needs.

## Start Here

- [Repo Overview](./repo-overview.md): what is in the repository, what already works, and what is still rough
- [Lessons Learned](./lessons-learned.md): what building this MVP has taught so far
- [How It Works](./how-it-works.md): the current runtime flow from trace capture to UI
- [Architecture](./architecture.md): system layers, major modules, and data flow
- [Improvement Roadmap](./improvement-roadmap.md): the most useful next improvements
- [Research Inspiration](./research-inspiration.md): papers influencing the design direction
- [Paper Notes](./papers/README.md): one note per paper, focused on what is actually useful here

## Suggested Reading Order

1. [Repo Overview](./repo-overview.md)
2. [How It Works](./how-it-works.md)
3. [Lessons Learned](./lessons-learned.md)
4. [Architecture](./architecture.md)
5. [Improvement Roadmap](./improvement-roadmap.md)
6. [Research Inspiration](./research-inspiration.md)
7. [Paper Notes](./papers/README.md)

## Documentation Principles

This project is still an MVP, so the docs try to stay honest about two things:

- what is implemented now
- what is intended but not fully wired yet

That distinction matters here. The event model is already useful. Persistence, replay, and the full debugger UI still need real work.

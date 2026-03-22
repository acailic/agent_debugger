# Documentation

This folder contains the repo's working documentation.

## Start Here

- [Repo Overview](./repo-overview.md): what the repository contains, what works, and what is still incomplete
- [Lessons Learned](./lessons-learned.md): what building this MVP has taught so far
- [How It Works](./how-it-works.md): learning-oriented walkthrough of the current implementation
- [Architecture](./architecture.md): system layers, major modules, and data flow
- [Improvement Roadmap](./improvement-roadmap.md): concrete ways to make the project better
- [Research Inspiration](./research-inspiration.md): papers influencing the design direction
- [Paper Notes](./papers/README.md): one article per inspiration paper with lessons and repo-specific insights

## Suggested Reading Order

1. [Repo Overview](./repo-overview.md)
2. [How It Works](./how-it-works.md)
3. [Lessons Learned](./lessons-learned.md)
4. [Architecture](./architecture.md)
5. [Improvement Roadmap](./improvement-roadmap.md)
6. [Research Inspiration](./research-inspiration.md)
7. [Paper Notes](./papers/README.md)

## Documentation Principles

This repo is still an MVP, so the docs should stay honest about two things:

- what is implemented now
- what is intended but not fully wired yet

That distinction matters in this project because the event model and tracing flow are already promising, while persistence, replay, and the full frontend debugger still need work.

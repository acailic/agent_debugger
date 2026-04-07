---
title: Contributing
description: How to contribute to Peaky Peek
---

# Contributing to Peaky Peek

We welcome contributions to Peaky Peek! This guide will help you get started.

## Quick Start

```bash
# Clone and install
git clone https://github.com/acailic/agent_debugger.git
cd agent_debugger
pip install -e ".[dev]"

# Install frontend dependencies
cd frontend && npm install && cd ..

# Run tests
python3 -m pytest -q

# Lint
ruff check .

# Build frontend
cd frontend && npm run build
```

## Project Structure

- **`agent_debugger_sdk/`** — Python SDK for instrumenting AI agents
- **`api/`** — FastAPI server (query, replay, streaming, auth)
- **`frontend/`** — React + TypeScript + Vite UI
- **`collector/`** — Event ingestion and pipeline
- **`storage/`** — Database engine, migrations, repositories
- **`auth/`** — API key authentication
- **`redaction/`** — Security/privacy filters
- **`tests/`** — Python test suite

## Development Workflow

### 1. Branch Off `main`

Create a branch for your work:

```bash
git checkout main
git pull origin main
git checkout -b feature/your-feature-name
```

### 2. Make Targeted Changes

Read the smallest set of files needed first, then make focused changes.

### 3. Validate Your Changes

Run appropriate validation:

```bash
# For Python changes
ruff check .
python3 -m pytest -q

# For frontend changes
cd frontend && npm run build

# For specific tests
python3 -m pytest -q tests/test_api_contract.py -k sessions
```

### 4. Check Boundaries

Before changing shared shapes, inspect both sides:

- **API ↔ frontend**: `api/schemas.py`, `frontend/src/types/index.ts`, `frontend/src/api/client.ts`
- **SDK ↔ API**: `agent_debugger_sdk/core/`, `api/schemas.py`
- **Auto-instrumentation**: `agent_debugger_sdk/auto_patch/`, `agent_debugger_sdk/adapters/`

## Code Style

### Python

- **Formatter**: Ruff with line length 120
- **Rules**: E/F/I (error, flake8, isort)
- **Import style**: Absolute imports from project root

```bash
# Check style
ruff check .

# Auto-fix
ruff check . --fix
```

### TypeScript

- **Formatter**: Vite/ESLint defaults
- **Style**: Standard React patterns

```bash
cd frontend

# Check style
npm run lint

# Fix
npm run lint -- --fix
```

## Running Locally

### Start the Backend

```bash
# Using make
make server

# Or directly
uvicorn api.main:app --reload --port 8000
```

### Start the Frontend

```bash
# Using make
make frontend

# Or directly
cd frontend && npm run dev
```

### Seed Demo Data

```bash
make demo-seed
```

## Testing

### Run All Tests

```bash
python3 -m pytest -q
```

### Run Specific Tests

```bash
# Test file
python3 -m pytest -q tests/test_api_contract.py

# Test with verbose output
python3 -m pytest -v tests/sdk/core/test_session_manager.py

# Run integration tests
python3 -m pytest -q -m integration
```

### Test Coverage

```bash
python3 -m pytest --cov=agent_debugger_sdk --cov=api --cov-report=html
```

## Commit Messages

Use conventional commits:

- `feat:` — New feature
- `fix:` — Bug fix
- `refactor:` — Code refactoring
- `docs:` — Documentation changes
- `test:` — Test changes
- `chore:` — Maintenance tasks

Examples:

```bash
git commit -m "feat: add Anthropic SDK integration"
git commit -m "fix: resolve session ID collision in concurrent traces"
git commit -m "docs: update API reference with new endpoints"
```

## Pull Requests

### Before Submitting

1. **Update documentation** if you changed behavior
2. **Add tests** for new features or bug fixes
3. **Run the full test suite** and ensure all tests pass
4. **Update CHANGELOG.md** if applicable

### PR Description Template

```markdown
## Description
Brief description of changes

## Type
- [ ] Bug fix
- [ ] Feature
- [ ] Breaking change
- [ ] Documentation

## Testing
How was this tested?

## Checklist
- [ ] Tests pass
- [ ] Documentation updated
- [ ] No breaking changes (or documented)
```

## Reporting Issues

Use [GitHub Issues](https://github.com/acailic/agent_debugger/issues) with:

- **Minimal reproduction steps**
- **Expected vs actual behavior**
- **Relevant logs or error messages**
- **Environment details** (OS, Python version, etc.)

## Areas Where We Need Help

### High Priority

- [ ] Additional framework adapters (CrewAI, AutoGen, LlamaIndex)
- [ ] Performance optimization for large trace sets
- [ ] Enhanced analytics and insights
- [ ] Documentation improvements

### Medium Priority

- [ ] Export functionality (LangSmith, etc.)
- [ ] Cost optimization suggestions
- [ ] Multi-agent comparison view
- [ ] Additional test coverage

### Low Priority

- [ ] Alternative UI themes
- [ ] Plugin system for custom analyzers
- [ ] Grafana/Prometheus metrics

## Design Philosophy

From [`CLAUDE.md`](../CLAUDE.md):

- **Ruthless simplicity** — Every abstraction must justify itself
- **Start minimal** — Keep the core path coherent before adding depth
- **Direct integration** — Minimal wrappers around frameworks
- **80/20 principle** — High-value features first

## Getting Help

- **Documentation**: Check the [docs site](https://acailic.github.io/agent_debugger/)
- **Issues**: Search [existing issues](https://github.com/acailic/agent_debugger/issues)
- **Discussions**: Use GitHub Discussions for questions

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](../LICENSE).

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow
- Assume good intentions

Thank you for contributing to Peaky Peek! 🚀

## Next Steps

- [Getting Started](getting-started.md) — 5-minute quickstart
- [Installation](installation.md) — Install Peaky Peek
- [Architecture](architecture.md) — System design overview

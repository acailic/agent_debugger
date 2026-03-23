# Contributing to Peaky Peek

Thank you for your interest in contributing! This document will help you get started.

## Architecture Overview

Peaky Peek is organized as a modular pipeline for agent debugging:

```
SDK → Collector → API → Storage → Frontend
```

- **SDK** (`agent_debugger_sdk/`) — Lightweight tracing library for instrumenting agent code with framework adapters
- **Collector** (`collector/`) — Event buffering and persistence pipeline that routes data to storage
- **API** (`api/`) — FastAPI server providing REST endpoints and SSE for real-time event streaming
- **Storage** (`storage/`) — SQLAlchemy-based persistence layer with SQLite/PostgreSQL support
- **Frontend** (`frontend/`) — React + TypeScript UI for visualizing decision trees, tool calls, and replay

The system captures a hierarchy: `Session → Trace → Event → Decision → Tool Call → Checkpoint`. See [ARCHITECTURE.md](./ARCHITECTURE.md) for full details.

## Development Environment Setup

### Prerequisites

- Python 3.10 or later
- Node.js 18+ (for frontend)
- Git

### Clone and Install

```bash
# Clone the repository
git clone https://github.com/acailic/agent_debugger
cd agent_debugger

# Install in editable mode with server dependencies
pip install -e ".[server]"

# Verify installation
python -m pytest -q
```

### Seed Demo Data

```bash
# Populate local database with example sessions
python scripts/seed_demo_sessions.py
```

This creates reusable benchmark sessions for testing and development.

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The dev server runs on `http://localhost:5173`.

### Run the API Server

```bash
uvicorn api.main:app --reload --port 8000
```

The API is available at `http://localhost:8000` with docs at `http://localhost:8000/docs`.

## Good First Issues

We welcome contributions in these areas:

### 1. Framework Adapters

Add support for new agent frameworks by creating adapter classes in `agent_debugger_sdk/adapters/`. Current adapters:
- PydanticAI
- LangChain
- CrewAI

Example: Add an adapter for AutoGen, Semantic Kernel, or a custom framework.

### 2. Seed Scenarios

Add demo data scenarios in `benchmarks/` to showcase debugging capabilities. Scenarios should:
- Represent realistic agent failure modes
- Include decision trees, tool calls, and checkpoints
- Be reusable for testing and demos

### 3. API Endpoints

Extend the FastAPI server in `api/` with new query or analysis endpoints:
- Session search filters
- Event aggregation APIs
- Comparison views for multiple runs

### 4. Frontend Components

Improve the UI in `frontend/src/`:
- Decision tree visualizations
- Tool call inspectors
- Session replay controls
- Search and filtering interfaces

Check [GitHub Issues](https://github.com/acailic/agent_debugger/issues) for tags like `good first issue` or `help wanted`.

## PR Process

### Branch Naming

Use conventional prefixes:
- `feature/` — New features or enhancements
- `fix/` — Bug fixes
- `docs/` — Documentation changes
- `refactor/` — Code refactoring
- `test/` — Test additions or updates

Example: `feature/add-autogen-adapter`

### Commit Messages

Follow [conventional commits](https://www.conventionalcommits.org/):

```
type(scope): description

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Example:
```
feat(sdk): add AutoGen framework adapter

Implements tracing for AutoGen multi-agent conversations.
Includes decision capture and tool call instrumentation.

Closes #123
```

### Test Expectations

All tests must pass before merging:

```bash
# Run full test suite
python -m pytest -v

# Run specific test file
python -m pytest tests/test_collector.py -v
```

### Code Review

1. Fork the repository and create a feature branch
2. Make your changes and add tests
3. Ensure tests pass and linting is clean
4. Submit a pull request with a clear description
5. Address review feedback
6. Once approved, maintainers will merge

### Review Checklist

- [ ] Tests pass locally
- [ ] New features include tests
- [ ] Documentation updated (if applicable)
- [ ] Commit messages follow conventions
- [ ] No unrelated changes included

## Running Tests

### Python Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=agent_debugger_sdk --cov=collector --cov=api --cov=storage

# Run specific test module
pytest tests/test_sdk.py -v

# Run async tests only
pytest tests/ -k "async" -v
```

### Frontend Build

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Run frontend tests
npm run test
```

### Type Checking

```bash
# Run mypy for static type checking (if configured)
mypy agent_debugger_sdk/ collector/ api/ storage/
```

### Database Reset

```bash
# Remove local database
rm agent_debugger.db

# Re-seed demo data
python scripts/seed_demo_sessions.py
```

## Additional Resources

- [ARCHITECTURE.md](./ARCHITECTURE.md) — Full system design
- [SDK_README.md](./SDK_README.md) — SDK usage guide
- [docs/integration.md](./docs/integration.md) — Framework integration docs
- [GitHub Issues](https://github.com/acailic/agent_debugger/issues) — Bug reports and feature requests

## Questions?

Feel free to open an issue or start a discussion. We're happy to help new contributors get started!

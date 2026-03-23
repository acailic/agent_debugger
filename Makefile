.PHONY: help server frontend demo-setup demo-seed demo-live demo-safety demo-research install install-dev test lint

# ── Help ─────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Agent Debugger — common targets"
	@echo ""
	@echo "  Development"
	@echo "    make install       Install full stack (SDK + server)"
	@echo "    make install-dev   Install with dev dependencies"
	@echo "    make server        Start FastAPI server on :8000"
	@echo "    make frontend      Start React dev server on :5173"
	@echo "    make test          Run test suite"
	@echo "    make lint          Run ruff linter"
	@echo ""
	@echo "  Demo recording"
	@echo "    make demo-setup    Seed all benchmark data, then print next steps"
	@echo "    make demo-seed     Seed benchmark sessions only"
	@echo "    make demo-live     Run live-stream demo (needs server running)"
	@echo "    make demo-safety   Run safety audit demo (needs server running)"
	@echo "    make demo-research Run research agent demo (needs server running)"
	@echo ""

# ── Development ──────────────────────────────────────────────────────────────
install:
	pip install -e ".[server]"

install-dev:
	pip install -e ".[server,langchain,pydantic-ai,crewai]"
	pip install pytest pytest-asyncio ruff

server:
	uvicorn api.main:app --reload --port 8000

frontend:
	cd frontend && npm install && npm run dev

test:
	python -m pytest -q

lint:
	ruff check .

# ── Demo recording ────────────────────────────────────────────────────────────
demo-seed:
	python scripts/seed_demo_sessions.py

demo-setup: demo-seed
	@echo ""
	@echo "  ✓ Benchmark sessions seeded."
	@echo ""
	@echo "  Next steps for recording:"
	@echo "    Terminal 1:  make server"
	@echo "    Terminal 2:  make frontend"
	@echo "    Terminal 3:  make demo-live    (or demo-safety, demo-research)"
	@echo ""
	@echo "  Open http://localhost:5173 and start your screen recorder."
	@echo ""

demo-live:
	python examples/demo_live_stream.py

demo-safety:
	python examples/demo_safety_audit.py

demo-research:
	python examples/mock_research_agent.py

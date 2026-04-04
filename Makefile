.PHONY: help server frontend demo-setup demo-seed demo-live demo-safety demo-research install install-dev test lint dead-code

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
	@echo "    make dead-code     Run dead code detection"
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

API_PORT ?= 8000

server:
	uvicorn api.main:app --reload --port $(API_PORT)

frontend:
	cd frontend && API_PORT=$(API_PORT) npm run dev

test:
	python3 -m pytest -q

lint:
	ruff check .

dead-code:
	@bash scripts/check_dead_code.sh

# ── Demo recording ────────────────────────────────────────────────────────────
demo-seed:
	python3 scripts/seed_demo_sessions.py

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
	python3 examples/08_live_stream.py

demo-safety:
	python3 examples/06_safety_audit.py

demo-research:
	python3 examples/02_research_agent.py

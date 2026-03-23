# Examples

Focused, self-contained scenarios for testing and exploring Peaky Peek.

## Prerequisites

Start the API server before running any example:

    # From the repo root
    uvicorn api.main:app --port 8000
    # Optional: open the UI at http://localhost:5173

Then in a second terminal:

    python examples/01_hello.py

## All Examples

| # | File | Demonstrates | What to look for in the UI |
|---|------|--------------|---------------------------|
| 01 | `01_hello.py` | Minimal trace: decision + tool call + checkpoint | Timeline, Decisions panel |
| 02 | `02_research_agent.py` | Multi-step mock research agent | Decision tree, Tool inspector |
| 03 | `03_langchain.py` | LangChain adapter (requires `pip install langchain-core`) | LLM events in timeline |
| 04 | `04_pydantic_ai.py` | PydanticAI adapter (requires `pip install pydantic-ai`) | LLM request/response pairs |
| 05 | `05_checkpoint_replay.py` | Checkpoint creation and state fetch via REST API | Checkpoint panel, replay button |
| 06 | `06_safety_audit.py` | Safety audit trail: 3 adversarial scenarios | Safety filter, Refusals tab |
| 07 | `07_loop_detection.py` | Stuck agent loop triggering live behavior alert | Live alerts timeline |
| 08 | `08_live_stream.py` | Live event streaming with staged delays | Live summary panel |

## Optional dependencies

Examples 03 and 04 require optional framework packages not installed by default:

    pip install langchain-core    # for 03_langchain.py
    pip install pydantic-ai       # for 04_pydantic_ai.py

Both examples print a helpful install message and exit gracefully if the dependency is missing.

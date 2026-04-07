---
title: Installation
description: Install Peaky Peek via pip, Docker, or from source
---

# Installation

Peaky Peek can be installed via pip, Docker, or from source for development.

## pip Installation (Recommended)

### Server Installation

```bash
pip install peaky-peek-server
peaky-peek --open
```

This installs:
- The FastAPI server
- The React frontend
- SQLite database support
- All dependencies

### SDK-Only Installation

If you only want the SDK for instrumenting agents:

```bash
pip install peaky-peek
```

Then connect to a remote server:

```python
from agent_debugger_sdk import init

init(
    endpoint="https://api.agentdebugger.dev",
    api_key="ad_live_...",
)
```

## Docker Installation

### Using Docker Hub

```bash
docker pull ghcr.io/acailic/agent_debugger:latest
docker run -p 8000:8000 -v ./traces:/app/traces ghcr.io/acailic/agent_debugger:latest
```

### Building from Source

```bash
docker build -t peaky-peek .
docker run -p 8000:8000 -v ./traces:/app/traces peaky-peek
```

## Development Installation

For local development:

```bash
# Clone the repository
git clone https://github.com/acailic/agent_debugger.git
cd agent_debugger

# Install in editable mode with dev dependencies
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

## Verification

Verify your installation:

```bash
# Check Python version (requires 3.10+)
python3 --version

# Check installation
python3 -c "import agent_debugger_sdk; print(agent_debugger_sdk.__version__)"

# Start the server
peaky-peek --open
```

## Running the Server

### Production Mode

```bash
peaky-peek
```

### Development Mode

```bash
# Backend
uvicorn api.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm run dev
```

### Using Make Commands

```bash
make server      # Start backend
make frontend    # Start frontend dev server
make demo-seed   # Seed demo data
```

## Three SDK Usage Patterns

### 1. Decorator Pattern

Simplest integration for existing code:

```python
from agent_debugger_sdk import trace

@trace
async def my_agent(prompt: str) -> str:
    return await llm_call(prompt)
```

### 2. Context Manager Pattern

Fine-grained control over tracing:

```python
from agent_debugger_sdk import TraceContext

async with TraceContext(agent_name="weather_agent") as ctx:
    await ctx.record_decision(
        reasoning="User asked for weather",
        confidence=0.9,
        chosen_action="call_weather_api",
    )
    result = await call_weather_api()
    await ctx.record_tool_result("weather_api", result=result)
```

### 3. Auto-Patch Pattern

Zero-code instrumentation:

```bash
PEAKY_PEEK_AUTO_PATCH=all python your_agent.py
```

Or programmatically:

```python
import agent_debugger_sdk.auto_patch  # activates on import

# Now all LLM calls are traced automatically
result = await my_agent()
```

## Supported Frameworks

Auto-patching works with:

- **PydanticAI** — Full integration
- **LangChain** — Handler-based tracing
- **OpenAI SDK** — Direct instrumentation
- **Anthropic SDK** — Direct instrumentation
- **CrewAI** — Agent tracing
- **AutoGen** — Multi-agent support
- **LlamaIndex** — Tool and LLM calls

## Environment Variables

Configure Peaky Peek via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_DEBUGGER_API_KEY` | - | API key for cloud mode |
| `AGENT_DEBUGGER_URL` | `http://localhost:8000` | Collector endpoint |
| `AGENT_DEBUGGER_ENABLED` | `true` | Enable or disable tracing |
| `AGENT_DEBUGGER_SAMPLE_RATE` | `1.0` | Sampling rate (0.0-1.0) |
| `AGENT_DEBUGGER_REDACT_PROMPTS` | `false` | Redact prompts before storage |
| `AGENT_DEBUGGER_MAX_PAYLOAD_KB` | `100` | Max payload size for events |
| `PEAKY_PEEK_AUTO_PATCH` | - | Auto-patch frameworks (`all` or comma-separated list) |

## Troubleshooting

### Port Already in Use

```bash
# Use a different port
uvicorn api.main:app --port 8001
```

### Database Lock Issues

```bash
# Remove existing database
rm traces/agent_debugger.db
```

### Frontend Build Errors

```bash
# Clear node_modules and reinstall
cd frontend
rm -rf node_modules package-lock.json
npm install
npm run build
```

### Import Errors

```bash
# Ensure you're using Python 3.10+
python3 --version

# Reinstall in editable mode
pip install -e .
```

## Next Steps

- [Getting Started](getting-started.md) — 5-minute quickstart
- [Integrations](integrations.md) — Framework-specific setup
- [Configuration](configuration.md) — Advanced configuration options

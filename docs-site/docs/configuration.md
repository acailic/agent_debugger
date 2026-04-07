---
title: Configuration
description: Environment variables, SDK configuration, and system settings
---

# Configuration

Peaky Peek can be configured via environment variables, SDK initialization, and configuration files.

## Environment Variables

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_DEBUGGER_API_KEY` | - | API key for cloud mode |
| `AGENT_DEBUGGER_URL` | `http://localhost:8000` | Collector endpoint URL |
| `AGENT_DEBUGGER_ENABLED` | `true` | Enable or disable tracing |
| `AGENT_DEBUGGER_SAMPLE_RATE` | `1.0` | Sampling rate (0.0-1.0) |
| `AGENT_DEBUGGER_REDACT_PROMPTS` | `false` | Redact prompts before storage |
| `AGENT_DEBUGGER_MAX_PAYLOAD_KB` | `100` | Max payload size for events |

### Auto-Patch Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `PEAKY_PEEK_AUTO_PATCH` | - | Auto-patch frameworks (`all` or comma-separated list) |
| `PEAKY_PEEK_AUTO_PATCH_EXCLUDE` | - | Frameworks to exclude from auto-patching |

### Database Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./traces/agent_debugger.db` | Database connection URL |
| `REDIS_URL` | - | Redis URL for distributed buffer (optional) |

### Server Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_DEBUGGER_CORS_ORIGINS` | `*` | CORS allowed origins |
| `AGENT_DEBUGGER_PORT` | `8000` | Server port |
| `AGENT_DEBUGGER_HOST` | `0.0.0.0` | Server host |

### Analytics Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ANALYTICS_DB_PATH` | `./traces/analytics.db` | Analytics database path |
| `ANALYTICS_ENABLED` | `true` | Enable analytics aggregations |

## SDK Configuration

### Basic Configuration

```python
from agent_debugger_sdk import init

init()
```

This uses default settings (local mode, localhost:8000).

### Cloud Configuration

```python
from agent_debugger_sdk import init

init(
    api_key="ad_live_...",
    endpoint="https://api.agentdebugger.dev",
)
```

### Advanced Configuration

```python
from agent_debugger_sdk import init

init(
    api_key="ad_live_...",
    endpoint="https://api.agentdebugger.dev",
    enabled=True,
    sample_rate=1.0,
    redact_prompts=False,
    max_payload_kb=100,
)
```

### Configuration Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_key` | `str` | `None` | API key for cloud mode |
| `endpoint` | `str` | `http://localhost:8000` | Collector endpoint URL |
| `enabled` | `bool` | `True` | Enable or disable tracing |
| `sample_rate` | `float` | `1.0` | Sampling rate (0.0-1.0) |
| `redact_prompts` | `bool` | `False` | Redact prompts before storage |
| `max_payload_kb` | `int` | `100` | Max payload size in KB |

## Configuration File

You can also use a configuration file (`peaky_peek_config.json`):

```json
{
  "api_key": "ad_live_...",
  "endpoint": "https://api.agentdebugger.dev",
  "enabled": true,
  "sample_rate": 1.0,
  "redact_prompts": false,
  "max_payload_kb": 100,
  "auto_patch": ["pydantic_ai", "langchain"],
  "cors_origins": ["http://localhost:3000"],
  "database_url": "sqlite:///./traces/agent_debugger.db"
}
```

Then load it:

```python
from agent_debugger_sdk import init_from_config

init_from_config("peaky_peek_config.json")
```

## Redaction Configuration

### Prompt Redaction

Enable prompt redaction to sensitive data:

```python
from agent_debugger_sdk import init

init(redact_prompts=True)
```

Or via environment variable:

```bash
export AGENT_DEBUGGER_REDACT_PROMPTS=true
```

### Custom Redaction Rules

You can define custom redaction rules:

```python
from agent_debugger_sdk.redaction import RedactionConfig

config = RedactionConfig(
    redact_prompts=True,
    redact_patterns=[
        r"Bearer\s+[A-Za-z0-9\-._~+/]+=*",  # Bearer tokens
        r"password\s*[:=]\s*\S+",            # Passwords
    ],
)

init(redaction_config=config)
```

## Transport Configuration

### HTTP Transport

Default HTTP transport with retry:

```python
from agent_debugger_sdk.transport import HttpTransport

transport = HttpTransport(
    endpoint="http://localhost:8000",
    timeout=30,
    max_retries=3,
)

init(transport=transport)
```

### SSE Transport

For real-time streaming:

```python
from agent_debugger_sdk.transport import SseTransport

transport = SseTransport(
    endpoint="http://localhost:8000",
    reconnect_interval=5,
)

init(transport=transport)
```

## Buffer Configuration

### In-Memory Buffer

Default in-memory buffer:

```python
from collector import create_buffer

buffer = create_buffer(backend="memory")
```

### Redis Buffer

For distributed systems:

```python
from collector import create_buffer

buffer = create_buffer(backend="redis", redis_url="redis://localhost:6379")
```

Or via environment variable:

```bash
export REDIS_URL=redis://localhost:6379
```

## Database Configuration

### SQLite

Default SQLite configuration:

```bash
export DATABASE_URL=sqlite:///./traces/agent_debugger.db
```

### PostgreSQL

For production use:

```bash
export DATABASE_URL=postgresql+asyncpg://user:password@localhost/agent_debugger
```

### Database Pooling

Configure connection pool:

```python
from storage.engine import configure_pool

configure_pool(
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
)
```

## CORS Configuration

Configure CORS for the API:

```bash
export AGENT_DEBUGGER_CORS_ORIGINS="http://localhost:3000,https://example.com"
```

Or for all origins (default):

```bash
export AGENT_DEBUGGER_CORS_ORIGINS="*"
```

## Sampling Configuration

### Fixed Rate Sampling

Sample a fixed percentage of events:

```python
init(sample_rate=0.1)  # Sample 10% of events
```

### Dynamic Sampling

Implement custom sampling logic:

```python
from agent_debugger_sdk import init

def should_sample(event):
    # Only sample high-importance events
    return event.importance > 0.7

init(sample_rate=1.0, sample_filter=should_sample)
```

## Logging Configuration

### Python Logging

Configure Python logging:

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Or for the SDK specifically
logging.getLogger("agent_debugger_sdk").setLevel(logging.DEBUG)
```

### Server Logging

Configure server logging:

```bash
export LOG_LEVEL=DEBUG
export LOG_FORMAT=json  # or 'text'
```

## Testing Configuration

### Test Mode

Enable test mode for deterministic behavior:

```python
from agent_debugger_sdk import init

init(
    enabled=True,
    test_mode=True,
    endpoint="http://localhost:8000",
)
```

### Mock Transport

Use mock transport for testing:

```python
from agent_debugger_sdk.transport import MockTransport

transport = MockTransport()
init(transport=transport)
```

## Deployment Configuration

### Docker Environment

Create `.env` file for Docker:

```env
AGENT_DEBUGGER_URL=http://api:8000
DATABASE_URL=postgresql+asyncpg://postgres:password@db/agent_debugger
REDIS_URL=redis://redis:6379
AGENT_DEBUGGER_CORS_ORIGINS=*
```

### Kubernetes ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: peaky-peek-config
data:
  AGENT_DEBUGGER_URL: "http://peaky-peek-api:8000"
  DATABASE_URL: "postgresql+asyncpg://postgres:password@postgres/agent_debugger"
  AGENT_DEBUGGER_ENABLED: "true"
  AGENT_DEBUGGER_SAMPLE_RATE: "1.0"
```

## Troubleshooting

### Debug Mode

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG
export AGENT_DEBUGGER_DEBUG=true
```

### Connection Issues

Test connection to collector:

```python
from agent_debugger_sdk import test_connection

test_connection(endpoint="http://localhost:8000")
```

### Configuration Validation

Validate your configuration:

```python
from agent_debugger_sdk.config import validate_config

config = {
    "endpoint": "http://localhost:8000",
    "sample_rate": 1.0,
}

validate_config(config)
```

## Next Steps

- [Getting Started](getting-started.md) — 5-minute quickstart
- [Installation](installation.md) — Install Peaky Peek
- [Integrations](integrations.md) — Framework-specific setup

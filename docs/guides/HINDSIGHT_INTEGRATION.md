# Hindsight Memory Integration

This guide explains how to integrate Peaky Peek with Hindsight memory banks for persistent debugging insights.

## Overview

The HindsightMemoryAdapter exports trace insights to Hindsight memory banks, mapping:
- **Failure patterns** → Experience memories
- **Entity summaries** → World fact memories  
- **Session digests** → Observation memories

It also supports TEMPR (Temporal Episode Memory with Progressive Retrieval) for recalling relevant past debugging context.

## Configuration

### Environment Variables

```bash
# Enable Hindsight integration
export AGENT_DEBUGGER_HINDSIGHT_ENABLED=true

# Hindsight endpoint (default: http://localhost:9000)
export HINDSIGHT_URL=https://hindsight.example.com

# Memory bank ID (default: agent_debugger)
export HINDSIGHT_BANK_ID=my_agent_bank

# Optional API key for authenticated Hindsight
export HINDSIGHT_API_KEY=your-api-key
```

### SDK Initialization

```python
from agent_debugger_sdk import init
from agent_debugger_sdk.adapters import HindsightMemoryAdapter, HindsightConfig

# Initialize with Hindsight enabled
init(
    hindsight_enabled=True,
    hindsight_endpoint="https://hindsight.example.com",
    hindsight_bank_id="my_agent_bank",
)

# Or configure manually
config = HindsightConfig(
    endpoint="https://hindsight.example.com",
    bank_id="my_agent_bank",
    api_key="your-api-key",
    tempr_enabled=True,
    tempr_top_k=5,
)

adapter = HindsightMemoryAdapter(config)
```

## Usage

### Automatic Export on Session Completion

```python
from agent_debugger_sdk.core.exporters.pipeline import MemoryExporterHook
from agent_debugger_sdk.adapters import HindsightMemoryAdapter, HindsightConfig

# Create Hindsight adapter
hindsight_config = HindsightConfig(
    endpoint="https://hindsight.example.com",
    bank_id="my_agent_bank",
)
hindsight_adapter = HindsightMemoryAdapter(hindsight_config)

# Create exporter hook
export_hook = MemoryExporterHook(
    exporter=hindsight_adapter,
    export_on_completion=True,
)

# Hook will auto-export when sessions complete
```

### Manual Export

```python
from agent_debugger_sdk.core.exporters.insights import InsightBuilder
from agent_debugger_sdk.adapters import HindsightMemoryAdapter

# Build insight from session data
builder = InsightBuilder()
insight = builder.build_insight(session, events, checkpoints, analysis)

# Export to Hindsight
adapter = HindsightMemoryAdapter()
await adapter.export(insight)
```

### Query Similar Sessions

```python
# Query for similar debugging contexts
similar = await adapter.query_similar(
    session_digest=current_session_digest,
    limit=10,
)

for session in similar:
    print(f"Similar session: {session.session_id}")
    print(f"  Errors: {session.errors}")
    print(f"  Replay value: {session.replay_value}")
```

### Get Top Failure Patterns

```python
# Get failure patterns across all sessions
patterns = await adapter.get_failure_patterns(
    agent_name="my-agent",
    limit=20,
)

for pattern in patterns:
    print(f"Pattern: {pattern.fingerprint}")
    print(f"  Occurrences: {pattern.count}")
    print(f"  Severity: {pattern.severity}")
```

## Memory Type Mapping

| Peaky Insight | Hindsight Memory Type | Description |
|--------------|---------------------|-------------|
| FailurePattern | experience_memory | Learned from failures and errors |
| SessionDigest | observation_memory | Session observations and outcomes |
| EntitySummary | world_fact_memory | Facts about tools, models, entities |

## TEMPR Retrieval

The adapter uses TEMPR (Temporal Episode Memory with Progressive Retrieval) to find relevant past debugging contexts:

```python
# TEMPR is enabled by default
config = HindsightConfig(
    tempr_enabled=True,
    tempr_top_k=5,          # Retrieve top 5 matches
    tempr_threshold=0.3,     # Minimum similarity score
)
```

Queries are built from session attributes:
- Agent name and framework
- Error counts and failure patterns
- Tags and metadata

## Health Check

```python
health = await adapter.health_check()

if health["status"] == "healthy":
    print("Hindsight connection is healthy")
    print(f"Bank: {health['bank_id']}")
else:
    print(f"Hindsight unhealthy: {health.get('error')}")
```

## Error Handling

```python
from agent_debugger_sdk.core.exporters import ExportError

try:
    await adapter.export(insight)
except ExportError as e:
    print(f"Export failed: {e.message}")
    if e.cause:
        print(f"Cause: {e.cause}")
```

## Testing

Use mock Hindsight servers for testing:

```python
from agent_debugger_sdk.adapters import HindsightConfig

config = HindsightConfig(
    endpoint="http://localhost:9000",  # Mock server
    bank_id="test_bank",
    enabled=True,
)

adapter = HindsightMemoryAdapter(config)
```

## Troubleshooting

### Connection Issues

```bash
# Test Hindsight endpoint
curl https://hindsight.example.com/api/v1/health

# Check firewall rules
telnet hindsight.example.com 9000
```

### Bank Not Found

```python
# Ensure bank exists or create it
# POST /api/v1/banks/{bank_id}
{
    "name": "My Agent Bank",
    "description": "Debugging insights"
}
```

### Empty Results

- Verify TEMPR settings (threshold, top_k)
- Check that memories have been exported
- Ensure query terms match memory content

# Changelog Entry for v0.1.4

## [0.1.4] - 2026-03-24

### Added

#### Auto-Patching Framework Support
- **Tier 1 Adapters**: OpenAI and Anthropic with zero-code instrumentation
- **Tier 2 Adapters**: LangChain and PydanticAI with auto-patch lifecycle
- **Tier 3 Adapters**: CrewAI, AutoGen, and LlamaIndex (experimental)
- Auto-patch registry with activate/deactivate lifecycle management

#### Replay Depth (Checkpoint L1+L2)
- Standardized checkpoint schemas for LangChain, PydanticAI, and custom agents
- `TraceContext.restore()` for manual execution restoration from checkpoints
- REST endpoints: `GET /api/checkpoints/{id}` and `POST /api/checkpoints/{id}/restore`
- Checkpoint validation helpers with framework-specific state validation

#### Developer Experience Improvements
- `peaky-peek` CLI command with --host, --port, --open, --version flags
- Pricing module with auto-cost-calculation for LLM response events
- Bundled frontend UI served from `/ui/` endpoint
- JSON export endpoint: `GET /api/sessions/{id}/export`
- 8 comprehensive examples covering all major SDK features

#### Intelligence & Analysis
- Decomposed TraceIntelligence into focused components
- Causal analysis module for failure-to-cause reconstruction
- Failure diagnostics with adaptive analysis
- Live monitoring with real-time alerts

### Refactored
- Decomposed TraceIntelligence into focused components (causal_analysis, failure_diagnostics, live_monitor)
- Decoupled API dependencies from main.py for better modularity
- Improved repository pattern with cleaner separation of concerns
- Runtime context and persistence flow improvements

### Fixed
- CI test failures - all tests now passing (523 passed, 1 skipped)
- App context initialization in test fixtures
- Transport mock setup for logging tests
- Import ordering and line length lint issues
- Alembic logger configuration
- Database session management in tests

### Documentation
- Getting started guide (5-minute tutorial)
- Quick wins implementation plan
- Examples folder with 8 working code samples
- Landing page design spec for GitHub Pages
- Comprehensive demo recording guide
- Top 0.1% strategy roadmap

### Examples
- 01_hello.py - Basic agent trace
- 02_research_agent.py - Research agent with tools
- 03_langchain.py - LangChain adapter integration
- 04_pydantic_ai.py - PydanticAI adapter integration
- 05_checkpoint_replay.py - Checkpoint creation and restore
- 06_safety_audit.py - Safety audit trail
- 07_loop_detection.py - Stuck agent loop alert
- 08_live_stream.py - Live SSE streaming

### Migration Notes
- Checkpoint schemas are now typed and validated
- Auto-patch adapters require explicit activate/deactivate calls
- TraceIntelligence API has changed (now decomposed into modules)

### Contributors
Thanks to all contributors who made this release possible!

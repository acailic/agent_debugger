# Changelog

All notable changes to Peaky Peek will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.19] - 2026-06-13

### Internal
- Deduplicated StrEnum Python 3.10 compatibility shim into `agent_debugger_sdk.core._compat`
- Added composite database indexes for events, sessions, checkpoints
- Replaced module-level `_shared_app` pattern with session-scoped `shared_app` fixture
- Enabled pyright type checking in CI

## [0.1.18] - 2026-06-10

### Fixed
- Corrected stepper test fixture and assertions

### Added
- Agent stepper, swimlane debugger, and violation detection features
- Reasoning editor and divergence detection features

## [0.1.17] - 2026-06-08

### Added
- Research-driven event behavior features
- Frame tracer and divergence detector

### Fixed
- Resolved all ruff lint errors across SDK and test files
- Python 3.10 compatibility for StrEnum in core modules

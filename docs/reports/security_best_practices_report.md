# Security Review Report

## Executive Summary

I did not find committed live credentials, private keys, or obvious sensitive tokens in the tracked repository contents.

The main residual risks are:

1. A tracked Claude settings file previously exposed a local absolute filesystem path and username. This has since been remediated (see LOW-01); it is documented here for history.
2. Ignored local SQLite databases exist in the working copy and contain runtime data, including hashed API-key material and event/session records. They are not tracked by git today, but they would be sensitive if someone force-added them or shared the repository directory as an archive.

## Low Severity

### LOW-01: Tracked local path leaks workstation username

**Status:** Resolved. The hook command in `.claude/settings.json` no longer embeds an absolute filesystem path; it resolves the repository root at runtime via `$(git rev-parse --show-toplevel)`, so no username or local directory layout is exposed.

**Impact:** (Historical, now remediated) Minor privacy leak. The repository previously exposed a developer-local absolute path that included the local username.

- Evidence: [.claude/settings.json](../../.claude/settings.json#L28)
- Detail: The hook command previously embedded a hardcoded `/home/<user>/...` path that revealed the local username and directory layout. It now derives the repo root with `$(git rev-parse --show-toplevel)`.
- Remediation: Replaced the hardcoded absolute path with an environment-derived repo-relative path (commit `7da42a8`, "security: add secret scanning and harden local config").

## Informational

### INFO-01: No committed secrets found in tracked files

- Evidence reviewed:
  - [.env.example](../../.env.example#L13)
  - [.env.example](../../.env.example#L18)
  - [tests/test_sdk_config.py](../../tests/test_sdk_config.py#L28)
  - [tests/test_sdk_transport.py](../../tests/test_sdk_transport.py#L27)
- Notes:
  - `.env.example` contains placeholders such as `sk-...`, not live values.
  - Test files use clearly synthetic sample keys like `ad_live_test123` and `ad_live_test`.
  - Targeted git-history searches for common secret formats did not return committed AWS keys, GitHub tokens, Slack tokens, Google API keys, JWTs, or private-key blocks.

### INFO-02: Sensitive local runtime artifacts exist but are gitignored

- Evidence:
  - [.gitignore](../../.gitignore#L20)
  - [.gitignore](../../.gitignore#L24)
  - [.gitignore](../../.gitignore#L26)
  - [.gitignore](../../.gitignore#L27)
- Notes:
  - Local ignored files currently present include `.coverage`, `traces/`, `dist/`, and SQLite databases under `data/`.
  - The local `data/agent_debugger.db` contains tables such as `api_keys`, `events`, `sessions`, and `checkpoints`.
  - The `api_keys` table appears to store hashed key material, not raw keys, and sampled pattern checks did not show obvious raw bearer tokens, OpenAI-style keys, passwords, or emails in the checked database fields.

## Scope and Method

- Searched tracked files for secret-related keywords and high-signal credential formats.
- Checked for tracked `.env`, key, certificate, and keystore-style files.
- Ran targeted git-history searches for common credential patterns.
- Reviewed ignore rules to confirm local runtime artifacts are excluded from git.
- Inspected local SQLite schemas and pattern counts without dumping record contents.

## Residual Gaps

- No dedicated entropy-based secret scanner such as `gitleaks` or `detect-secrets` was installed in this environment.
- The history review was targeted to high-signal credential patterns rather than a full scanner-backed audit of every commit blob.

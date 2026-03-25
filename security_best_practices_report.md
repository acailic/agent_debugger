# Security Review Report

## Executive Summary

I did not find committed live credentials, private keys, or obvious sensitive tokens in the tracked repository contents.

The main residual risks are:

1. A tracked Claude settings file exposes a local absolute filesystem path and username.
2. Ignored local SQLite databases exist in the working copy and contain runtime data, including hashed API-key material and event/session records. They are not tracked by git today, but they would be sensitive if someone force-added them or shared the repository directory as an archive.

## Low Severity

### LOW-01: Tracked local path leaks workstation username

**Impact:** Minor privacy leak. The repository exposes a developer-local absolute path that includes the local username.

- Evidence: [.claude/settings.json](/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/.claude/settings.json#L28)
- Detail: The hook command embeds `/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/...`, which reveals the local username `nistrator` and local directory layout.
- Recommendation: Replace the hardcoded absolute path with a repo-relative or environment-derived path.

## Informational

### INFO-01: No committed secrets found in tracked files

- Evidence reviewed:
  - [.env.example](/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/.env.example#L13)
  - [.env.example](/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/.env.example#L18)
  - [tests/test_sdk_config.py](/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/tests/test_sdk_config.py#L25)
  - [tests/test_sdk_transport.py](/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/tests/test_sdk_transport.py#L20)
- Notes:
  - `.env.example` contains placeholders such as `sk-...`, not live values.
  - Test files use clearly synthetic sample keys like `ad_live_test123` and `ad_live_test`.
  - Targeted git-history searches for common secret formats did not return committed AWS keys, GitHub tokens, Slack tokens, Google API keys, JWTs, or private-key blocks.

### INFO-02: Sensitive local runtime artifacts exist but are gitignored

- Evidence:
  - [.gitignore](/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/.gitignore#L10)
  - [.gitignore](/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/.gitignore#L24)
  - [.gitignore](/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/.gitignore#L26)
  - [.gitignore](/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/.gitignore#L27)
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

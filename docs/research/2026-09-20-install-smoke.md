# Install smoke: wheel launch → trace → query → restart → same trace

Date: 2026-09-20
Mission: Q12 first slice (roadmap W11) — "clean wheel launch → trace → query → restart
→ same trace, with explicit data directory and no source-tree dependency", plus the
Q13 acceptance remainder (a non-skipping real-service Redis CI job).

Reproducer: `scripts/install_smoke.sh` (bash, `set -euo pipefail`, exits nonzero on any
failure; keeps its temp workspace on failure with server-log tails printed to stderr).

## Environment

| Component | Version |
| --- | --- |
| OS | Ubuntu 24.04 (kernel 7.1.5-76070105-generic) |
| Python | 3.12.3 (system; also the venv/python in all images) |
| pip | 25.0.1 (upgraded inside the smoke venv) |
| Node / npm | v22.23.2 / 10.9.8 (publish.yml pins node 22) |
| Docker | 29.1.3, daemon reachable |
| Wheels built | `peaky_peek-0.4.0-py3-none-any.whl`, `peaky_peek_server-0.4.0-py3-none-any.whl` |
| Runtime deps resolved | fastapi 0.141.1, uvicorn 0.53.0, SQLAlchemy 2.0.54, aiosqlite 0.22.1, alembic 1.20.0, aiofiles 25.1.0, bcrypt 5.0.0, httpx 0.28.1 |

## Method

Both wheels were built the way `.github/workflows/publish.yml` builds them, in temp
copies of the repo (the checkout's `pyproject.toml` was never modified):

- **SDK**: temp copy → same version-substitution snippet as the `Set SDK version from
  tag` step (driven with the committed version) → `python -m build`.
- **Server**: temp copy → `cp pyproject-server.toml pyproject.toml` →
  `frontend: npm ci && npm run build` → version substitution → `python -m build`.
- Both wheels were installed into a **fresh venv under /tmp** (outside the checkout)
  together with the runtime dependency list mirrored from `ci.yml`
  (fastapi, uvicorn[standard], sqlalchemy[asyncio], aiosqlite, alembic, aiofiles,
  bcrypt, httpx). SDK wheel first, server wheel second (both ship a `peaky-peek`
  console script and the `agent_debugger_sdk` package; the server install must win
  the script).
- Verified **no source-tree dependency**: with `cwd` outside the checkout and
  `PYTHONPATH` unset, `agent_debugger_sdk`, `api` and `storage` all import from the
  venv's `site-packages` (asserted in the script).
- Server started via the installed `peaky-peek` console script on an ephemeral port
  with an **explicit data directory**:
  `AGENT_DEBUGGER_DB_URL=sqlite+aiosqlite:///<tmp>/data/install-smoke.db`, cwd outside
  the checkout.
- Traced with the **installed SDK without an API key**
  (`init(endpoint=...)` → local mode, unauthenticated loopback delivery):
  1 decision + 1 tool call + 1 tool result + 1 checkpoint, then queried back over
  HTTP (`GET /api/sessions`, `GET /api/sessions/{id}/trace`,
  `GET /api/sessions/{id}/checkpoints`). Server stopped, restarted against the same
  data directory, same session re-queried and event/checkpoint counts compared.

## Results

| Step | Result |
| --- | --- |
| SDK wheel build (publish-sdk path) | PASS |
| Server wheel build incl. frontend `npm ci && npm run build` (publish-server path) | PASS |
| Wheel content audit (packages, migrations, `frontend/dist/index.html`) | PASS (see finding 1) |
| Fresh-venv install of both wheels + runtime deps | PASS |
| Import isolation (site-packages only, cwd outside repo, PYTHONPATH unset) | PASS |
| Installed server start, explicit data dir, ephemeral port | PASS (after finding 1 fix) |
| SDK trace (no API key) → query over HTTP | PASS — 6 events, 1 checkpoint |
| Bundled UI `GET /ui/` | PASS — 200, HTML from wheel-bundled `frontend/dist` |
| Stop → restart same data dir → same trace | PASS — 6 events / 1 checkpoint before and after |
| Docker daemon | reachable |
| `docker build -t peaky-peek-smoke .` | PASS (after findings 2+3 fixes) |
| Container: trace → restart (mounted volume) → same trace | PASS — 6 events / 1 checkpoint; DB file visible on the host-mounted volume |
| Container UI `GET /ui/` | PASS — 200 |

## Findings

1. **`alembic.ini` is missing from BOTH wheels — this was fatal, now guarded.**
   `storage/engine.py` builds the Alembic config from
   `<package-parent>/alembic.ini` (i.e. `site-packages/alembic.ini` when installed)
   and `storage/migrations/env.py` called `fileConfig(config.config_file_name)`
   unconditionally, so the installed server crashed during lifespan with
   `FileNotFoundError: .../site-packages/alembic.ini doesn't exist` and uvicorn
   exited ("Application startup failed"). Fix applied in this change:
   `env.py` now guards on `os.path.exists(config.config_file_name)` (the standard
   Alembic template pattern; `engine.py` already overrides `script_location` and
   `sqlalchemy.url`, so the ini is not otherwise needed). Recommended follow-up:
   force-include `alembic.ini` in the wheel target of `pyproject-server.toml`.
2. **Dockerfile could not build: no `pyproject.toml` in the image.**
   `COPY pyproject-server.toml ./` left only `pyproject-server.toml` in `/app`, and
   `RUN pip install --no-cache-dir -e .` failed with "neither 'setup.py' nor
   'pyproject.toml' found". Fixed by copying it as `./pyproject.toml` — exactly the
   swap `publish.yml` performs (`cp pyproject-server.toml pyproject.toml`).
3. **Dockerfile did not copy `README.md`.** The server pyproject declares
   `readme = "README.md"`, so hatchling aborted metadata generation with
   `OSError: Readme file does not exist: README.md`. Fixed by adding
   `COPY README.md ./README.md`.
4. **Container persistence directory mismatch (recorded, not changed).** The image
   prepares `/app/traces`, but the default DB URL is the cwd-relative
   `./data/agent_debugger.db` → `/app/data`. A volume mounted at `/app/traces` does
   not capture the database. The smoke runs the container with
   `AGENT_DEBUGGER_DB_URL=sqlite+aiosqlite:////app/data/install-smoke.db` and mounts
   the volume at `/app/data`; consider aligning the default with `/app/traces`.
5. **Container runs as `appuser` (uid 100); bind-mounted host dirs are not writable
   by it** (host-created dirs are owned by the invoking uid). The smoke runs the
   container with `--user "$(id -u):$(id -g)"` so the explicit DB URL on the mounted
   volume is writable.
6. **Install-order note (not a bug).** `peaky-peek` and `peaky-peek-server` both ship
   the `peaky-peek` console script and the `agent_debugger_sdk` package; installing
   the server wheel last gives its `api.cli` server entry point control of the
   script (the smoke relies on this and documents it).
7. **SDK wheel's `peaky-peek seed` subcommand cannot work from a wheel** (observed by
   inspection): `agent_debugger_sdk/cli.py` resolves
   `scripts/seed_demo_sessions.py` relative to the package parent, and `scripts/`
   is not packaged. Masked in practice whenever the server wheel is installed
   alongside (its script wins, finding 6).
8. **`alembic.ini` also absent from the Docker image** — tolerated since finding 1's
   guard (migrations run from the packaged `storage/migrations` with the URL
   overridden), recorded for completeness.

## Q13 remainder — Redis buffer (real service) CI job

`redis-server` is not installed on this machine, so the real-service tests cannot run
locally. Added a dedicated job to `.github/workflows/ci.yml`:

- `redis-buffer` / "Redis buffer (real service)", `runs-on: ubuntu-latest`.
- `services: redis: image redis:7-alpine`, port `6379:6379`, redis-cli ping health
  options; `REDIS_URL=redis://localhost:6379` exported for the run.
- Also runs `sudo apt-get install -y redis-server`: `tests/test_buffer_redis_service.py`
  skips unless a `redis-server` **binary** is on PATH — it spawns its own ephemeral
  servers, which a service container alone cannot satisfy.
- Installs the repo (`pip install -e .`) plus the minimal mirror of the test job's
  list (fastapi, uvicorn[standard], sqlalchemy[asyncio], aiosqlite, alembic,
  aiofiles, bcrypt, httpx, pytest, pytest-asyncio, pytest-timeout) and `redis`.
- Runs `python3 -m pytest -v -ra -o addopts='' tests/test_buffer_redis.py
  tests/test_buffer_redis_service.py`.
- Other jobs untouched; YAML parses (`yaml.safe_load`); job structure reviewed
  against the existing conventions (checkout@v7, setup-python@v7, pip upgrade).

Local verification of what could run: in an isolated venv with the same install list,
`tests/test_buffer_redis.py` → **12 passed**; `tests/test_buffer_redis_service.py`
→ **1 module-level skip** ("redis-server binary not available on PATH"), which the
job's apt step removes. On the bare repo venv (no `redis` pip package) both files
skip at collection — exactly the gap the job closes.

## Local suite note

`tests/test_api_main_unit.py` currently shows 11 failures / 11 passes in the repo
venv — identical with and without this change's `storage/migrations/env.py` edit
(verified via stash), caused by a concurrently-added `tests/__init__.py` breaking the
lazy `from conftest import ...` imports there. Files owned by other agents; not
addressed here.

## Rerun

```bash
scripts/install_smoke.sh                 # full run incl. container slice
SMOKE_SKIP_DOCKER=1 scripts/install_smoke.sh   # wheels + venv + restart check only
SMOKE_KEEP_TMP=1 scripts/install_smoke.sh      # keep temp workspace on success
```

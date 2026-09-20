#!/usr/bin/env bash
# Install smoke for Peaky Peek (roadmap W11 / Q12 first slice).
#
# "Clean wheel launch -> trace -> query -> restart -> same trace, with an
# explicit data directory and no source-tree dependency."
#
# What this script does, mirroring .github/workflows/publish.yml faithfully
# (in TEMP COPIES of the repo — the checkout's pyproject.toml is never
# touched):
#
#   1. Build the SDK wheel (peaky-peek) the way the publish-sdk job does.
#   2. Build the server wheel (peaky-peek-server) the way the publish-server
#      job does: temp copy of the repo, `cp pyproject-server.toml
#      pyproject.toml`, frontend `npm ci && npm run build`, version pinned
#      through the same substitution snippet, then `python -m build`.
#   3. Install both wheels + runtime deps into a FRESH venv located outside
#      the repo checkout, and verify imports resolve from site-packages only
#      (cwd outside the checkout, PYTHONPATH unset).
#   4. Start the server via the installed `peaky-peek` console script on an
#      ephemeral port with an EXPLICIT data directory
#      (AGENT_DEBUGGER_DB_URL=sqlite+aiosqlite:///<datadir>/install-smoke.db).
#   5. Trace with the installed SDK — init(endpoint=...) with NO API key
#      (local unauthenticated loopback delivery) — send 3 events + a
#      checkpoint, query them back over HTTP (sessions list -> trace bundle
#      -> checkpoints).
#   6. STOP the server, RESTART it against the same data directory, and
#      verify the same trace and checkpoint are still queryable.
#   7. Verify the bundled UI (frontend/dist force-included in the server
#      wheel) is served by the installed server.
#   8. Audit the wheels for expected contents (records anything missing,
#      e.g. alembic.ini, as findings on stdout).
#   9. If a Docker daemon is reachable, build the repo image and verify
#      trace/restart persistence inside a container with a mounted volume.
#      (Set SMOKE_SKIP_DOCKER=1 to skip.)
#
# Usage: scripts/install_smoke.sh
# Env:   SMOKE_SKIP_DOCKER=1   skip the container slice
#        SMOKE_KEEP_TMP=1      keep the temp workspace on success too
#
# The script exits nonzero on any failure. Temp workspace is kept on failure
# (path printed to stderr) for post-mortem, removed on success.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_BASE="${TMPDIR:-/tmp}"
SMOKE_ID="peaky-smoke-$(date +%Y%m%d-%H%M%S)-$$"
TMP="$(mktemp -d "$TMP_BASE/${SMOKE_ID}.XXXXXX")"

SERVER_PID=""
SKIP_DOCKER="${SMOKE_SKIP_DOCKER:-0}"
KEEP_TMP="${SMOKE_KEEP_TMP:-0}"

log() { printf '\n==> %s\n' "$*"; }
step() { printf -- '--> %s\n' "$*"; }

cleanup() {
  local rc=$?
  set +e
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
  if [[ $rc -ne 0 ]]; then
    echo "SMOKE FAILED (rc=$rc); workspace kept at: $TMP" >&2
    for f in "$TMP"/server*.log; do
      if [[ -f "$f" ]]; then
        echo "--- $f (tail) ---" >&2
        tail -n 40 "$f" >&2
      fi
    done
  else
    if [[ "$KEEP_TMP" == "1" ]]; then
      echo "workspace kept at: $TMP"
    else
      rm -rf "$TMP"
    fi
  fi
  exit "$rc"
}
trap cleanup EXIT INT TERM

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

# ---------------------------------------------------------------------------
# 0. Preflight
# ---------------------------------------------------------------------------
log "Step 0: preflight"
step "repo: $REPO_ROOT"
step "workspace: $TMP"
command -v python3 >/dev/null || fail "python3 not found"
command -v npm >/dev/null || fail "npm not found (server wheel needs the frontend build)"
python3 --version
node --version
npm --version

copy_source_tree() { # $1 = destination (fresh checkout stand-in)
  mkdir -p "$1"
  tar -C "$REPO_ROOT" -cf - \
    --exclude=.git \
    --exclude=.venv \
    --exclude=.venv-ci \
    --exclude=frontend/node_modules \
    --exclude=dist \
    --exclude=build \
    --exclude=traces \
    --exclude=data \
    --exclude=test-results \
    --exclude=coverage.xml \
    --exclude=__pycache__ \
    . | tar -C "$1" -xf -
}

# The exact version-substitution publish.yml runs ("Set ... version from
# tag"); here RELEASE_VERSION is the current committed version, so the same
# code path executes without a tag.
set_version_like_publish() {
  python3 - <<'PY'
import os
import re
from pathlib import Path

version = os.environ["RELEASE_VERSION"]
path = Path("pyproject.toml")
content = path.read_text(encoding="utf-8")
updated, count = re.subn(
    r'(?m)^version = "[^"]+"$',
    f'version = "{version}"',
    content,
    count=1,
)
if count != 1:
    raise SystemExit("failed to update version in pyproject.toml")
path.write_text(updated, encoding="utf-8")
PY
}

show_build_metadata() { # same "Show ... build metadata" step as publish.yml
  python3 - <<'PY'
import tomllib
with open("pyproject.toml", "rb") as f:
    data = tomllib.load(f)
print(data["project"]["name"], data["project"]["version"])
PY
}

# ---------------------------------------------------------------------------
# 1. Build tools
# ---------------------------------------------------------------------------
log "Step 1: build tools (pip install build, like publish.yml)"
python3 -m venv "$TMP/build-venv"
"$TMP/build-venv/bin/pip" install -q --upgrade pip build

# ---------------------------------------------------------------------------
# 2. SDK wheel — mirrors the publish-sdk job
# ---------------------------------------------------------------------------
log "Step 2: build peaky-peek (SDK) wheel in a temp copy (mirrors publish.yml publish-sdk)"
copy_source_tree "$TMP/src-sdk"
(
  cd "$TMP/src-sdk"
  RELEASE_VERSION="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
  export RELEASE_VERSION
  set_version_like_publish
  step "SDK build metadata:"
  show_build_metadata
  "$TMP/build-venv/bin/python" -m build --outdir "$TMP/wheels"
)
SDK_WHEEL="$(ls "$TMP"/wheels/peaky_peek-*.whl | head -n 1)"
[[ -n "$SDK_WHEEL" ]] || fail "SDK wheel not produced"
step "SDK wheel: $SDK_WHEEL"

# ---------------------------------------------------------------------------
# 3. Server wheel — mirrors the publish-server job
#    (frontend build first, pyproject-server.toml swapped in as pyproject.toml)
# ---------------------------------------------------------------------------
log "Step 3: build peaky-peek-server wheel in a temp copy (mirrors publish.yml publish-server)"
copy_source_tree "$TMP/src-server"
(
  set -e
  cd "$TMP/src-server"
  step "swap in server pyproject for build: cp pyproject-server.toml pyproject.toml"
  cp pyproject-server.toml pyproject.toml
  step "build frontend bundle: npm ci && npm run build"
  (cd frontend && npm ci && npm run build)
  RELEASE_VERSION="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
  export RELEASE_VERSION
  set_version_like_publish
  step "server build metadata:"
  show_build_metadata
  "$TMP/build-venv/bin/python" -m build --outdir "$TMP/wheels"
)
SERVER_WHEEL="$(ls "$TMP"/wheels/peaky_peek_server-*.whl | head -n 1)"
[[ -n "$SERVER_WHEEL" ]] || fail "server wheel not produced"
step "server wheel: $SERVER_WHEEL"

# ---------------------------------------------------------------------------
# 4. Wheel content audit (records missing files as findings)
# ---------------------------------------------------------------------------
log "Step 4: wheel content audit"
"$TMP/build-venv/bin/python" - "$SDK_WHEEL" "$SERVER_WHEEL" <<'PY'
import sys
import zipfile

sdk_whl, server_whl = sys.argv[1], sys.argv[2]

def audit(path, required, label):
    names = set(zipfile.ZipFile(path).namelist())
    print(f"{label}: {len(names)} entries")
    missing = []
    for item in required:
        mark = "OK     " if item in names else "MISSING"
        print(f"  {mark} {item}")
        if item not in names:
            missing.append(item)
    return names, missing

sdk_names, sdk_missing = audit(
    sdk_whl,
    [
        "agent_debugger_sdk/__init__.py",
        "agent_debugger_sdk/transport.py",
        "agent_debugger_sdk/core/context/trace_context.py",
    ],
    "SDK wheel",
)

server_names, server_missing = audit(
    server_whl,
    [
        "api/main.py",
        "api/cli.py",
        "auth/__init__.py",
        "collector/server.py",
        "redaction/pipeline.py",
        "storage/engine.py",
        "storage/migrations/env.py",
        "agent_debugger_sdk/__init__.py",
        "frontend/dist/index.html",
    ],
    "server wheel",
)

# Advisory findings: recorded, not fatal (server still boots without these —
# storage/engine.py overrides script_location and sqlalchemy.url at runtime).
for wheel, names, label in ((sdk_whl, sdk_names, "SDK"), (server_whl, server_names, "server")):
    has = "alembic.ini" in names
    mark = "OK     " if has else "MISSING"
    note = "" if has else " (advisory: engine.py sets script_location/sqlalchemy.url explicitly)"
    print(f"  {mark} alembic.ini in {label} wheel{note}")

if not any(n.startswith("storage/migrations/versions/") for n in server_names):
    print("  MISSING storage/migrations/versions/* in server wheel (advisory)")
if not any(n.startswith("frontend/dist/assets/") for n in server_names):
    server_missing.append("frontend/dist/assets/*")

if sdk_missing or server_missing:
    sys.exit(f"wheel audit failed: missing {sdk_missing + server_missing}")
PY
step "wheel audit passed"

# ---------------------------------------------------------------------------
# 5. Fresh venv OUTSIDE the checkout + install wheels + runtime deps
# ---------------------------------------------------------------------------
log "Step 5: fresh venv + install wheels (runtime deps mirror ci.yml's install list)"
python3 -m venv "$TMP/venv"
VPIP="$TMP/venv/bin/pip"
"$VPIP" install -q --upgrade pip
# SDK wheel first, server second: both ship a `peaky-peek` console script and
# the agent_debugger_sdk package; the server install must win the script.
"$VPIP" install -q "$SDK_WHEEL"
"$VPIP" install -q \
  fastapi \
  "uvicorn[standard]" \
  "sqlalchemy[asyncio]" \
  aiosqlite \
  alembic \
  aiofiles \
  bcrypt \
  httpx
"$VPIP" install -q "$SERVER_WHEEL"
step "installed:"
"$TMP/venv/bin/pip" list 2>/dev/null | grep -Ei 'peaky|fastapi|uvicorn|sqlalchemy|aiosqlite|alembic|aiofiles|bcrypt|httpx' || true

# No source-tree dependency: run from OUTSIDE the checkout with PYTHONPATH
# unset and assert everything imports from the venv's site-packages.
mkdir -p "$TMP/run"
(
  cd "$TMP/run"
  env -u PYTHONPATH "$TMP/venv/bin/python" - <<'PY'
import agent_debugger_sdk
import api
import storage

for mod in (agent_debugger_sdk, api, storage):
    path = mod.__file__
    assert "site-packages" in path, f"{mod.__name__} imported from outside site-packages: {path}"
    print(f"  {mod.__name__:22s} -> {path}")
PY
) || fail "packages did not import from site-packages (source-tree dependency?)"
step "imports resolve from site-packages only"

# ---------------------------------------------------------------------------
# 6. Server start #1 — explicit data directory, ephemeral port
# ---------------------------------------------------------------------------
log "Step 6: start installed server (console script) with an explicit data directory"
DATA_DIR="$TMP/data"
RUN_DIR="$TMP/run"
DB_URL="sqlite+aiosqlite:///$DATA_DIR/install-smoke.db"
mkdir -p "$DATA_DIR"

free_port() {
  env -u PYTHONPATH "$TMP/venv/bin/python" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'
}

start_server() { # $1 = port, $2 = logfile
  (
    cd "$RUN_DIR"
    exec env -u PYTHONPATH -u AGENT_DEBUGGER_URL -u AGENT_DEBUGGER_API_KEY \
      AGENT_DEBUGGER_DB_URL="$DB_URL" \
      "$TMP/venv/bin/peaky-peek" --host 127.0.0.1 --port "$1"
  ) >"$2" 2>&1 &
  SERVER_PID=$!
}

wait_healthy() { # $1 = port
  local i
  for i in $(seq 1 150); do
    if curl -sf "http://127.0.0.1:$1/api/health" >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      return 1
    fi
    sleep 0.3
  done
  return 1
}

stop_server() {
  [[ -n "$SERVER_PID" ]] || return 0
  kill "$SERVER_PID" 2>/dev/null || true
  local i
  for i in $(seq 1 50); do
    kill -0 "$SERVER_PID" 2>/dev/null || { wait "$SERVER_PID" 2>/dev/null || true; SERVER_PID=""; return 0; }
    sleep 0.2
  done
  kill -9 "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
  SERVER_PID=""
}

PORT1="$(free_port)"
step "port: $PORT1  db: $DB_URL"
start_server "$PORT1" "$TMP/server1.log"
wait_healthy "$PORT1" || fail "server did not become healthy (see $TMP/server1.log)"
step "server healthy on http://127.0.0.1:$PORT1 (pid $SERVER_PID)"

# ---------------------------------------------------------------------------
# 7. Trace with the installed SDK (no API key) and query back over HTTP
# ---------------------------------------------------------------------------
log "Step 7: traced session via installed SDK (no API key) -> query over HTTP"

cat >"$TMP/smoke_client.py" <<'PY'
"""Install-smoke client: installed SDK against the installed server.

Phases:
  record  - init(endpoint=...) WITHOUT an api key (local unauthenticated
            loopback delivery), trace 3 events + a checkpoint, then query the
            session back over HTTP (sessions list -> trace bundle).
  verify  - re-query the same session (used after a server restart) and
            compare event/checkpoint counts against the recorded run.

Env: SMOKE_BASE_URL, SMOKE_SESSION_FILE, SMOKE_COUNTS_FILE.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

from agent_debugger_sdk import config as cfg
from agent_debugger_sdk.core.context import TraceContext

BASE_URL = os.environ["SMOKE_BASE_URL"]
SESSION_FILE = Path(os.environ["SMOKE_SESSION_FILE"])
COUNTS_FILE = Path(os.environ["SMOKE_COUNTS_FILE"])
PHASE = sys.argv[1]


def fetch_bundle(session_id: str) -> dict:
    """Poll the trace bundle until the server returns it (delivery lag)."""
    last_error = None
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        for _ in range(50):
            try:
                response = client.get(f"/api/sessions/{session_id}/trace")
                if response.status_code == 200:
                    return response.json()
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            except httpx.HTTPError as exc:  # server restarting
                last_error = repr(exc)
            time.sleep(0.3)
    raise SystemExit(f"trace bundle never became queryable: {last_error}")


def query_and_report(session_id: str) -> dict:
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        listing = client.get("/api/sessions", params={"limit": 100}).json()
        checkpoints = client.get(f"/api/sessions/{session_id}/checkpoints").json()
    ids = [s["id"] for s in listing["sessions"]]
    assert session_id in ids, f"session {session_id} not in sessions list ({len(ids)} sessions)"
    bundle = fetch_bundle(session_id)
    events = bundle["events"]
    names = [e["name"] for e in events]
    n_checkpoints = len(bundle["checkpoints"])
    assert n_checkpoints >= 1, "no checkpoints in trace bundle"
    assert checkpoints["checkpoints"], "no checkpoints via checkpoint endpoint"
    return {"events": len(events), "checkpoints": n_checkpoints, "names": names}


async def record() -> None:
    session_id = f"install-smoke-{uuid.uuid4().hex[:8]}"
    # No api_key: endpoint-only init keeps the SDK in local mode and delivers
    # unauthenticated to the loopback collector.
    cfg.init(endpoint=BASE_URL)

    async with TraceContext(session_id=session_id, agent_name="install_smoke_agent") as ctx:
        await ctx.record_decision(
            reasoning="smoke: pick a search strategy",
            confidence=0.9,
            chosen_action="search",
        )
        await ctx.record_tool_call("search", {"query": "peaky peek smoke"})
        await ctx.record_tool_result("search", {"hits": 3})
        await ctx.create_checkpoint(
            state={"step": 1, "items": ["a", "b", "c"]},
            memory={"turn": 1},
            importance=0.7,
        )

    SESSION_FILE.write_text(session_id, encoding="utf-8")
    counts = query_and_report(session_id)
    COUNTS_FILE.write_text(json.dumps(counts), encoding="utf-8")
    print(f"RECORD OK session={session_id} events={counts['events']} checkpoints={counts['checkpoints']}")
    assert counts["events"] >= 6, f"expected >=6 events, got {counts['events']}"


def verify() -> None:
    session_id = SESSION_FILE.read_text(encoding="utf-8").strip()
    recorded = json.loads(COUNTS_FILE.read_text(encoding="utf-8"))
    counts = query_and_report(session_id)
    assert counts["events"] == recorded["events"], (
        f"event count changed across restart: {recorded['events']} -> {counts['events']}"
    )
    assert counts["checkpoints"] == recorded["checkpoints"], (
        f"checkpoint count changed across restart: {recorded['checkpoints']} -> {counts['checkpoints']}"
    )
    print(
        f"VERIFY OK session={session_id} events={counts['events']} "
        f"checkpoints={counts['checkpoints']} (same as before restart)"
    )


if PHASE == "record":
    asyncio.run(record())
elif PHASE == "verify":
    verify()
else:
    raise SystemExit(f"unknown phase: {PHASE}")
PY

SMOKE_BASE_URL="http://127.0.0.1:$PORT1" \
SMOKE_SESSION_FILE="$TMP/session-id.txt" \
SMOKE_COUNTS_FILE="$TMP/counts.json" \
  env -u PYTHONPATH "$TMP/venv/bin/python" "$TMP/smoke_client.py" record \
  || fail "SDK trace/query phase failed"

[[ -f "$DATA_DIR/install-smoke.db" ]] || fail "database file not created in the explicit data dir"

# ---------------------------------------------------------------------------
# 8. Bundled UI served by the installed server
# ---------------------------------------------------------------------------
log "Step 8: bundled UI (frontend/dist from the server wheel)"
UI_CODE="$(curl -s -o "$TMP/ui-index.html" -w '%{http_code}' "http://127.0.0.1:$PORT1/ui/")"
[[ "$UI_CODE" == "200" ]] || fail "GET /ui/ returned $UI_CODE (expected 200)"
grep -qi "<!doctype html" "$TMP/ui-index.html" || fail "GET /ui/ did not return HTML"
step "GET /ui/ -> 200 HTML ($(wc -c <"$TMP/ui-index.html") bytes)"

# ---------------------------------------------------------------------------
# 9. STOP, then RESTART against the same data directory
# ---------------------------------------------------------------------------
log "Step 9: restart server against the SAME data directory and verify persistence"
stop_server
step "server stopped"
PORT2="$(free_port)"
start_server "$PORT2" "$TMP/server2.log"
wait_healthy "$PORT2" || fail "server did not come back after restart (see $TMP/server2.log)"
step "server restarted on http://127.0.0.1:$PORT2"

SMOKE_BASE_URL="http://127.0.0.1:$PORT2" \
SMOKE_SESSION_FILE="$TMP/session-id.txt" \
SMOKE_COUNTS_FILE="$TMP/counts.json" \
  env -u PYTHONPATH "$TMP/venv/bin/python" "$TMP/smoke_client.py" verify \
  || fail "post-restart persistence check failed"

stop_server

# ---------------------------------------------------------------------------
# 10. Container slice (only when a Docker daemon is reachable)
# ---------------------------------------------------------------------------
if [[ "$SKIP_DOCKER" == "1" ]]; then
  log "Step 10: docker slice skipped (SMOKE_SKIP_DOCKER=1)"
elif ! docker info >/dev/null 2>&1; then
  log "Step 10: docker daemon not reachable - skipping container slice"
else
  log "Step 10: container slice (docker build + volume-mounted persistence)"
  docker build -t peaky-peek-smoke "$TMP/src-server" || fail "docker build failed"

  CPORT="$(free_port)"
  CNAME="$SMOKE_ID"
  CGATEWAY_DATA="$TMP/container-data"
  mkdir -p "$CGATEWAY_DATA"
  # The image's default DB is ./data/agent_debugger.db under /app; point it at
  # the mounted volume so restart persistence can be observed from the host.
  # Run as the invoking host uid: the image's appuser cannot write a
  # bind-mounted volume created by the host user, and the explicit DB URL
  # below must live on that volume for the restart check.
  docker run -d --name "$CNAME" \
    --user "$(id -u):$(id -g)" \
    -p "127.0.0.1:$CPORT:8000" \
    -e AGENT_DEBUGGER_DB_URL="sqlite+aiosqlite:////app/data/install-smoke.db" \
    -v "$CGATEWAY_DATA:/app/data" \
    peaky-peek-smoke >/dev/null || fail "docker run failed"

  c_wait_healthy() {
    local i
    for i in $(seq 1 150); do
      if curl -sf "http://127.0.0.1:$1/api/health" >/dev/null 2>&1; then
        return 0
      fi
      if [[ "$(docker inspect -f '{{.State.Running}}' "$CNAME" 2>/dev/null)" != "true" ]]; then
        return 1
      fi
      sleep 0.3
    done
    return 1
  }

  c_wait_healthy "$CPORT" || {
    docker logs "$CNAME" >&2 || true
    fail "container did not become healthy"
  }
  step "container healthy on http://127.0.0.1:$CPORT"

  # The server only accepts loopback clients in local mode, so the smoke
  # client runs INSIDE the container (python:3.12-slim + installed package).
  docker cp "$TMP/smoke_client.py" "$CNAME:/app/smoke_client.py"
  docker exec \
    -e SMOKE_BASE_URL="http://127.0.0.1:8000" \
    -e SMOKE_SESSION_FILE=/tmp/session-id.txt \
    -e SMOKE_COUNTS_FILE=/tmp/counts.json \
    -e PYTHONPATH= \
    "$CNAME" python /app/smoke_client.py record \
    || fail "container trace/query phase failed"

  step "restarting container against the same mounted volume"
  docker restart "$CNAME" >/dev/null
  c_wait_healthy "$CPORT" || fail "container did not come back after restart"
  docker exec \
    -e SMOKE_BASE_URL="http://127.0.0.1:8000" \
    -e SMOKE_SESSION_FILE=/tmp/session-id.txt \
    -e SMOKE_COUNTS_FILE=/tmp/counts.json \
    -e PYTHONPATH= \
    "$CNAME" python /app/smoke_client.py verify \
    || fail "container post-restart persistence check failed"

  UI_CODE_C="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$CPORT/ui/")"
  [[ "$UI_CODE_C" == "200" ]] || fail "container GET /ui/ returned $UI_CODE_C"
  step "container UI: GET /ui/ -> 200"

  docker rm -f "$CNAME" >/dev/null
  step "container slice passed"
fi

log "INSTALL SMOKE PASSED"

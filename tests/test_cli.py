"""Tests for the peaky-peek CLI.

Covers two related but distinct CLI modules:

* ``api.cli``  -- server CLI (``peaky-peek-server`` entry point).
* ``agent_debugger_sdk.cli`` -- SDK CLI (``peaky-peek`` entry point) with the
  ``seed``/``serve``/``demo`` subcommands. This is the primary coverage target.
"""

import subprocess
import sys
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Existing tests for the api.cli module (server CLI) -- preserved.
# ---------------------------------------------------------------------------


def test_cli_module_importable():
    """CLI module should be importable."""
    from api.cli import main

    assert callable(main)


def test_cli_version_flag(capsys):
    """--version should print version string."""
    with patch.object(sys, "argv", ["peaky-peek", "--version"]):
        try:
            from api.cli import main

            main()
        except SystemExit as e:
            # --version exits with code 0
            assert e.code == 0

    captured = capsys.readouterr()
    assert "peaky-peek" in captured.out


# ---------------------------------------------------------------------------
# Tests for agent_debugger_sdk.cli (SDK CLI: seed / serve / demo).
# ---------------------------------------------------------------------------

from agent_debugger_sdk import cli as sdk_cli  # noqa: E402


def _make_fake_path(exists_return: bool):
    """Build a Path stand-in controlling ``exists()`` for ``run_seed``.

    Replicates the small slice of pathlib.Path that ``run_seed`` exercises:
    ``Path(__file__).parent.parent / "scripts" / "seed_demo_sessions.py"``.
    """

    class _FakePath:
        def __init__(self, *args, **kwargs):
            pass

        @property
        def parent(self):
            return self

        def __truediv__(self, _other):
            return self

        def __str__(self):
            return "/fake/scripts/seed_demo_sessions.py"

        def exists(self):
            return exists_return

    return _FakePath


class _FakePopen:
    """Minimal subprocess.Popen double recording terminate()/wait() calls."""

    instances: list["_FakePopen"] = []

    def __init__(self, args, cwd=None, env=None, stdout=None, stderr=None):
        self.args = args
        self.cwd = cwd
        self.env = env
        self.stdout = stdout
        self.stderr = stderr
        self.terminated = False
        self.wait_calls = 0
        type(self).instances.append(self)

    def wait(self):
        self.wait_calls += 1
        return 0

    def terminate(self):
        self.terminated = True


class _InterruptServerWaitPopen(_FakePopen):
    """Popen double modeling a single Ctrl+C interrupting the server wait.

    Only the first ``wait()`` on the uvicorn server process raises; subsequent
    waits (including the frontend's) return 0, mirroring realistic behaviour
    where terminate() lets the cleanup waits complete.
    """

    def wait(self):
        self.wait_calls += 1
        if self.wait_calls == 1 and "uvicorn" in self.args:
            raise KeyboardInterrupt
        return 0


# --- module surface --------------------------------------------------------


def test_sdk_cli_module_importable():
    """SDK CLI module exposes the expected callables."""
    assert callable(sdk_cli.main)
    assert callable(sdk_cli.run_seed)
    assert callable(sdk_cli.run_serve)
    assert callable(sdk_cli.run_demo)


# --- main() argument dispatch ---------------------------------------------


def test_sdk_main_seed_dispatches(monkeypatch):
    calls = []

    def fake_run_seed():
        calls.append("seed")
        return 0

    monkeypatch.setattr(sdk_cli, "run_seed", fake_run_seed)
    monkeypatch.setattr(sys, "argv", ["peaky-peek", "seed"])
    assert sdk_cli.main() == 0
    assert calls == ["seed"]


def test_sdk_main_serve_dispatches(monkeypatch):
    calls = []

    def fake_run_serve():
        calls.append("serve")
        return 0

    monkeypatch.setattr(sdk_cli, "run_serve", fake_run_serve)
    monkeypatch.setattr(sys, "argv", ["peaky-peek", "serve"])
    assert sdk_cli.main() == 0
    assert calls == ["serve"]


def test_sdk_main_demo_dispatches(monkeypatch):
    calls = []

    def fake_run_demo():
        calls.append("demo")
        return 0

    monkeypatch.setattr(sdk_cli, "run_demo", fake_run_demo)
    monkeypatch.setattr(sys, "argv", ["peaky-peek", "demo"])
    assert sdk_cli.main() == 0
    assert calls == ["demo"]


def test_sdk_main_no_args_prints_help_and_returns_zero(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["peaky-peek"])
    result = sdk_cli.main()
    captured = capsys.readouterr()
    assert result == 0
    assert "usage:" in captured.out.lower()
    assert "peaky-peek" in captured.out


def test_sdk_main_unknown_command_exits_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["peaky-peek", "nope"])
    with pytest.raises(SystemExit) as exc:
        sdk_cli.main()
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "invalid choice" in err


# --- run_seed() ------------------------------------------------------------


def test_run_seed_success(monkeypatch, capsys):
    captured = {}

    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(sdk_cli, "Path", _make_fake_path(exists_return=True))
    monkeypatch.setattr(sdk_cli.subprocess, "run", fake_run)

    assert sdk_cli.run_seed() == 0

    out = capsys.readouterr().out
    assert "Seeding demo sessions" in out
    assert captured["cmd"][0] == sys.executable
    assert captured["cmd"][1].endswith("seed_demo_sessions.py")


def test_run_seed_propagates_nonzero_returncode(monkeypatch):
    def fake_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(cmd, 3)

    monkeypatch.setattr(sdk_cli, "Path", _make_fake_path(exists_return=True))
    monkeypatch.setattr(sdk_cli.subprocess, "run", fake_run)

    assert sdk_cli.run_seed() == 3


def test_run_seed_missing_script_returns_one(monkeypatch, capsys):
    def boom(cmd, *args, **kwargs):
        raise AssertionError("subprocess.run must not be called when script is missing")

    monkeypatch.setattr(sdk_cli, "Path", _make_fake_path(exists_return=False))
    monkeypatch.setattr(sdk_cli.subprocess, "run", boom)

    assert sdk_cli.run_seed() == 1
    err = capsys.readouterr().err
    assert "seed script not found" in err


# --- run_serve() -----------------------------------------------------------


def test_run_serve_success(monkeypatch, capsys):
    captured = {}

    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        captured["check"] = kwargs.get("check")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(sdk_cli.subprocess, "run", fake_run)

    assert sdk_cli.run_serve() == 0

    out = capsys.readouterr().out
    assert "Starting server" in out
    assert "localhost:8000" in out
    assert captured["check"] is True
    assert "uvicorn" in captured["cmd"]
    assert "api.main:app" in captured["cmd"]


def test_run_serve_keyboard_interrupt_returns_zero(monkeypatch, capsys):
    def fake_run(cmd, *args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(sdk_cli.subprocess, "run", fake_run)

    assert sdk_cli.run_serve() == 0
    out = capsys.readouterr().out
    assert "Server stopped" in out


def test_run_serve_called_process_error_returns_one(monkeypatch, capsys):
    def fake_run(cmd, *args, **kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd)

    monkeypatch.setattr(sdk_cli.subprocess, "run", fake_run)

    assert sdk_cli.run_serve() == 1
    err = capsys.readouterr().err
    assert "Error starting server" in err


def test_run_serve_file_not_found_returns_one(monkeypatch, capsys):
    def fake_run(cmd, *args, **kwargs):
        raise FileNotFoundError("uvicorn")

    monkeypatch.setattr(sdk_cli.subprocess, "run", fake_run)

    assert sdk_cli.run_serve() == 1
    err = capsys.readouterr().err
    assert "uvicorn not found" in err


# --- run_demo() ------------------------------------------------------------


def test_run_demo_success(monkeypatch, capsys):
    _FakePopen.instances = []

    monkeypatch.setattr(sdk_cli, "run_seed", lambda: 0)
    monkeypatch.setattr(sdk_cli.subprocess, "Popen", _FakePopen)

    assert sdk_cli.run_demo() == 0

    out = capsys.readouterr().out
    assert "Peaky Peek demo is running!" in out
    assert "http://localhost:8000" in out
    assert "http://localhost:5173" in out

    # Two background processes spawned: server then frontend.
    assert len(_FakePopen.instances) == 2
    server_proc, frontend_proc = _FakePopen.instances
    assert "uvicorn" in server_proc.args
    assert "api.main:app" in server_proc.args
    assert frontend_proc.cwd is not None
    assert frontend_proc.env.get("API_PORT") == "8000"
    assert frontend_proc.args == ["npm", "run", "dev"]


def test_run_demo_seed_failure_short_circuits(monkeypatch):
    _FakePopen.instances = []

    def boom(*args, **kwargs):
        raise AssertionError("Popen must not be called when seeding fails")

    monkeypatch.setattr(sdk_cli, "run_seed", lambda: 7)
    monkeypatch.setattr(sdk_cli.subprocess, "Popen", boom)

    assert sdk_cli.run_demo() == 7
    assert _FakePopen.instances == []


def test_run_demo_server_popen_failure_returns_one(monkeypatch, capsys):
    def boom(*args, **kwargs):
        raise OSError("cannot spawn")

    monkeypatch.setattr(sdk_cli, "run_seed", lambda: 0)
    monkeypatch.setattr(sdk_cli.subprocess, "Popen", boom)

    assert sdk_cli.run_demo() == 1
    err = capsys.readouterr().err
    assert "Error starting server" in err


def test_run_demo_frontend_popen_failure_terminates_server(monkeypatch, capsys):
    _FakePopen.instances = []
    calls = {"n": 0}

    def popen_factory(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakePopen(*args, **kwargs)
        raise OSError("npm missing")

    monkeypatch.setattr(sdk_cli, "run_seed", lambda: 0)
    monkeypatch.setattr(sdk_cli.subprocess, "Popen", popen_factory)

    assert sdk_cli.run_demo() == 1
    err = capsys.readouterr().err
    assert "Error starting frontend" in err

    # The server process that did start must be terminated when frontend fails.
    assert len(_FakePopen.instances) == 1
    assert _FakePopen.instances[0].terminated is True


def test_run_demo_keyboard_interrupt_terminates_both(monkeypatch, capsys):
    _FakePopen.instances = []

    monkeypatch.setattr(sdk_cli, "run_seed", lambda: 0)
    monkeypatch.setattr(sdk_cli.subprocess, "Popen", _InterruptServerWaitPopen)

    assert sdk_cli.run_demo() == 0
    out = capsys.readouterr().out
    assert "Stopping server and frontend" in out

    assert len(_FakePopen.instances) == 2
    assert all(p.terminated for p in _FakePopen.instances)

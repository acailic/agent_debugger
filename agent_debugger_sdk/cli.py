#!/usr/bin/env python3
"""Peaky Peek CLI - zero-friction onboarding and demo commands."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run_seed() -> int:
    """Run the demo seed script."""
    script_path = Path(__file__).parent.parent / "scripts" / "seed_demo_sessions.py"
    if not script_path.exists():
        print(f"Error: seed script not found at {script_path}", file=sys.stderr)
        return 1

    print("Seeding demo sessions...")
    result = subprocess.run([sys.executable, str(script_path)])
    return result.returncode


def run_serve() -> int:
    """Start the development server."""
    print("Starting server on http://localhost:8000")
    print("Press Ctrl+C to stop")
    try:
        subprocess.run(
            [sys.executable, "-m", "uvicorn", "api.main:app", "--reload", "--port", "8000"],
            check=True,
        )
    except KeyboardInterrupt:
        print("\nServer stopped")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"Error starting server: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print("Error: uvicorn not found. Install with: pip install uvicorn", file=sys.stderr)
        return 1


def run_demo() -> int:
    """Seed demo data and start server + frontend."""
    # Step 1: Seed the data
    seed_result = run_seed()
    if seed_result != 0:
        return seed_result

    # Step 2: Start server in background
    print("\nStarting server in background...")
    try:
        server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api.main:app", "--reload", "--port", "8000"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, OSError) as e:
        print(f"Error starting server: {e}", file=sys.stderr)
        return 1

    # Step 3: Start frontend in background
    print("Starting frontend in background...")
    frontend_dir = Path(__file__).parent.parent / "frontend"
    try:
        frontend_process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(frontend_dir),
            env={**os.environ, "API_PORT": "8000"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, OSError) as e:
        print(f"Error starting frontend: {e}", file=sys.stderr)
        server_process.terminate()
        return 1

    # Step 4: Print instructions
    print("\n" + "=" * 60)
    print("  Peaky Peek demo is running!")
    print("=" * 60)
    print("\n  Server:    http://localhost:8000")
    print("  Frontend:  http://localhost:5173")
    print("\n  Press Ctrl+C to stop both processes")
    print("\n  Open http://localhost:5173 to explore demo sessions")
    print("=" * 60 + "\n")

    # Wait for interrupt
    try:
        server_process.wait()
        frontend_process.wait()
    except KeyboardInterrupt:
        print("\nStopping server and frontend...")
        server_process.terminate()
        frontend_process.terminate()
        server_process.wait()
        frontend_process.wait()
        print("Done")

    return 0


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="peaky-peek",
        description="Peaky Peek - AI agent debugger CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("demo", help="Seed demo data and launch server + frontend")
    subparsers.add_parser("seed", help="Seed benchmark demo sessions")
    subparsers.add_parser("serve", help="Start the development server")

    args = parser.parse_args()

    if args.command == "demo":
        return run_demo()
    elif args.command == "seed":
        return run_seed()
    elif args.command == "serve":
        return run_serve()
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())

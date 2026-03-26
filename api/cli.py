"""CLI entry point for peaky-peek-server.

This module provides the command-line interface for running the server.
"""

import argparse
import importlib.metadata
import webbrowser

import uvicorn


def main() -> None:
    """Main CLI entry point."""
    # Get version from package metadata (avoids hardcoding)
    try:
        version = importlib.metadata.version("peaky-peek-server")
    except importlib.metadata.PackageNotFoundError:
        version = "0.0.0-dev"

    parser = argparse.ArgumentParser(
        prog="peaky-peek",
        description="Debug AI agents with time-travel replay and decision trees",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind (default: 8000)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open browser after starting",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version}",
    )

    args = parser.parse_args()

    if args.open:
        webbrowser.open(f"http://{args.host}:{args.port}")

    uvicorn.run("api.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()

"""Tests for the peaky-peek CLI."""


def test_cli_module_importable():
    """CLI module should be importable."""
    from api.cli import main

    assert callable(main)


def test_cli_version_flag(capsys):
    """--version should print version string."""
    import sys
    from unittest.mock import patch

    with patch.object(sys, "argv", ["peaky-peek", "--version"]):
        try:
            from api.cli import main

            main()
        except SystemExit as e:
            # --version exits with code 0
            assert e.code == 0

    captured = capsys.readouterr()
    assert "peaky-peek" in captured.out
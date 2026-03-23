"""Tests for package metadata and imports."""

def test_package_importable():
    import agent_debugger_sdk
    assert hasattr(agent_debugger_sdk, "init")
    assert hasattr(agent_debugger_sdk, "TraceContext")
    assert hasattr(agent_debugger_sdk, "EventType")


def test_version_exists():
    import agent_debugger_sdk
    assert hasattr(agent_debugger_sdk, "__version__")
    assert agent_debugger_sdk.__version__ == "0.1.0"
"""Tests for package metadata and imports."""

from importlib.metadata import PackageNotFoundError, version

import pytest


def test_package_importable():
    import agent_debugger_sdk
    assert hasattr(agent_debugger_sdk, "init")
    assert hasattr(agent_debugger_sdk, "TraceContext")
    assert hasattr(agent_debugger_sdk, "EventType")


def test_version_exists():
    import agent_debugger_sdk
    assert hasattr(agent_debugger_sdk, "__version__")
    
    # When developing locally, the package may not be installed in site-packages
    # So we check that the version attribute exists and is valid
    assert isinstance(agent_debugger_sdk.__version__, str)
    assert len(agent_debugger_sdk.__version__) > 0
    
    # If the package is installed, verify it matches metadata
    try:
        installed_version = version("peaky-peek")
        assert agent_debugger_sdk.__version__ == installed_version
    except PackageNotFoundError:
        # Package not installed in development mode - this is OK
        # Just verify the hardcoded version is valid
        assert agent_debugger_sdk.__version__ == "0.1.4"


def test_version_format():
    """Test that version follows semantic versioning."""
    import re

    import agent_debugger_sdk
    
    # Semantic versioning pattern: major.minor.patch
    semver_pattern = r'^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$'
    assert re.match(semver_pattern, agent_debugger_sdk.__version__), \
        f"Version {agent_debugger_sdk.__version__} doesn't follow semver"


def test_all_exports_importable():
    """Test that all __all__ exports are actually importable."""
    import agent_debugger_sdk
    
    for export_name in agent_debugger_sdk.__all__:
        assert hasattr(agent_debugger_sdk, export_name), \
            f"Export '{export_name}' declared in __all__ but not found in module"


def test_no_circular_imports():
    """Test that the package can be imported without circular dependency issues.

    NOTE: This test deletes and re-imports all agent_debugger_sdk modules,
    which can cause issues with other tests that hold references to event classes.
    This test should be run in isolation or with pytest --forked if available.
    """
    pytest.skip("Run in isolation only: deletes sys.modules entries, breaks other tests")
    import sys

    # Remove from cache if present
    modules_to_remove = [
        key for key in sys.modules.keys()
        if key.startswith('agent_debugger_sdk')
    ]
    for module in modules_to_remove:
        del sys.modules[module]

    # Re-import should work without issues
    import agent_debugger_sdk
    assert agent_debugger_sdk is not None

    # Verify the EVENT_TYPE_REGISTRY is populated after re-import
    from agent_debugger_sdk.core.events import EVENT_TYPE_REGISTRY, EventType
    # Access the registry to ensure it's populated
    _ = EVENT_TYPE_REGISTRY.get(EventType.TOOL_CALL)
    assert len(EVENT_TYPE_REGISTRY) > 0, "EVENT_TYPE_REGISTRY should be populated after re-import"

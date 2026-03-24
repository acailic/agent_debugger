"""Tests for PatchConfig, BaseAdapter, and PatchRegistry."""
from __future__ import annotations

from agent_debugger_sdk.auto_patch.registry import BaseAdapter, PatchConfig, PatchRegistry


class _MockAdapter(BaseAdapter):
    """Concrete adapter for testing."""

    name = "mock"

    def __init__(self, available: bool = True) -> None:
        self._available = available
        self.patched = False
        self.unpatched = False

    def is_available(self) -> bool:
        return self._available

    def patch(self, config: PatchConfig) -> None:
        self.patched = True
        self.last_config = config

    def unpatch(self) -> None:
        self.unpatched = True


class _AnotherMockAdapter(BaseAdapter):
    """Second concrete adapter for testing name filtering."""

    name = "another"

    def __init__(self, available: bool = True) -> None:
        self._available = available
        self.patched = False
        self.unpatched = False

    def is_available(self) -> bool:
        return self._available

    def patch(self, config: PatchConfig) -> None:
        self.patched = True

    def unpatch(self) -> None:
        self.unpatched = True


class TestPatchConfigDefaults:
    def test_default_server_url(self) -> None:
        config = PatchConfig()
        assert config.server_url == "http://localhost:8000"

    def test_default_capture_content(self) -> None:
        config = PatchConfig()
        assert config.capture_content is False

    def test_custom_values(self) -> None:
        config = PatchConfig(server_url="http://example.com:9000", capture_content=True)
        assert config.server_url == "http://example.com:9000"
        assert config.capture_content is True


class TestPatchRegistryApply:
    def test_apply_calls_patch_on_available_adapter(self) -> None:
        registry = PatchRegistry()
        adapter = _MockAdapter(available=True)
        registry.register(adapter)
        config = PatchConfig()
        registry.apply(config)
        assert adapter.patched is True

    def test_apply_skips_unavailable_adapter(self) -> None:
        registry = PatchRegistry()
        adapter = _MockAdapter(available=False)
        registry.register(adapter)
        config = PatchConfig()
        registry.apply(config)
        assert adapter.patched is False

    def test_apply_with_names_filter_patches_only_named(self) -> None:
        registry = PatchRegistry()
        mock_adapter = _MockAdapter(available=True)
        another_adapter = _AnotherMockAdapter(available=True)
        registry.register(mock_adapter)
        registry.register(another_adapter)
        config = PatchConfig()
        registry.apply(config, names=["mock"])
        assert mock_adapter.patched is True
        assert another_adapter.patched is False

    def test_apply_with_names_filter_skips_unavailable_even_if_named(self) -> None:
        registry = PatchRegistry()
        adapter = _MockAdapter(available=False)
        registry.register(adapter)
        config = PatchConfig()
        registry.apply(config, names=["mock"])
        assert adapter.patched is False

    def test_apply_without_names_patches_all_available(self) -> None:
        registry = PatchRegistry()
        mock_adapter = _MockAdapter(available=True)
        another_adapter = _AnotherMockAdapter(available=True)
        registry.register(mock_adapter)
        registry.register(another_adapter)
        config = PatchConfig()
        registry.apply(config)
        assert mock_adapter.patched is True
        assert another_adapter.patched is True

    def test_apply_passes_config_to_patch(self) -> None:
        registry = PatchRegistry()
        adapter = _MockAdapter(available=True)
        registry.register(adapter)
        config = PatchConfig(server_url="http://custom:1234", capture_content=True)
        registry.apply(config)
        assert adapter.last_config is config

    def test_patched_names_reflects_applied_adapters(self) -> None:
        registry = PatchRegistry()
        mock_adapter = _MockAdapter(available=True)
        another_adapter = _AnotherMockAdapter(available=False)
        registry.register(mock_adapter)
        registry.register(another_adapter)
        config = PatchConfig()
        registry.apply(config)
        names = registry.patched_names()
        assert "mock" in names
        assert "another" not in names


class TestPatchRegistryUnapply:
    def test_unapply_calls_unpatch_on_patched_adapters(self) -> None:
        registry = PatchRegistry()
        adapter = _MockAdapter(available=True)
        registry.register(adapter)
        config = PatchConfig()
        registry.apply(config)
        registry.unapply()
        assert adapter.unpatched is True

    def test_unapply_does_not_call_unpatch_on_unpatched_adapters(self) -> None:
        registry = PatchRegistry()
        adapter = _MockAdapter(available=False)
        registry.register(adapter)
        config = PatchConfig()
        registry.apply(config)  # Won't patch because not available
        registry.unapply()
        assert adapter.unpatched is False

    def test_patched_names_empty_after_unapply(self) -> None:
        registry = PatchRegistry()
        adapter = _MockAdapter(available=True)
        registry.register(adapter)
        config = PatchConfig()
        registry.apply(config)
        assert "mock" in registry.patched_names()
        registry.unapply()
        assert registry.patched_names() == []


class TestPatchRegistryGetRegistry:
    def test_get_registry_returns_singleton(self) -> None:
        from agent_debugger_sdk.auto_patch.registry import get_registry

        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_get_registry_returns_patch_registry_instance(self) -> None:
        from agent_debugger_sdk.auto_patch.registry import get_registry

        registry = get_registry()
        assert isinstance(registry, PatchRegistry)

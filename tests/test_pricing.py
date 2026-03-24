"""Tests for the pricing module."""

def test_pricing_module_importable():
    """Pricing module should be importable."""
    from agent_debugger_sdk import pricing

    assert hasattr(pricing, "calculate_cost")
    assert hasattr(pricing, "get_pricing")
    assert hasattr(pricing, "PRICING_TABLE")


def test_get_pricing_known_model():
    """get_pricing should return pricing for known models."""
    from agent_debugger_sdk.pricing import get_pricing

    pricing = get_pricing("gpt-4o")
    assert pricing is not None
    assert pricing.input_cost > 0
    assert pricing.output_cost > 0


def test_get_pricing_unknown_model():
    """get_pricing should return None for unknown models."""
    from agent_debugger_sdk.pricing import get_pricing

    pricing = get_pricing("nonexistent-model-xyz")
    assert pricing is None


def test_get_pricing_resolves_aliases():
    """get_pricing should resolve model aliases."""
    from agent_debugger_sdk.pricing import MODEL_ALIASES, get_pricing

    # Test that aliases work
    for alias, canonical in MODEL_ALIASES.items():
        alias_pricing = get_pricing(alias)
        canonical_pricing = get_pricing(canonical)
        assert alias_pricing == canonical_pricing, f"Alias {alias} should resolve to {canonical}"


def test_calculate_cost_known_model():
    """calculate_cost should compute correct cost."""
    from agent_debugger_sdk.pricing import calculate_cost

    # gpt-4o: $2.50/1M input, $10.00/1M output
    # 1000 input + 500 output = (1000/1M * 2.50) + (500/1M * 10.00) = 0.0025 + 0.005 = 0.0075
    cost = calculate_cost("gpt-4o", input_tokens=1000, output_tokens=500)
    assert cost is not None
    assert abs(cost - 0.0075) < 0.0001


def test_calculate_cost_unknown_model():
    """calculate_cost should return None for unknown models."""
    from agent_debugger_sdk.pricing import calculate_cost

    cost = calculate_cost("nonexistent-model-xyz", input_tokens=1000, output_tokens=500)
    assert cost is None


def test_calculate_cost_zero_tokens():
    """calculate_cost should return 0.0 for zero tokens."""
    from agent_debugger_sdk.pricing import calculate_cost

    cost = calculate_cost("gpt-4o", input_tokens=0, output_tokens=0)
    assert cost == 0.0


def test_llm_response_event_auto_cost_calculation():
    """LLMResponseEvent should auto-calculate cost when tokens provided."""
    from agent_debugger_sdk.core.events import LLMResponseEvent

    # Create event with tokens but no explicit cost
    event = LLMResponseEvent(
        model="gpt-4o",
        usage={"input_tokens": 1000, "output_tokens": 500},
    )
    # Cost should be auto-calculated
    assert event.cost_usd > 0, "Cost should be auto-calculated"
    assert abs(event.cost_usd - 0.0075) < 0.0001


def test_llm_response_event_preserves_explicit_cost():
    """LLMResponseEvent should preserve explicitly set cost."""
    from agent_debugger_sdk.core.events import LLMResponseEvent
    # Create event with explicit cost
    event = LLMResponseEvent(
        model="gpt-4o",
        usage={"input_tokens": 1000, "output_tokens": 500},
        cost_usd=0.999,  # Explicit cost
    )
    # Explicit cost should be preserved
    assert event.cost_usd == 0.999


def test_llm_response_event_no_cost_for_unknown_model():
    """LLMResponseEvent should have 0.0 cost for unknown models."""
    from agent_debugger_sdk.core.events import LLMResponseEvent
    event = LLMResponseEvent(
        model="unknown-model-xyz",
        usage={"input_tokens": 1000, "output_tokens": 500},
    )
    # Cost should remain 0.0 for unknown model
    assert event.cost_usd == 0.0

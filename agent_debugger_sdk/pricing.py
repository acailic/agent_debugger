"""Model pricing data for cost estimation.

Prices are per 1M tokens in USD as of March 2026.
Update this file when model pricing changes.
"""

from dataclasses import dataclass

# Constant for token-to-cost conversion
TOKENS_PER_MILLION = 1_000_000


@dataclass(frozen=True)
class ModelPricing:
    """Pricing information for a model."""

    input_cost: float  # $ per 1M input tokens
    output_cost: float  # $ per 1M output tokens


# Pricing data - update periodically
# Last updated: 2026-03-23
PRICING_TABLE: dict[str, ModelPricing] = {
    # OpenAI
    "gpt-4o": ModelPricing(2.50, 10.00),
    "gpt-4o-mini": ModelPricing(0.15, 0.60),
    "gpt-4-turbo": ModelPricing(10.00, 30.00),
    "gpt-4": ModelPricing(30.00, 60.00),
    "gpt-3.5-turbo": ModelPricing(0.50, 1.50),
    # Anthropic
    "claude-opus-4-6": ModelPricing(15.00, 75.00),
    "claude-sonnet-4-6": ModelPricing(3.00, 15.00),
    "claude-haiku-4-5": ModelPricing(0.80, 4.00),
    "claude-3-5-sonnet": ModelPricing(3.00, 15.00),
    "claude-3-haiku": ModelPricing(0.25, 1.25),
    # Google
    "gemini-2.0-flash": ModelPricing(0.10, 0.40),
    "gemini-1.5-pro": ModelPricing(1.25, 5.00),
}

# Aliases for common shorthand
MODEL_ALIASES: dict[str, str] = {
    "gpt-4": "gpt-4-turbo",
    "claude-3-sonnet": "claude-3-5-sonnet",
}


def get_pricing(model: str) -> ModelPricing | None:
    """Get pricing for a model, resolving aliases.

    Args:
        model: Model identifier (e.g., "gpt-4o")

    Returns:
        ModelPricing if found, None otherwise
    """
    model = MODEL_ALIASES.get(model, model)
    return PRICING_TABLE.get(model)


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Calculate cost in USD for a request.

    Args:
        model: Model identifier (e.g., "gpt-4o")
        input_tokens: Number of input/prompt tokens
        output_tokens: Number of output/completion tokens

    Returns:
        Cost in USD, or None if model not in pricing table
    """
    pricing = get_pricing(model)
    if pricing is None:
        return None

    if input_tokens == 0 and output_tokens == 0:
        return 0.0

    input_cost = (input_tokens / TOKENS_PER_MILLION) * pricing.input_cost
    output_cost = (output_tokens / TOKENS_PER_MILLION) * pricing.output_cost
    return round(input_cost + output_cost, 6)
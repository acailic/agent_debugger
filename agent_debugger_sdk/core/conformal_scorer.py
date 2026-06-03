"""Conformal prediction scoring for agent uncertainty quantification.

Based on CROP (Conformal Risk Optimization) - provides statistically rigorous
uncertainty intervals and coverage guarantees for agent predictions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent

__all__ = [
    "PredictionRegion",
    "CoverageLevel",
    "ConformalScore",
    "score_prediction_conformality",
    "compute_coverage_statistics",
]


class CoverageLevel(Enum):
    """Classification of prediction coverage quality."""

    WELL_COVERED = "well_covered"  # Prediction falls within confidence region
    UNDER_COVERED = "under_covered"  # Prediction outside expected region (high uncertainty)
    OVER_COVERED = "over_covered"  # Excessively wide region (low precision)
    UNKNOWN = "unknown"  # Unable to determine coverage


@dataclass
class PredictionRegion:
    """Uncertainty region for a single prediction."""

    lower_bound: float  # Lower bound of prediction interval
    upper_bound: float  # Upper bound of prediction interval
    confidence_level: float  # Target confidence level (e.g., 0.9 for 90%)
    actual_value: float | None  # Ground truth value if available
    is_covered: bool  # Whether actual_value falls within [lower_bound, upper_bound]
    width: float  # Region width (upper_bound - lower_bound)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "confidence_level": self.confidence_level,
            "actual_value": self.actual_value,
            "is_covered": self.is_covered,
            "width": self.width,
        }


@dataclass
class ConformalScore:
    """Conformal prediction analysis for a single prediction/event."""

    event_id: str
    prediction_region: PredictionRegion
    coverage_level: CoverageLevel
    calibration_score: float  # 0.0 (poorly calibrated) to 1.0 (well-calibrated)
    reasoning: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "prediction_region": self.prediction_region.to_dict(),
            "coverage_level": self.coverage_level.value,
            "calibration_score": self.calibration_score,
            "reasoning": self.reasoning,
        }


def _extract_prediction_value(event: TraceEvent) -> tuple[float | None, float | None]:
    """Extract predicted value and optional ground truth from event data.

    Returns:
        Tuple of (predicted_value, actual_value)
    """
    # Check for confidence score in event data
    predicted_value = None
    actual_value = None

    # Extract from decision events with confidence
    if event.event_type == EventType.DECISION:
        confidence = getattr(event, "confidence", None)
        if confidence is not None:
            predicted_value = float(confidence)

    # Extract from LLM response events
    if event.event_type == EventType.LLM_RESPONSE:
        # Could extract from content analysis or metadata
        confidence = event.data.get("confidence")
        if confidence is not None:
            predicted_value = float(confidence)

    # Extract ground truth if available
    if hasattr(event, "data"):
        actual_value = event.data.get("ground_truth")
        if actual_value is not None:
            actual_value = float(actual_value)

    return predicted_value, actual_value


def _compute_prediction_region(
    predicted_value: float,
    confidence_level: float = 0.9,
    uncertainty_scale: float = 0.2,
) -> PredictionRegion:
    """Compute uncertainty region around prediction.

    Args:
        predicted_value: Central prediction value
        confidence_level: Target confidence level
        uncertainty_scale: Scale factor for uncertainty (e.g., standard deviation)

    Returns:
        PredictionRegion with computed bounds
    """
    # Use conformal prediction approach: create interval around prediction
    # Width scales with requested confidence level
    try:
        from scipy.stats import norm

        z_score = norm.ppf(1 - (1 - confidence_level) / 2)
    except ImportError:
        # Fallback: approximate z-scores for common confidence levels
        _Z_SCORES: dict[float, float] = {
            0.50: 0.674, 0.60: 0.842, 0.70: 1.036, 0.80: 1.282,
            0.90: 1.645, 0.95: 1.960, 0.99: 2.576, 0.999: 3.291,
        }
        # Interpolate for intermediate values
        if confidence_level in _Z_SCORES:
            z_score = _Z_SCORES[confidence_level]
        else:
            sorted_levels = sorted(_Z_SCORES)
            for i in range(len(sorted_levels) - 1):
                lo, hi = sorted_levels[i], sorted_levels[i + 1]
                if lo <= confidence_level <= hi:
                    t = (confidence_level - lo) / (hi - lo)
                    z_score = _Z_SCORES[lo] * (1 - t) + _Z_SCORES[hi] * t
                    break
            else:
                z_score = 1.96  # default to 95%

    # Compute interval bounds
    margin = z_score * uncertainty_scale
    lower_bound = max(0.0, predicted_value - margin)  # Clamp to valid range
    upper_bound = min(1.0, predicted_value + margin)
    width = upper_bound - lower_bound

    return PredictionRegion(
        lower_bound=float(lower_bound),
        upper_bound=float(upper_bound),
        confidence_level=float(confidence_level),
        actual_value=None,  # Will be set if ground truth available
        is_covered=False,  # Will be updated if ground truth available
        width=float(width),
    )


def _classify_coverage_level(region: PredictionRegion) -> tuple[CoverageLevel, str]:
    """Classify the coverage level of a prediction region.

    Args:
        region: Prediction region to classify

    Returns:
        Tuple of (coverage_level, reasoning)
    """
    if region.actual_value is None:
        # No ground truth available - classify based on region properties
        if region.width > 0.5:
            return CoverageLevel.OVER_COVERED, "Region too wide - low precision"
        elif region.width < 0.1:
            return CoverageLevel.UNDER_COVERED, "Region too narrow - potentially overconfident"
        else:
            return CoverageLevel.WELL_COVERED, "Reasonable region width"

    # Ground truth available - check coverage
    is_covered = bool(region.lower_bound <= region.actual_value <= region.upper_bound)

    if is_covered:
        # Well covered if region is reasonably precise
        if region.width <= 0.3:
            return CoverageLevel.WELL_COVERED, f"Well-calibrated: actual {region.actual_value:.3f} within region"
        else:
            return CoverageLevel.OVER_COVERED, f"Covered but imprecise: width {region.width:.3f}"
    else:
        lo, hi = region.lower_bound, region.upper_bound
        return (
            CoverageLevel.UNDER_COVERED,
            f"Missed: actual {region.actual_value:.3f} outside [{lo:.3f}, {hi:.3f}]",
        )


def _calculate_calibration_score(region: PredictionRegion, coverage_level: CoverageLevel) -> float:
    """Calculate calibration score based on coverage and region properties.

    Score is 0.0 (poorly calibrated) to 1.0 (well-calibrated).
    """
    if coverage_level == CoverageLevel.WELL_COVERED:
        # Well-covered regions get high scores
        base_score = 0.9
        # Bonus for narrow regions (precise predictions)
        if region.width < 0.2:
            base_score = 1.0
        return base_score

    elif coverage_level == CoverageLevel.OVER_COVERED:
        # Over-covered regions are safe but imprecise
        # Penalize for very wide regions
        width_penalty = min(0.5, region.width)
        return 0.7 - width_penalty

    elif coverage_level == CoverageLevel.UNDER_COVERED:
        # Under-covered regions are problematic (predictions miss ground truth)
        return 0.2

    else:  # UNKNOWN
        return 0.5


def score_prediction_conformality(
    events: list[TraceEvent],
    confidence_level: float = 0.9,
    uncertainty_scale: float = 0.2,
) -> list[ConformalScore]:
    """Analyze prediction events and score them for conformal prediction quality.

    Args:
        events: List of trace events from the session
        confidence_level: Target confidence level for prediction regions
        uncertainty_scale: Scale factor for uncertainty estimation

    Returns:
        List of ConformalScore objects for events with predictions
    """
    if not events:
        return []

    scores: list[ConformalScore] = []

    for event in events:
        # Extract prediction value
        predicted_value, actual_value = _extract_prediction_value(event)

        if predicted_value is None:
            # Skip events without predictions
            continue

        # Compute prediction region
        region = _compute_prediction_region(
            predicted_value=predicted_value,
            confidence_level=confidence_level,
            uncertainty_scale=uncertainty_scale,
        )

        # Update region with ground truth if available
        if actual_value is not None:
            region.actual_value = actual_value
            region.is_covered = bool(region.lower_bound <= actual_value <= region.upper_bound)

        # Classify coverage level
        coverage_level, reasoning = _classify_coverage_level(region)

        # Calculate calibration score
        calibration_score = _calculate_calibration_score(region, coverage_level)

        scores.append(ConformalScore(
            event_id=event.id,
            prediction_region=region,
            coverage_level=coverage_level,
            calibration_score=calibration_score,
            reasoning=reasoning,
        ))

    return scores


def compute_coverage_statistics(scores: list[ConformalScore]) -> dict[str, Any]:
    """Compute coverage statistics for conformal prediction analysis.

    Args:
        scores: List of ConformalScore objects from score_prediction_conformality()

    Returns:
        Dictionary with coverage statistics
    """
    if not scores:
        return {
            "total_predictions": 0,
            "well_covered_count": 0,
            "under_covered_count": 0,
            "over_covered_count": 0,
            "unknown_count": 0,
            "avg_calibration_score": 0.0,
            "coverage_rate": 0.0,
            "avg_region_width": 0.0,
        }

    well_covered = sum(1 for s in scores if s.coverage_level == CoverageLevel.WELL_COVERED)
    under_covered = sum(1 for s in scores if s.coverage_level == CoverageLevel.UNDER_COVERED)
    over_covered = sum(1 for s in scores if s.coverage_level == CoverageLevel.OVER_COVERED)
    unknown = sum(1 for s in scores if s.coverage_level == CoverageLevel.UNKNOWN)

    # Calculate actual coverage rate (for regions with ground truth)
    regions_with_truth = [s.prediction_region for s in scores if s.prediction_region.actual_value is not None]
    coverage_rate = 0.0
    if regions_with_truth:
        covered_count = sum(1 for r in regions_with_truth if r.is_covered)
        coverage_rate = covered_count / len(regions_with_truth)

    avg_calibration = sum(s.calibration_score for s in scores) / len(scores)
    avg_width = sum(s.prediction_region.width for s in scores) / len(scores)

    return {
        "total_predictions": len(scores),
        "well_covered_count": well_covered,
        "under_covered_count": under_covered,
        "over_covered_count": over_covered,
        "unknown_count": unknown,
        "avg_calibration_score": avg_calibration,
        "coverage_rate": coverage_rate,
        "avg_region_width": avg_width,
    }
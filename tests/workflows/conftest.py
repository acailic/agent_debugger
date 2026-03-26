"""Fixtures for workflow-based tests."""

import pytest

from tests.fixtures.workflow_helpers import load_cassette


@pytest.fixture
def cassettes_dir():
    """Path to the cassettes directory."""
    from tests.fixtures.workflow_helpers import CASSETTES_DIR

    return CASSETTES_DIR


@pytest.fixture
def load_root_cause_cassettes():
    """Load root cause hunting cassettes."""
    happy = load_cassette("root_cause/tool_failure_to_decision.yaml")
    failure = load_cassette("root_cause/hallucinated_evidence.yaml")
    return {"happy": happy, "failure": failure}


@pytest.fixture
def load_safety_cassettes():
    """Load safety auditing cassettes."""
    happy = load_cassette("safety/enumerate_safety_events.yaml")
    failure = load_cassette("safety/missed_policy_violation.yaml")
    return {"happy": happy, "failure": failure}


@pytest.fixture
def load_reproducibility_cassettes():
    """Load reproducibility cassettes."""
    happy = load_cassette("reproducibility/checkpoint_replay.yaml")
    failure = load_cassette("reproducibility/session_diff_divergence.yaml")
    return {"happy": happy, "failure": failure}

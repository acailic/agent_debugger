import pytest


@pytest.fixture(autouse=True)
def setup_test_db():
    """No-op override: auto_patch tests do not need a database."""
    yield

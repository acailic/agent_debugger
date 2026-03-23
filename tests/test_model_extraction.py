from storage.models import Base, SessionModel, EventModel, CheckpointModel


def test_models_importable_from_new_location():
    """Models should be importable from storage.models."""
    assert SessionModel.__tablename__ == "sessions"
    assert EventModel.__tablename__ == "events"
    assert CheckpointModel.__tablename__ == "checkpoints"
    assert hasattr(Base, "metadata")


def test_repository_still_works_with_extracted_models():
    """TraceRepository should still import and function."""
    from storage.repository import TraceRepository
    assert callable(TraceRepository)
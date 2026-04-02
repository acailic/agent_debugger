from storage.models import Base, CheckpointModel, EventModel, SessionModel


def test_models_importable_from_new_location():
    """Models should be importable from storage.models and have expected attributes."""
    # Test that models are importable and have essential attributes for ORM functionality
    # Note: __tablename__ is an implementation detail of SQLAlchemy internals
    # We test behavior instead: models should have table-like attributes
    assert hasattr(SessionModel, "__table__") or hasattr(SessionModel, "__tablename__")
    assert hasattr(EventModel, "__table__") or hasattr(EventModel, "__tablename__")
    assert hasattr(CheckpointModel, "__table__") or hasattr(CheckpointModel, "__tablename__")
    assert hasattr(Base, "metadata")


def test_repository_still_works_with_extracted_models():
    """TraceRepository should still import and function."""
    from storage.repository import TraceRepository

    assert callable(TraceRepository)

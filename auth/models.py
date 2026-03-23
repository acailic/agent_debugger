"""Auth-related ORM models."""
from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import DateTime, String, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from storage.models import Base


class TenantModel(Base):
    """ORM model for tenant/accounts."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    plan: Mapped[str] = mapped_column(String(32), default="free")  # free, developer, team, business
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=lambda: datetime.datetime.now(datetime.UTC)
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class APIKeyModel(Base):
    """ORM model for API keys."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    key_prefix: Mapped[str] = mapped_column(String(16))  # ad_live_ or ad_test_
    environment: Mapped[str] = mapped_column(String(8))  # live, test
    name: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=lambda: datetime.datetime.now(datetime.UTC)
    )
    last_used_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

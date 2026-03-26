"""Alert persistence for derived anomaly alerts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from storage import TraceRepository


@dataclass
class DerivedAlert:
    """Alert derived from live monitoring analysis."""

    alert_type: str
    severity: float  # 0.0-1.0
    signal: str
    event_ids: list[str] = field(default_factory=list)
    source: str = "derived"  # "captured" or "derived"
    detection_config: dict[str, Any] = field(default_factory=dict)


class AlertPersister:
    """Persist derived alerts to the AnomalyAlertModel table."""

    def __init__(self, repository: TraceRepository, tenant_id: str = "local"):
        """Initialize the persister with a repository.

        Args:
            repository: TraceRepository instance for database access
            tenant_id: Tenant identifier for multi-tenant isolation
        """
        self.repository = repository
        self.tenant_id = tenant_id

    async def persist_alerts(
        self,
        session_id: str,
        alerts: list[DerivedAlert],
    ) -> list[dict[str, Any]]:
        """Persist derived alerts to the database.

        Args:
            session_id: Session ID to associate alerts with
            alerts: List of DerivedAlert instances to persist

        Returns:
            List of persisted alert dictionaries
        """
        from storage.models import AnomalyAlertModel

        persisted: list[dict[str, Any]] = []

        for alert in alerts:
            model = AnomalyAlertModel(
                id=str(uuid.uuid4()),
                tenant_id=self.tenant_id,
                session_id=session_id,
                alert_type=alert.alert_type,
                severity=alert.severity,
                signal=alert.signal,
                event_ids=alert.event_ids,
                detection_source=alert.source,
                detection_config=alert.detection_config,
                created_at=datetime.now(timezone.utc),
            )

            created = await self.repository.create_anomaly_alert(model)
            persisted.append(
                {
                    "id": created.id,
                    "session_id": created.session_id,
                    "alert_type": created.alert_type,
                    "severity": created.severity,
                    "signal": created.signal,
                    "event_ids": created.event_ids,
                    "detection_source": created.detection_source,
                    "created_at": created.created_at.isoformat() if created.created_at else None,
                }
            )

        return persisted

    async def persist_live_summary_alerts(
        self,
        session_id: str,
        live_summary: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Persist alerts from a live summary response.

        Args:
            session_id: Session ID to associate alerts with
            live_summary: Live summary dict containing recent_alerts

        Returns:
            List of persisted alert dictionaries
        """
        recent_alerts = live_summary.get("recent_alerts", [])
        derived_alerts: list[DerivedAlert] = []

        for alert in recent_alerts:
            # Only persist derived alerts (not captured ones which are already events)
            source = alert.get("source", "captured")
            if source == "derived":
                severity_raw = alert.get("severity", "medium")
                # Convert string severity to float
                if isinstance(severity_raw, str):
                    severity_map = {"low": 0.3, "medium": 0.5, "high": 0.8, "critical": 1.0}
                    severity = severity_map.get(severity_raw.lower(), 0.5)
                else:
                    severity = float(severity_raw)

                derived_alerts.append(
                    DerivedAlert(
                        alert_type=alert.get("alert_type", "unknown"),
                        severity=severity,
                        signal=alert.get("signal", ""),
                        event_ids=[alert.get("event_id")] if alert.get("event_id") else [],
                        source=source,
                        detection_config={},
                    )
                )

        # Also add oscillation alert if present
        oscillation = live_summary.get("oscillation_alert")
        if oscillation:
            derived_alerts.append(
                DerivedAlert(
                    alert_type="oscillation",
                    severity=oscillation.get("severity", 0.5),
                    signal=f"Oscillation pattern detected: {oscillation.get('pattern', 'unknown')}",
                    event_ids=oscillation.get("event_ids", []),
                    source="derived",
                    detection_config={
                        "repeat_count": oscillation.get("repeat_count", 0),
                        "event_type": oscillation.get("event_type", ""),
                    },
                )
            )

        return await self.persist_alerts(session_id, derived_alerts)

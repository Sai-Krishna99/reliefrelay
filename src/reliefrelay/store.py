from dataclasses import dataclass
from datetime import datetime
from typing import Any

from reliefrelay.domain import Incident


@dataclass
class IncidentRecord:
    incident: Incident
    report_count: int
    updated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident": self.incident.to_dict(),
            "report_count": self.report_count,
            "updated_at": self.updated_at.isoformat(),
        }


class InMemoryIncidentStore:
    def __init__(self) -> None:
        self._records: dict[str, IncidentRecord] = {}

    def upsert(self, incident: Incident) -> IncidentRecord:
        existing = self._records.get(incident.fingerprint)
        if existing is None:
            record = IncidentRecord(
                incident=incident,
                report_count=1,
                updated_at=incident.created_at,
            )
        else:
            record = IncidentRecord(
                incident=incident,
                report_count=existing.report_count + 1,
                updated_at=incident.created_at,
            )

        self._records[incident.fingerprint] = record
        return record

    def list(self) -> list[IncidentRecord]:
        severity_order = {"critical": 0, "high": 1, "standard": 2}
        return sorted(
            self._records.values(),
            key=lambda record: (
                severity_order[record.incident.severity],
                -record.updated_at.timestamp(),
            ),
        )

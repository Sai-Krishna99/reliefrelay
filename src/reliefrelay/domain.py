from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class Incident:
    id: str
    fingerprint: str
    location: str
    incident_type: str
    severity: str
    people_affected: int | None
    requested_resource: str | None
    transcript: str
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        return payload


def utc_now() -> datetime:
    return datetime.now(UTC)

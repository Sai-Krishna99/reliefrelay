from dataclasses import asdict, dataclass, field
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
    extraction_confidence: float = 0.0
    review_required: bool = True
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        payload["warnings"] = list(self.warnings)
        return payload


@dataclass(frozen=True)
class ExtractionAssessment:
    incident: Incident
    confidence: float
    review_required: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "review_required": self.review_required,
            "warnings": list(self.warnings),
        }


def utc_now() -> datetime:
    return datetime.now(UTC)

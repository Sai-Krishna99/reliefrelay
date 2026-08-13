from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from reliefrelay.domain import Incident


INCIDENT_STATUSES = (
    "needs_review",
    "acknowledged",
    "assigned",
    "dispatched",
    "resolved",
    "rejected",
)
SEVERITY_ORDER = {"standard": 0, "high": 1, "critical": 2}


@dataclass(frozen=True)
class ReportRecord:
    id: str
    incident_id: str
    source: str
    transcript: str
    extraction_confidence: float
    review_required: bool
    warnings: tuple[str, ...]
    processing: dict[str, Any]
    created_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "source": self.source,
            "transcript": self.transcript,
            "extraction_confidence": self.extraction_confidence,
            "review_required": self.review_required,
            "warnings": list(self.warnings),
            "processing": self.processing,
            "created_at": self.created_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewed_by": self.reviewed_by,
            "pending_review": self.review_required and self.reviewed_at is None,
        }


@dataclass(frozen=True)
class IncidentRecord:
    incident: Incident
    report_count: int
    updated_at: datetime
    status: str = "needs_review"
    assigned_to: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident": self.incident.to_dict(),
            "report_count": self.report_count,
            "updated_at": self.updated_at.isoformat(),
            "status": self.status,
            "assigned_to": self.assigned_to,
        }


@dataclass(frozen=True)
class IngestResult:
    incident: IncidentRecord
    report: ReportRecord


class SQLiteIncidentStore:
    """Thread-safe local incident store with report and audit history."""

    def __init__(
        self,
        database_path: Path | str = ":memory:",
        *,
        deduplication_window_hours: float = 24,
    ) -> None:
        if database_path != ":memory:":
            path = Path(database_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            database_path = path
        self._connection = sqlite3.connect(
            str(database_path),
            check_same_thread=False,
            timeout=10,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._deduplication_window = timedelta(
            hours=max(0.01, deduplication_window_hours)
        )
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    location TEXT NOT NULL,
                    incident_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    people_affected INTEGER,
                    requested_resource TEXT,
                    transcript TEXT NOT NULL,
                    extraction_confidence REAL NOT NULL,
                    review_required INTEGER NOT NULL,
                    warnings_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    assigned_to TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS incidents_fingerprint_status
                    ON incidents(fingerprint, status);
                CREATE INDEX IF NOT EXISTS incidents_priority
                    ON incidents(status, severity, updated_at);

                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL REFERENCES incidents(id),
                    source TEXT NOT NULL,
                    transcript TEXT NOT NULL,
                    extraction_confidence REAL NOT NULL,
                    review_required INTEGER NOT NULL,
                    warnings_json TEXT NOT NULL,
                    processing_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    reviewed_by TEXT
                );
                CREATE INDEX IF NOT EXISTS reports_incident_created
                    ON reports(incident_id, created_at);

                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL REFERENCES incidents(id),
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS audit_incident_created
                    ON audit_events(incident_id, created_at);
                """
            )
            report_columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(reports)")
            }
            if "reviewed_at" not in report_columns:
                self._connection.execute(
                    "ALTER TABLE reports ADD COLUMN reviewed_at TEXT"
                )
            if "reviewed_by" not in report_columns:
                self._connection.execute(
                    "ALTER TABLE reports ADD COLUMN reviewed_by TEXT"
                )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        return datetime.fromisoformat(value)

    @staticmethod
    def _incident_from_row(row: sqlite3.Row) -> Incident:
        return Incident(
            id=row["id"],
            fingerprint=row["fingerprint"],
            location=row["location"],
            incident_type=row["incident_type"],
            severity=row["severity"],
            people_affected=row["people_affected"],
            requested_resource=row["requested_resource"],
            transcript=row["transcript"],
            created_at=SQLiteIncidentStore._parse_datetime(row["created_at"]),
            extraction_confidence=row["extraction_confidence"],
            review_required=bool(row["review_required"]),
            warnings=tuple(json.loads(row["warnings_json"])),
        )

    def _record_from_row(self, row: sqlite3.Row) -> IncidentRecord:
        report_count = self._connection.execute(
            "SELECT COUNT(*) FROM reports WHERE incident_id = ?",
            (row["id"],),
        ).fetchone()[0]
        return IncidentRecord(
            incident=self._incident_from_row(row),
            report_count=report_count,
            updated_at=self._parse_datetime(row["updated_at"]),
            status=row["status"],
            assigned_to=row["assigned_to"],
        )

    @staticmethod
    def _report_from_row(row: sqlite3.Row) -> ReportRecord:
        return ReportRecord(
            id=row["id"],
            incident_id=row["incident_id"],
            source=row["source"],
            transcript=row["transcript"],
            extraction_confidence=row["extraction_confidence"],
            review_required=bool(row["review_required"]),
            warnings=tuple(json.loads(row["warnings_json"])),
            processing=json.loads(row["processing_json"]),
            created_at=SQLiteIncidentStore._parse_datetime(row["created_at"]),
            reviewed_at=(
                SQLiteIncidentStore._parse_datetime(row["reviewed_at"])
                if row["reviewed_at"]
                else None
            ),
            reviewed_by=row["reviewed_by"],
        )

    def _audit(
        self,
        incident_id: str,
        action: str,
        *,
        actor: str = "system",
        details: dict[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO audit_events
                (id, incident_id, action, actor, details_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                incident_id,
                action,
                actor,
                json.dumps(details or {}, sort_keys=True),
                (created_at or self._now()).isoformat(),
            ),
        )

    def ingest(
        self,
        incident: Incident,
        *,
        source: str = "text",
        processing: dict[str, Any] | None = None,
    ) -> IngestResult:
        with self._lock, self._connection:
            existing = self._connection.execute(
                """
                SELECT * FROM incidents
                WHERE fingerprint = ? AND status NOT IN ('resolved', 'rejected')
                    AND updated_at >= ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (
                    incident.fingerprint,
                    (incident.created_at - self._deduplication_window).isoformat(),
                ),
            ).fetchone()
            now = incident.created_at
            if existing is None:
                incident_id = incident.id
                status = "needs_review" if incident.review_required else "acknowledged"
                self._connection.execute(
                    """
                    INSERT INTO incidents (
                        id, fingerprint, location, incident_type, severity,
                        people_affected, requested_resource, transcript,
                        extraction_confidence, review_required, warnings_json,
                        status, assigned_to, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                    """,
                    (
                        incident_id,
                        incident.fingerprint,
                        incident.location,
                        incident.incident_type,
                        incident.severity,
                        incident.people_affected,
                        incident.requested_resource,
                        incident.transcript,
                        incident.extraction_confidence,
                        int(incident.review_required),
                        json.dumps(incident.warnings),
                        status,
                        incident.created_at.isoformat(),
                        now.isoformat(),
                    ),
                )
                audit_action = "incident.created"
            else:
                incident_id = existing["id"]
                prior_severity = existing["severity"]
                severity = max(
                    (prior_severity, incident.severity),
                    key=SEVERITY_ORDER.__getitem__,
                )
                severity_increased = SEVERITY_ORDER[severity] > SEVERITY_ORDER[prior_severity]
                status = "needs_review" if severity_increased else existing["status"]
                warnings = sorted(
                    set(json.loads(existing["warnings_json"])) | set(incident.warnings)
                )
                self._connection.execute(
                    """
                    UPDATE incidents SET
                        severity = ?,
                        people_affected = COALESCE(?, people_affected),
                        requested_resource = COALESCE(?, requested_resource),
                        transcript = ?,
                    extraction_confidence = ?,
                        review_required = 1,
                        warnings_json = ?,
                        status = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        severity,
                        incident.people_affected,
                        incident.requested_resource,
                        incident.transcript,
                        incident.extraction_confidence,
                        json.dumps(warnings),
                        status,
                        now.isoformat(),
                        incident_id,
                    ),
                )
                audit_action = "report.merged"

            report = ReportRecord(
                id=str(uuid4()),
                incident_id=incident_id,
                source=source,
                transcript=incident.transcript,
                extraction_confidence=incident.extraction_confidence,
                review_required=incident.review_required,
                warnings=incident.warnings,
                processing=processing or {},
                created_at=now,
            )
            self._connection.execute(
                """
                INSERT INTO reports (
                    id, incident_id, source, transcript, extraction_confidence,
                    review_required, warnings_json, processing_json, created_at,
                    reviewed_at, reviewed_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    report.id,
                    report.incident_id,
                    report.source,
                    report.transcript,
                    report.extraction_confidence,
                    int(report.review_required),
                    json.dumps(report.warnings),
                    json.dumps(report.processing, sort_keys=True),
                    report.created_at.isoformat(),
                ),
            )
            self._audit(
                incident_id,
                audit_action,
                details={"report_id": report.id, "source": source},
                created_at=now,
            )
            row = self._connection.execute(
                "SELECT * FROM incidents WHERE id = ?", (incident_id,)
            ).fetchone()
            return IngestResult(self._record_from_row(row), report)

    def upsert(self, incident: Incident) -> IncidentRecord:
        return self.ingest(incident).incident

    def list(self, *, include_closed: bool = True) -> list[IncidentRecord]:
        query = "SELECT * FROM incidents"
        parameters: tuple[str, ...] = ()
        if not include_closed:
            query += " WHERE status NOT IN (?, ?)"
            parameters = ("resolved", "rejected")
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
            records = [self._record_from_row(row) for row in rows]
        status_order = {
            "needs_review": 0,
            "acknowledged": 1,
            "assigned": 2,
            "dispatched": 3,
            "resolved": 4,
            "rejected": 5,
        }
        return sorted(
            records,
            key=lambda record: (
                0 if record.incident.review_required else 1,
                status_order[record.status],
                -SEVERITY_ORDER[record.incident.severity],
                -record.updated_at.timestamp(),
            ),
        )

    def get(self, incident_id: str) -> IncidentRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM incidents WHERE id = ?", (incident_id,)
            ).fetchone()
            return self._record_from_row(row) if row else None

    def reports(self, incident_id: str) -> list[ReportRecord]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM reports WHERE incident_id = ? ORDER BY created_at",
                (incident_id,),
            ).fetchall()
        return [self._report_from_row(row) for row in rows]

    def audit_events(self, incident_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM audit_events WHERE incident_id = ? ORDER BY created_at",
                (incident_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "incident_id": row["incident_id"],
                "action": row["action"],
                "actor": row["actor"],
                "details": json.loads(row["details_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def update(
        self,
        incident_id: str,
        *,
        status: str | None = None,
        assigned_to: str | None = None,
        actor: str = "operator",
        corrections: dict[str, Any] | None = None,
    ) -> IncidentRecord | None:
        if status is not None and status not in INCIDENT_STATUSES:
            raise ValueError(f"Unsupported incident status: {status}")
        corrections = corrections or {}
        allowed_corrections = {
            "location",
            "incident_type",
            "severity",
            "people_affected",
            "requested_resource",
            "transcript",
        }
        unknown = set(corrections) - allowed_corrections
        if unknown:
            raise ValueError(f"Unsupported corrections: {', '.join(sorted(unknown))}")
        if "severity" in corrections and corrections["severity"] not in SEVERITY_ORDER:
            raise ValueError("Severity must be critical, high, or standard")

        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT * FROM incidents WHERE id = ?", (incident_id,)
            ).fetchone()
            if row is None:
                return None
            changes: dict[str, Any] = {}
            values = dict(row)
            if status is not None and status != row["status"]:
                values["status"] = status
                changes["status"] = {"from": row["status"], "to": status}
            if assigned_to is not None and assigned_to != row["assigned_to"]:
                values["assigned_to"] = assigned_to or None
                changes["assigned_to"] = {
                    "from": row["assigned_to"],
                    "to": assigned_to or None,
                }
            for field, value in corrections.items():
                if value != row[field]:
                    values[field] = value
                    changes[field] = {"from": row[field], "to": value}
            if values["status"] in {"assigned", "dispatched"} and not values[
                "assigned_to"
            ]:
                raise ValueError(
                    f"An assignee is required when status is {values['status']}"
                )
            review_cleared = bool(row["review_required"]) and (
                status is not None and status != "needs_review"
            )
            if review_cleared:
                changes["review_required"] = {"from": True, "to": False}
            if not changes:
                return self._record_from_row(row)

            review_required = (
                0
                if review_cleared or values["status"] != "needs_review"
                else 1
            )
            identity = f"{values['location'].casefold()}:{values['incident_type']}"
            if values["location"] == "Unknown location" or values["incident_type"] == "other":
                identity = f"{identity}:{values['transcript'].casefold()}"
            fingerprint = hashlib.sha256(identity.encode()).hexdigest()[:12]
            now = self._now()
            self._connection.execute(
                """
                UPDATE incidents SET
                    fingerprint = ?, location = ?, incident_type = ?, severity = ?,
                    people_affected = ?, requested_resource = ?, status = ?,
                    assigned_to = ?, transcript = ?, review_required = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    fingerprint,
                    values["location"],
                    values["incident_type"],
                    values["severity"],
                    values["people_affected"],
                    values["requested_resource"],
                    values["status"],
                    values["assigned_to"],
                    values["transcript"],
                    review_required,
                    now.isoformat(),
                    incident_id,
                ),
            )
            self._audit(
                incident_id,
                "incident.updated",
                actor=actor,
                details={"changes": changes},
                created_at=now,
            )
            if review_required == 0:
                self._connection.execute(
                    """
                    UPDATE reports SET reviewed_at = ?, reviewed_by = ?
                    WHERE incident_id = ? AND reviewed_at IS NULL
                    """,
                    (now.isoformat(), actor, incident_id),
                )
            updated = self._connection.execute(
                "SELECT * FROM incidents WHERE id = ?", (incident_id,)
            ).fetchone()
            return self._record_from_row(updated)


class InMemoryIncidentStore(SQLiteIncidentStore):
    """Compatibility name backed by an isolated in-memory SQLite database."""

    def __init__(self) -> None:
        super().__init__(":memory:")

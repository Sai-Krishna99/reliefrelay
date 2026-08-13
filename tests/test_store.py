from pathlib import Path

from reliefrelay.extraction import EmergencyReportExtractor, RESPONSE_LOCATIONS
from reliefrelay.store import SQLiteIncidentStore


def test_store_persists_reports_and_never_silently_downgrades(tmp_path: Path) -> None:
    database = tmp_path / "reliefrelay.db"
    extractor = EmergencyReportExtractor(RESPONSE_LOCATIONS)
    store = SQLiteIncidentStore(database)
    first = extractor.extract(
        "Medical emergency at Harbor School. One patient unconscious."
    )
    second = extractor.extract(
        "Harbor School reporting medical issue. Situation stable."
    )

    store.ingest(first, source="radio-1")
    merged = store.ingest(second, source="radio-2").incident

    assert merged.report_count == 2
    assert merged.incident.severity == "critical"
    assert len(store.reports(merged.incident.id)) == 2

    reopened = SQLiteIncidentStore(database)
    assert reopened.get(merged.incident.id) is not None
    assert reopened.get(merged.incident.id).report_count == 2


def test_resolved_incident_does_not_absorb_a_new_emergency() -> None:
    extractor = EmergencyReportExtractor(RESPONSE_LOCATIONS)
    store = SQLiteIncidentStore()
    report = extractor.extract("Fire at North Clinic. One patient trapped.")
    first = store.ingest(report).incident
    store.update(first.incident.id, status="resolved", actor="dispatcher")

    second = store.ingest(extractor.extract(report.transcript)).incident

    assert second.incident.id != first.incident.id
    assert len(store.list()) == 2


def test_each_merged_report_requires_a_recorded_operator_review() -> None:
    extractor = EmergencyReportExtractor(RESPONSE_LOCATIONS)
    store = SQLiteIncidentStore()
    first = store.ingest(
        extractor.extract("Fire at North Clinic. One patient trapped.")
    ).incident
    store.update(first.incident.id, status="acknowledged", actor="dispatcher-a")

    merged = store.ingest(
        extractor.extract("North Clinic reporting fire. Send a fire crew.")
    ).incident

    assert merged.status == "acknowledged"
    assert merged.incident.review_required is True
    assert [report.to_dict()["pending_review"] for report in store.reports(first.incident.id)] == [
        False,
        True,
    ]

    store.update(first.incident.id, status="acknowledged", actor="dispatcher-b")
    reports = store.reports(first.incident.id)
    assert [report.to_dict()["pending_review"] for report in reports] == [False, False]
    assert reports[-1].reviewed_by == "dispatcher-b"


def test_assignment_requires_an_assignee() -> None:
    extractor = EmergencyReportExtractor(RESPONSE_LOCATIONS)
    store = SQLiteIncidentStore()
    record = store.ingest(
        extractor.extract("Fire at North Clinic. One patient trapped.")
    ).incident

    try:
        store.update(record.incident.id, status="assigned", actor="dispatcher")
    except ValueError as error:
        assert "assignee is required" in str(error)
    else:
        raise AssertionError("Assignment without an assignee should fail")

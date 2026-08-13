import io
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from reliefrelay.api import create_app
from reliefrelay.transcription import TranscriptResult


class StubAudioTranscriber:
    def transcribe(self, audio_path: Path) -> TranscriptResult:
        assert audio_path.exists()
        assert audio_path.read_bytes().startswith(b"RIFF")
        return TranscriptResult(
            text=(
                "Medic 4 reporting from North Clinic. Fire in the east wing. "
                "Two patients trapped. Send a rescue team immediately."
            ),
            duration_seconds=8.1,
            inference_seconds=1.2,
            model="ggml-tiny.en-q5_1.bin",
            runtime="whisper.cpp",
            architecture="aarch64",
        )


def valid_wav_bytes() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(b"\x00\x00" * 16_000)
    return output.getvalue()


def test_text_report_creates_incident() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/reports/text",
        json={
            "transcript": (
                "Medic 4 reporting from North Clinic. Fire in the east wing. "
                "Two patients trapped. Send a rescue team immediately."
            )
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["incident"]["location"] == "North Clinic"
    assert body["incident"]["severity"] == "critical"
    assert body["report_count"] == 1
    assert body["processing"]["mode"] == "transcript-simulation"


def test_related_reports_merge_into_one_incident() -> None:
    client = TestClient(create_app())
    reports = (
        "Flooding at Riverside Shelter. Six people need evacuation.",
        "Riverside Shelter reporting flood water. Send rescue support.",
    )

    for transcript in reports:
        response = client.post(
            "/api/reports/text",
            json={"transcript": transcript},
        )
        assert response.status_code == 201

    incidents = client.get("/api/incidents").json()
    assert len(incidents) == 1
    assert incidents[0]["report_count"] == 2


def test_health_exposes_runtime_architecture() -> None:
    client = TestClient(create_app(discover_transcriber=False))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["inference"] == "setup-required"
    assert response.json()["architecture"]


def test_health_is_operational_when_inference_is_ready() -> None:
    client = TestClient(create_app(transcriber=StubAudioTranscriber()))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "operational"
    assert response.json()["inference"] == "ready"


def test_root_serves_operations_board() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "ReliefRelay" in response.text
    assert "Response Operations" in response.text


def test_dashboard_serves_synthetic_audio_fixture() -> None:
    client = TestClient(create_app())

    response = client.get("/audio/riverside-flood-radio.wav")

    assert response.status_code == 200
    assert response.headers["content-type"] in {"audio/wav", "audio/x-wav"}
    assert response.content[:4] == b"RIFF"


def test_audio_report_transcribes_and_routes_incident() -> None:
    client = TestClient(create_app(transcriber=StubAudioTranscriber()))

    response = client.post(
        "/api/reports/audio",
        files={"audio": ("north-clinic.wav", valid_wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["incident"]["location"] == "North Clinic"
    assert body["incident"]["incident_type"] == "fire"
    assert body["processing"]["mode"] == "local-audio"
    assert body["processing"]["runtime"] == "whisper.cpp"
    assert body["processing"]["architecture"] == "aarch64"
    assert body["processing"]["real_time_factor"] == 0.15
    assert body["status"] == "needs_review"
    assert body["assessment"]["review_required"] is True
    assert body["report"]["source"] == "audio:north-clinic.wav"


def test_audio_report_requires_local_whisper_runtime() -> None:
    client = TestClient(create_app(discover_transcriber=False))

    response = client.post(
        "/api/reports/audio",
        files={"audio": ("report.wav", b"RIFF-test-audio", "audio/wav")},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Local Whisper runtime is not configured"


def test_audio_report_rejects_non_wav_upload() -> None:
    client = TestClient(create_app(transcriber=StubAudioTranscriber()))

    response = client.post(
        "/api/reports/audio",
        files={"audio": ("report.mp3", b"not-a-wave", "audio/mpeg")},
    )

    assert response.status_code == 415


def test_audio_report_rejects_invalid_wav_content() -> None:
    client = TestClient(create_app(transcriber=StubAudioTranscriber()))

    response = client.post(
        "/api/reports/audio",
        files={"audio": ("report.wav", b"not-a-wave", "audio/wav")},
    )

    assert response.status_code == 422
    assert "valid WAV" in response.json()["detail"]


def test_operator_can_review_assign_and_inspect_history() -> None:
    client = TestClient(create_app())
    created = client.post(
        "/api/reports/text",
        json={
            "transcript": "Fire at North Clinic. Two patients trapped.",
            "source": "radio-console-4",
        },
    ).json()
    incident_id = created["incident"]["id"]

    updated = client.patch(
        f"/api/incidents/{incident_id}",
        json={
            "status": "assigned",
            "assigned_to": "Engine 2",
            "actor": "dispatcher-a",
            "people_affected": 3,
        },
    )

    assert updated.status_code == 200
    assert updated.json()["status"] == "assigned"
    assert updated.json()["assigned_to"] == "Engine 2"
    assert updated.json()["incident"]["people_affected"] == 3
    detail = client.get(f"/api/incidents/{incident_id}").json()
    assert len(detail["reports"]) == 1
    assert detail["reports"][0]["source"] == "radio-console-4"
    assert detail["reports"][0]["pending_review"] is False
    assert detail["reports"][0]["reviewed_by"] == "dispatcher-a"
    assert [event["action"] for event in detail["audit_events"]] == [
        "incident.created",
        "incident.updated",
    ]


def test_operator_token_protects_operational_api() -> None:
    client = TestClient(create_app(api_token="correct-horse-battery-staple"))

    denied = client.get("/api/incidents")
    allowed = client.get(
        "/api/incidents",
        headers={"Authorization": "Bearer correct-horse-battery-staple"},
    )
    health = client.get("/api/health")

    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert health.status_code == 200
    assert allowed.headers["x-frame-options"] == "DENY"

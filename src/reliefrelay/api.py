import asyncio
import hmac
import os
import platform
import subprocess
import tempfile
import wave
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles

from reliefrelay.extraction import EmergencyReportExtractor, RESPONSE_LOCATIONS
from reliefrelay.pipeline import AudioReportPipeline, Transcriber
from reliefrelay.platform_info import default_inference_threads
from reliefrelay.store import (
    InMemoryIncidentStore,
    SQLiteIncidentStore,
)
from reliefrelay.transcription import WhisperCppTranscriber


MAX_AUDIO_BYTES = 25 * 1024 * 1024
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TextReportRequest(BaseModel):
    transcript: str = Field(min_length=3, max_length=4_000)
    source: str = Field(default="operator-text", min_length=2, max_length=80)


class IncidentUpdateRequest(BaseModel):
    status: Literal[
        "needs_review",
        "acknowledged",
        "assigned",
        "dispatched",
        "resolved",
        "rejected",
    ] | None = None
    assigned_to: str | None = Field(default=None, max_length=120)
    actor: str = Field(default="operator", min_length=2, max_length=120)
    location: str | None = Field(default=None, min_length=2, max_length=120)
    incident_type: str | None = Field(default=None, min_length=2, max_length=80)
    severity: Literal["critical", "high", "standard"] | None = None
    people_affected: int | None = Field(default=None, ge=0, le=1_000_000)
    requested_resource: str | None = Field(default=None, max_length=120)
    transcript: str | None = Field(default=None, min_length=3, max_length=4_000)


def configured_transcriber() -> WhisperCppTranscriber | None:
    executable_name = "whisper-cli.exe" if os.name == "nt" else "whisper-cli"
    configured_binary = os.getenv("RELIEFRELAY_WHISPER_BINARY")
    if configured_binary:
        binary_path = Path(configured_binary)
    else:
        candidates = sorted(
            (PROJECT_ROOT / ".local" / "whisper").rglob(executable_name)
        )
        binary_path = candidates[0] if candidates else Path(executable_name)
    model_path = Path(
        os.getenv(
            "RELIEFRELAY_WHISPER_MODEL",
            PROJECT_ROOT / "models" / "whisper" / "ggml-tiny.en-q5_1.bin",
        )
    )
    if not binary_path.exists() or not model_path.exists():
        return None
    threads = max(
        1,
        int(
            os.getenv(
                "RELIEFRELAY_WHISPER_THREADS",
                str(default_inference_threads()),
            )
        ),
    )
    timeout_seconds = max(
        1.0,
        float(os.getenv("RELIEFRELAY_WHISPER_TIMEOUT_SECONDS", "120")),
    )
    return WhisperCppTranscriber(
        binary_path,
        model_path,
        threads=threads,
        timeout_seconds=timeout_seconds,
    )


def validate_wav(path: Path) -> None:
    try:
        with wave.open(str(path), "rb") as wav_file:
            if wav_file.getcomptype() != "NONE" or wav_file.getsampwidth() != 2:
                raise ValueError("Audio must be uncompressed 16-bit PCM WAV")
            if wav_file.getnchannels() not in (1, 2):
                raise ValueError("Audio must contain one or two channels")
            if wav_file.getframerate() < 8_000 or wav_file.getframerate() > 96_000:
                raise ValueError("Audio sample rate must be between 8 kHz and 96 kHz")
            if wav_file.getnframes() == 0:
                raise ValueError("Audio report is empty")
    except (wave.Error, EOFError) as error:
        raise ValueError("Audio is not a valid WAV file") from error


def create_app(
    transcriber: Transcriber | None = None,
    *,
    discover_transcriber: bool = True,
    store: SQLiteIncidentStore | None = None,
    api_token: str | None = None,
) -> FastAPI:
    app = FastAPI(
        title="ReliefRelay",
        description="Arm-optimized emergency voice intelligence",
        version="0.1.0",
    )
    extractor = EmergencyReportExtractor(known_locations=RESPONSE_LOCATIONS)
    incident_store = store or InMemoryIncidentStore()
    audio_transcriber = transcriber
    if audio_transcriber is None and discover_transcriber:
        audio_transcriber = configured_transcriber()
    audio_pipeline = (
        AudioReportPipeline(audio_transcriber, extractor)
        if audio_transcriber is not None
        else None
    )
    inference_limit = max(
        1,
        int(os.getenv("RELIEFRELAY_MAX_CONCURRENT_INFERENCE", "1")),
    )
    inference_slots = asyncio.Semaphore(inference_limit)
    queue_timeout_seconds = max(
        0.1,
        float(os.getenv("RELIEFRELAY_QUEUE_TIMEOUT_SECONDS", "5")),
    )
    required_api_token = api_token or os.getenv("RELIEFRELAY_API_TOKEN")

    @app.middleware("http")
    async def secure_requests(request: Request, call_next: Any) -> Any:
        if (
            required_api_token
            and request.url.path.startswith("/api/")
            and request.url.path != "/api/health"
        ):
            authorization = request.headers.get("authorization", "")
            supplied = authorization.removeprefix("Bearer ")
            if not hmac.compare_digest(supplied, required_api_token):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Valid operator token required"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; media-src 'self' blob:; connect-src 'self'"
        )
        return response

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {
            "status": "operational" if audio_pipeline is not None else "degraded",
            "architecture": platform.machine() or "unknown",
            "inference": "ready" if audio_pipeline is not None else "setup-required",
            "storage": "ready",
        }

    @app.get("/api/incidents")
    def list_incidents(
        include_closed: bool = Query(default=True),
    ) -> list[dict[str, Any]]:
        return [
            record.to_dict()
            for record in incident_store.list(include_closed=include_closed)
        ]

    @app.get("/api/incidents/{incident_id}")
    def get_incident(incident_id: str) -> dict[str, Any]:
        record = incident_store.get(incident_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        return {
            **record.to_dict(),
            "reports": [
                report.to_dict() for report in incident_store.reports(incident_id)
            ],
            "audit_events": incident_store.audit_events(incident_id),
        }

    @app.patch("/api/incidents/{incident_id}")
    def update_incident(
        incident_id: str,
        update: IncidentUpdateRequest,
    ) -> dict[str, Any]:
        provided = update.model_fields_set
        corrections = {
            field: getattr(update, field)
            for field in (
                "location",
                "incident_type",
                "severity",
                "people_affected",
                "requested_resource",
                "transcript",
            )
            if field in provided
        }
        try:
            record = incident_store.update(
                incident_id,
                status=update.status if "status" in provided else None,
                assigned_to=update.assigned_to if "assigned_to" in provided else None,
                actor=update.actor,
                corrections=corrections,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if record is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        return record.to_dict()

    @app.post("/api/reports/text", status_code=status.HTTP_201_CREATED)
    def create_text_report(report: TextReportRequest) -> dict[str, Any]:
        assessment = extractor.extract_with_assessment(report.transcript)
        processing = {
            "mode": "transcript-simulation",
            "architecture": platform.machine() or "unknown",
        }
        ingested = incident_store.ingest(
            assessment.incident,
            source=report.source,
            processing=processing,
        )
        return {
            **ingested.incident.to_dict(),
            "processing": processing,
            "assessment": assessment.to_dict(),
            "report": ingested.report.to_dict(),
        }

    @app.post("/api/reports/audio", status_code=status.HTTP_201_CREATED)
    async def create_audio_report(
        audio: UploadFile = File(description="16-bit PCM WAV field report"),
    ) -> dict[str, Any]:
        if audio_pipeline is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Local Whisper runtime is not configured",
            )
        if Path(audio.filename or "report.wav").suffix.lower() != ".wav":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Only WAV field reports are supported",
            )

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                total_bytes = 0
                while chunk := await audio.read(1024 * 1024):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_AUDIO_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                            detail="Audio report exceeds the 25 MB limit",
                        )
                    temporary.write(chunk)

            validate_wav(temporary_path)
            try:
                await asyncio.wait_for(
                    inference_slots.acquire(),
                    timeout=queue_timeout_seconds,
                )
            except TimeoutError as error:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Local inference is busy; retry shortly",
                ) from error
            try:
                result = await asyncio.to_thread(audio_pipeline.process, temporary_path)
            finally:
                inference_slots.release()
            processing = {
                "mode": "local-audio",
                **asdict(result.transcription),
                "real_time_factor": result.transcription.real_time_factor,
            }
            ingested = incident_store.ingest(
                result.incident,
                source=f"audio:{Path(audio.filename or 'report.wav').name[:120]}",
                processing=processing,
            )
            return {
                **ingested.incident.to_dict(),
                "processing": processing,
                "assessment": result.assessment.to_dict(),
                "report": ingested.report.to_dict(),
            }
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Whisper runtime asset not found: {Path(error.filename or str(error)).name}",
            ) from error
        except subprocess.CalledProcessError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Whisper could not transcribe this audio report",
            ) from error
        except subprocess.TimeoutExpired as error:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Local transcription exceeded its time limit",
            ) from error
        finally:
            await audio.close()
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    static_directory = Path(__file__).parent / "static"
    app.mount("/", StaticFiles(directory=static_directory, html=True), name="static")

    return app


database_path = Path(
    os.getenv(
        "RELIEFRELAY_DATABASE",
        PROJECT_ROOT / ".local" / "reliefrelay.db",
    )
)
app = create_app(
    store=SQLiteIncidentStore(
        database_path,
        deduplication_window_hours=float(
            os.getenv("RELIEFRELAY_DEDUPLICATION_WINDOW_HOURS", "24")
        ),
    )
)

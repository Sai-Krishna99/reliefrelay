import os
import platform
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles

from reliefrelay.extraction import EmergencyReportExtractor, RESPONSE_LOCATIONS
from reliefrelay.pipeline import AudioReportPipeline, Transcriber
from reliefrelay.store import InMemoryIncidentStore
from reliefrelay.transcription import WhisperCppTranscriber


MAX_AUDIO_BYTES = 25 * 1024 * 1024
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TextReportRequest(BaseModel):
    transcript: str = Field(min_length=3, max_length=4_000)


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
    threads = int(os.getenv("RELIEFRELAY_WHISPER_THREADS", "4"))
    return WhisperCppTranscriber(binary_path, model_path, threads=threads)


def create_app(
    transcriber: Transcriber | None = None,
    *,
    discover_transcriber: bool = True,
) -> FastAPI:
    app = FastAPI(
        title="ReliefRelay",
        description="Arm-optimized emergency voice intelligence",
        version="0.1.0",
    )
    extractor = EmergencyReportExtractor(known_locations=RESPONSE_LOCATIONS)
    store = InMemoryIncidentStore()
    audio_transcriber = transcriber
    if audio_transcriber is None and discover_transcriber:
        audio_transcriber = configured_transcriber()
    audio_pipeline = (
        AudioReportPipeline(audio_transcriber, extractor)
        if audio_transcriber is not None
        else None
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {
            "status": "operational",
            "architecture": platform.machine() or "unknown",
            "inference": "ready" if audio_pipeline is not None else "setup-required",
        }

    @app.get("/api/incidents")
    def list_incidents() -> list[dict[str, Any]]:
        return [record.to_dict() for record in store.list()]

    @app.post("/api/reports/text", status_code=status.HTTP_201_CREATED)
    def create_text_report(report: TextReportRequest) -> dict[str, Any]:
        incident = extractor.extract(report.transcript)
        record = store.upsert(incident)
        return {
            **record.to_dict(),
            "processing": {
                "mode": "transcript-simulation",
                "architecture": platform.machine() or "unknown",
            },
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

            result = audio_pipeline.process(temporary_path)
            record = store.upsert(result.incident)
            return {
                **record.to_dict(),
                "processing": {
                    "mode": "local-audio",
                    **asdict(result.transcription),
                    "real_time_factor": result.transcription.real_time_factor,
                },
            }
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
        finally:
            await audio.close()
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    static_directory = Path(__file__).parent / "static"
    app.mount("/", StaticFiles(directory=static_directory, html=True), name="static")

    return app


app = create_app()

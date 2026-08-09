from pathlib import Path

from reliefrelay.extraction import EmergencyReportExtractor
from reliefrelay.pipeline import AudioReportPipeline
from reliefrelay.transcription import TranscriptResult
from reliefrelay.transcription import WhisperCppTranscriber


class StubTranscriber:
    def transcribe(self, audio_path: Path) -> TranscriptResult:
        assert audio_path.name == "report.wav"
        return TranscriptResult(
            text="Fire at North Clinic. Two people trapped. Send medical team.",
            duration_seconds=4.2,
            inference_seconds=0.8,
            model="whisper-tiny.en-q5_1",
            runtime="whisper.cpp",
            architecture="aarch64",
        )


def test_pipeline_preserves_arm_inference_provenance(tmp_path: Path) -> None:
    audio_path = tmp_path / "report.wav"
    audio_path.touch()
    pipeline = AudioReportPipeline(
        transcriber=StubTranscriber(),
        extractor=EmergencyReportExtractor(),
    )

    result = pipeline.process(audio_path)

    assert result.incident.location == "North Clinic"
    assert result.incident.incident_type == "fire"
    assert result.incident.severity == "critical"
    assert result.transcription.runtime == "whisper.cpp"
    assert result.transcription.architecture == "aarch64"
    assert result.transcription.real_time_factor == 0.19


def test_whisper_cpp_adapter_invokes_cpu_runtime_and_parses_json(
    tmp_path: Path,
) -> None:
    import json
    import subprocess
    import wave

    binary_path = tmp_path / "whisper-cli"
    model_path = tmp_path / "ggml-tiny.en-q5_1.bin"
    audio_path = tmp_path / "field-report.wav"
    binary_path.touch()
    model_path.touch()
    with wave.open(str(audio_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(b"\x00\x00" * 16_000)

    captured_command: list[str] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        captured_command.extend(command)
        output_prefix = Path(command[command.index("-of") + 1])
        output_prefix.with_suffix(".json").write_text(
            json.dumps(
                {
                    "transcription": [
                        {"text": " Fire at North Clinic."},
                        {"text": " Two people trapped."},
                    ]
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    timings = iter((10.0, 10.75))
    transcriber = WhisperCppTranscriber(
        binary_path=binary_path,
        model_path=model_path,
        threads=3,
        run_command=fake_run,
        timer=lambda: next(timings),
    )

    result = transcriber.transcribe(audio_path)

    assert result.text == "Fire at North Clinic. Two people trapped."
    assert result.duration_seconds == 1.0
    assert result.inference_seconds == 0.75
    assert result.model == "ggml-tiny.en-q5_1.bin"
    assert "-ng" in captured_command
    assert captured_command[captured_command.index("-t") + 1] == "3"

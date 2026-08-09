import json
import platform
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class TranscriptResult:
    text: str
    duration_seconds: float
    inference_seconds: float
    model: str
    runtime: str
    architecture: str

    @property
    def real_time_factor(self) -> float:
        if self.duration_seconds == 0:
            return 0.0
        return round(self.inference_seconds / self.duration_seconds, 2)


class WhisperCppTranscriber:
    def __init__(
        self,
        binary_path: Path,
        model_path: Path,
        threads: int = 4,
        run_command: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._binary_path = binary_path
        self._model_path = model_path
        self._threads = threads
        self._run_command = run_command
        self._timer = timer

    def transcribe(self, audio_path: Path) -> TranscriptResult:
        for required_path in (self._binary_path, self._model_path, audio_path):
            if not required_path.exists():
                raise FileNotFoundError(required_path)

        with tempfile.TemporaryDirectory(prefix="reliefrelay-") as directory:
            output_prefix = Path(directory) / "transcript"
            command = [
                str(self._binary_path),
                "-m",
                str(self._model_path),
                "-f",
                str(audio_path),
                "-t",
                str(self._threads),
                "-oj",
                "-of",
                str(output_prefix),
                "-np",
                "-nt",
                "-ng",
            ]
            started_at = self._timer()
            self._run_command(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
            inference_seconds = round(self._timer() - started_at, 3)
            output = json.loads(
                output_prefix.with_suffix(".json").read_text(encoding="utf-8")
            )

        transcript = " ".join(
            segment["text"].strip() for segment in output["transcription"]
        ).strip()
        return TranscriptResult(
            text=transcript,
            duration_seconds=self._wav_duration(audio_path),
            inference_seconds=inference_seconds,
            model=self._model_path.name,
            runtime="whisper.cpp",
            architecture=platform.machine() or "unknown",
        )

    @staticmethod
    def _wav_duration(audio_path: Path) -> float:
        with wave.open(str(audio_path), "rb") as audio:
            return round(audio.getnframes() / audio.getframerate(), 3)

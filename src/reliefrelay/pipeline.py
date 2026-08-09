from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from reliefrelay.domain import Incident
from reliefrelay.extraction import EmergencyReportExtractor
from reliefrelay.transcription import TranscriptResult


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> TranscriptResult: ...


@dataclass(frozen=True)
class PipelineResult:
    incident: Incident
    transcription: TranscriptResult


class AudioReportPipeline:
    def __init__(
        self,
        transcriber: Transcriber,
        extractor: EmergencyReportExtractor,
    ) -> None:
        self._transcriber = transcriber
        self._extractor = extractor

    def process(self, audio_path: Path) -> PipelineResult:
        transcription = self._transcriber.transcribe(audio_path)
        incident = self._extractor.extract(transcription.text)
        return PipelineResult(incident=incident, transcription=transcription)

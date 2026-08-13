from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from reliefrelay.domain import ExtractionAssessment, Incident
from reliefrelay.extraction import EmergencyReportExtractor
from reliefrelay.transcription import TranscriptResult


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> TranscriptResult: ...


@dataclass(frozen=True)
class PipelineResult:
    incident: Incident
    transcription: TranscriptResult
    assessment: ExtractionAssessment


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
        assessment = self._extractor.extract_with_assessment(transcription.text)
        return PipelineResult(
            incident=assessment.incident,
            transcription=transcription,
            assessment=assessment,
        )

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
from statistics import mean
from typing import Any

from reliefrelay.api import configured_transcriber
from reliefrelay.benchmark import word_error_rate
from reliefrelay.extraction import EmergencyReportExtractor, RESPONSE_LOCATIONS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark ReliefRelay audio fixtures")
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("src/reliefrelay/static/audio"),
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def benchmark(fixtures_directory: Path) -> dict[str, Any]:
    transcriber = configured_transcriber()
    if transcriber is None:
        raise SystemExit("Whisper runtime is not configured")
    extractor = EmergencyReportExtractor(known_locations=RESPONSE_LOCATIONS)
    manifest = json.loads(
        (fixtures_directory / "manifest.json").read_text(encoding="utf-8")
    )
    results: list[dict[str, Any]] = []

    for fixture in manifest["fixtures"]:
        transcription = transcriber.transcribe(fixtures_directory / fixture["file"])
        incident = extractor.extract(transcription.text)
        field_results = {
            field: getattr(incident, field) == expected
            for field, expected in fixture["expected"].items()
        }
        results.append(
            {
                "file": fixture["file"],
                "variant": fixture["variant"],
                "transcript": transcription.text,
                "word_error_rate": word_error_rate(
                    fixture["transcript"], transcription.text
                ),
                "inference_seconds": transcription.inference_seconds,
                "audio_seconds": transcription.duration_seconds,
                "real_time_factor": transcription.real_time_factor,
                "field_results": field_results,
            }
        )

    field_checks = [
        passed
        for result in results
        for passed in result["field_results"].values()
    ]
    return {
        "runtime": {
            "architecture": platform.machine() or "unknown",
            "processor": platform.processor() or "unknown",
            "model": "ggml-tiny.en-q5_1.bin",
            "engine": "whisper.cpp",
        },
        "summary": {
            "fixture_count": len(results),
            "mean_inference_seconds": round(
                mean(result["inference_seconds"] for result in results), 4
            ),
            "mean_real_time_factor": round(
                mean(result["real_time_factor"] for result in results), 4
            ),
            "mean_word_error_rate": round(
                mean(result["word_error_rate"] for result in results), 4
            ),
            "structured_field_accuracy": round(
                sum(field_checks) / len(field_checks), 4
            ),
        },
        "fixtures": results,
    }


if __name__ == "__main__":
    arguments = parse_args()
    report = benchmark(arguments.fixtures)
    serialized = json.dumps(report, indent=2) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")

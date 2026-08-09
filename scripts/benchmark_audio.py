from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
from statistics import mean, median
from typing import Any

from reliefrelay.benchmark import percentile, word_error_rate
from reliefrelay.extraction import EmergencyReportExtractor, RESPONSE_LOCATIONS
from reliefrelay.transcription import WhisperCppTranscriber


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark ReliefRelay audio fixtures")
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("src/reliefrelay/static/audio"),
    )
    parser.add_argument("--binary", type=Path)
    parser.add_argument(
        "--model",
        type=Path,
        default=Path("models/whisper/ggml-tiny.en-q5_1.bin"),
    )
    parser.add_argument("--label", default="q5_1")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--warmups", type=int, default=0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_binary() -> Path:
    executable_name = "whisper-cli.exe" if os.name == "nt" else "whisper-cli"
    runtime_directory = PROJECT_ROOT / ".local" / "whisper"
    candidates = sorted(runtime_directory.rglob(executable_name))
    if len(candidates) != 1:
        raise SystemExit(
            f"Expected one {executable_name} under .local/whisper, "
            f"found {len(candidates)}"
        )
    return candidates[0]


def benchmark(
    fixtures_directory: Path,
    *,
    binary_path: Path,
    model_path: Path,
    label: str,
    threads: int,
    runs: int,
    warmups: int,
) -> dict[str, Any]:
    if runs < 1:
        raise ValueError("runs must be at least 1")
    if warmups < 0:
        raise ValueError("warmups cannot be negative")

    transcriber = WhisperCppTranscriber(binary_path, model_path, threads=threads)
    extractor = EmergencyReportExtractor(known_locations=RESPONSE_LOCATIONS)
    manifest = json.loads(
        (fixtures_directory / "manifest.json").read_text(encoding="utf-8")
    )
    fixtures = manifest["fixtures"]

    warmup_path = fixtures_directory / fixtures[0]["file"]
    for _ in range(warmups):
        transcriber.transcribe(warmup_path)

    results: list[dict[str, Any]] = []
    all_inference_seconds: list[float] = []
    all_real_time_factors: list[float] = []

    for fixture in fixtures:
        fixture_path = fixtures_directory / fixture["file"]
        transcriptions = [transcriber.transcribe(fixture_path) for _ in range(runs)]
        inference_seconds = [item.inference_seconds for item in transcriptions]
        transcript = transcriptions[-1].text
        audio_seconds = transcriptions[-1].duration_seconds
        real_time_factors = [timing / audio_seconds for timing in inference_seconds]
        incident = extractor.extract(transcript)
        field_results = {
            field: getattr(incident, field) == expected
            for field, expected in fixture["expected"].items()
        }
        all_inference_seconds.extend(inference_seconds)
        all_real_time_factors.extend(real_time_factors)
        results.append(
            {
                "file": fixture["file"],
                "variant": fixture["variant"],
                "transcript": transcript,
                "distinct_transcript_count": len(
                    {item.text for item in transcriptions}
                ),
                "word_error_rate": word_error_rate(
                    fixture["transcript"], transcript
                ),
                "inference_seconds": inference_seconds,
                "median_inference_seconds": round(median(inference_seconds), 4),
                "p95_inference_seconds": round(
                    percentile(inference_seconds, 0.95), 4
                ),
                "audio_seconds": audio_seconds,
                "median_real_time_factor": round(median(real_time_factors), 4),
                "field_results": field_results,
            }
        )

    field_checks = [
        passed
        for result in results
        for passed in result["field_results"].values()
    ]
    model_bytes = model_path.stat().st_size
    return {
        "runtime": {
            "label": label,
            "architecture": platform.machine() or "unknown",
            "processor": platform.processor() or "unknown",
            "model": model_path.name,
            "model_bytes": model_bytes,
            "model_mib": round(model_bytes / (1024 * 1024), 2),
            "model_sha256": sha256(model_path),
            "binary": binary_path.name,
            "engine": "whisper.cpp",
            "threads": threads,
            "runs": runs,
            "warmups": warmups,
            "commit": os.getenv("GITHUB_SHA", "local"),
        },
        "summary": {
            "fixture_count": len(results),
            "sample_count": len(all_inference_seconds),
            "median_inference_seconds": round(median(all_inference_seconds), 4),
            "p95_inference_seconds": round(
                percentile(all_inference_seconds, 0.95), 4
            ),
            "median_real_time_factor": round(
                median(all_real_time_factors), 4
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
    report = benchmark(
        arguments.fixtures,
        binary_path=arguments.binary or discover_binary(),
        model_path=arguments.model,
        label=arguments.label,
        threads=arguments.threads,
        runs=arguments.runs,
        warmups=arguments.warmups,
    )
    serialized = json.dumps(report, indent=2) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")

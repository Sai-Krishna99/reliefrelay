from __future__ import annotations

import argparse
import hashlib
import json
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from reliefrelay.audio_fixtures import PROFILES, make_radio_clip, write_pcm16_wav


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    voice: str
    speed: float
    transcript: str
    expected: dict[str, Any]


SCENARIOS = (
    Scenario(
        scenario_id="riverside-flood",
        voice="af_sarah",
        speed=1.03,
        transcript=(
            "Unit 12 reporting from Riverside Shelter. We have rising flood "
            "water and twelve people need evacuation. Send a rescue team "
            "immediately."
        ),
        expected={
            "location": "Riverside Shelter",
            "incident_type": "flood",
            "severity": "critical",
            "people_affected": 12,
            "requested_resource": "rescue team",
        },
    ),
    Scenario(
        scenario_id="north-clinic-fire",
        voice="am_michael",
        speed=0.98,
        transcript=(
            "Medic 4 reporting from North Clinic. Fire in the east wing. "
            "Two patients trapped. Send a rescue team immediately."
        ),
        expected={
            "location": "North Clinic",
            "incident_type": "fire",
            "severity": "critical",
            "people_affected": 2,
            "requested_resource": "rescue team",
        },
    ),
    Scenario(
        scenario_id="harbor-school-medical",
        voice="af_nicole",
        speed=1.05,
        transcript=(
            "Team 7 reporting from Harbor School. Three people injured and "
            "conditions worsening. Send a medical team."
        ),
        expected={
            "location": "Harbor School",
            "incident_type": "medical",
            "severity": "high",
            "people_affected": 3,
            "requested_resource": "medical team",
        },
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate ReliefRelay audio fixtures")
    parser.add_argument(
        "--model-dir", type=Path, default=Path("models/tts"), help="Kokoro assets"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("src/reliefrelay/static/audio"),
        help="Fixture output directory",
    )
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav_file:
        return wav_file.getnframes() / wav_file.getframerate()


def generate(model_dir: Path, output_dir: Path) -> None:
    from kokoro_onnx import Kokoro

    model_path = model_dir / "kokoro-v1.0.int8.onnx"
    voices_path = model_dir / "voices-v1.0.bin"
    missing = [path for path in (model_path, voices_path) if not path.exists()]
    if missing:
        missing_list = ", ".join(str(path) for path in missing)
        raise SystemExit(f"Missing Kokoro assets: {missing_list}")

    synthesizer = Kokoro(str(model_path), str(voices_path))
    output_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []

    for scenario_index, scenario in enumerate(SCENARIOS):
        samples, sample_rate = synthesizer.create(
            scenario.transcript,
            voice=scenario.voice,
            speed=scenario.speed,
            lang="en-us",
        )
        for profile_index, profile in enumerate(PROFILES.values()):
            filename = f"{scenario.scenario_id}-{profile.name}.wav"
            path = output_dir / filename
            clip = make_radio_clip(
                samples,
                sample_rate,
                profile,
                seed=10_000 + scenario_index * 100 + profile_index,
            )
            write_pcm16_wav(path, clip, 16_000)
            entries.append(
                {
                    "file": filename,
                    "scenario_id": scenario.scenario_id,
                    "variant": profile.name,
                    "voice": scenario.voice,
                    "speed": scenario.speed,
                    "transcript": scenario.transcript,
                    "expected": scenario.expected,
                    "sample_rate_hz": 16_000,
                    "duration_seconds": round(wav_duration(path), 3),
                    "sha256": file_sha256(path),
                    "processing": asdict(profile),
                }
            )

    manifest = {
        "schema_version": 1,
        "description": "Synthetic emergency-radio benchmark; no real events or people.",
        "generator": "scripts/generate_demo_audio.py",
        "model": {
            "name": "Kokoro-82M v1.0 int8",
            "license": "Apache-2.0",
            "source": "https://huggingface.co/hexgrad/Kokoro-82M",
            "onnx_runner": "kokoro-onnx 0.5.0",
            "onnx_runner_license": "MIT",
            "onnx_runner_source": "https://github.com/thewh1teagle/kokoro-onnx",
            "model_file_sha256": file_sha256(model_path),
            "voices_file_sha256": file_sha256(voices_path),
        },
        "fixtures": entries,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(entries)} fixtures in {output_dir}")


if __name__ == "__main__":
    arguments = parse_args()
    generate(arguments.model_dir, arguments.output_dir)

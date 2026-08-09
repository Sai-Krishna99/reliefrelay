import hashlib
import json
import math
import wave
from pathlib import Path

from reliefrelay.audio_fixtures import PROFILES, make_radio_clip, write_pcm16_wav
from reliefrelay.extraction import EmergencyReportExtractor


def test_radio_processing_is_deterministic() -> None:
    source_rate = 24_000
    samples = [
        0.4 * math.sin(2 * math.pi * 440 * index / source_rate)
        for index in range(source_rate)
    ]

    first = make_radio_clip(samples, source_rate, PROFILES["radio"], seed=17)
    second = make_radio_clip(samples, source_rate, PROFILES["radio"], seed=17)

    assert first == second
    assert len(first) == 16_000
    assert max(abs(sample) for sample in first) <= 1.0


def test_pcm_writer_creates_mono_16khz_wav(tmp_path: Path) -> None:
    path = tmp_path / "fixture.wav"

    write_pcm16_wav(path, [0.0, 0.25, -0.25], 16_000)

    with wave.open(str(path), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 16_000
        assert wav_file.getnframes() == 3


def test_generated_audio_matches_manifest() -> None:
    audio_directory = Path("src/reliefrelay/static/audio")
    manifest_path = audio_directory / "manifest.json"

    assert manifest_path.exists(), "Run scripts/generate_demo_audio.py"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert len(manifest["fixtures"]) == 9
    extractor = EmergencyReportExtractor()

    for fixture in manifest["fixtures"]:
        path = audio_directory / fixture["file"]
        assert path.exists()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == fixture["sha256"]
        with wave.open(str(path), "rb") as wav_file:
            assert wav_file.getnchannels() == 1
            assert wav_file.getframerate() == fixture["sample_rate_hz"]
            duration = wav_file.getnframes() / wav_file.getframerate()
        assert round(duration, 3) == fixture["duration_seconds"]
        incident = extractor.extract(fixture["transcript"])
        for field, expected_value in fixture["expected"].items():
            assert getattr(incident, field) == expected_value

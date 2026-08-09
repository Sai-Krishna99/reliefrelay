from __future__ import annotations

import math
import random
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class RadioProfile:
    name: str
    noise_level: float
    dropout_count: int
    band_limited: bool


PROFILES = {
    "clear": RadioProfile("clear", 0.001, 0, False),
    "radio": RadioProfile("radio", 0.016, 1, True),
    "severe": RadioProfile("severe", 0.032, 3, True),
}


def _resample(
    samples: list[float], source_rate: int, target_rate: int
) -> list[float]:
    if source_rate == target_rate:
        return samples.copy()
    target_length = round(len(samples) * target_rate / source_rate)
    if target_length < 2 or len(samples) < 2:
        return samples.copy()

    scale = (len(samples) - 1) / (target_length - 1)
    result: list[float] = []
    for target_index in range(target_length):
        source_position = target_index * scale
        left_index = int(source_position)
        right_index = min(left_index + 1, len(samples) - 1)
        fraction = source_position - left_index
        result.append(
            samples[left_index] * (1 - fraction)
            + samples[right_index] * fraction
        )
    return result


def _high_pass(samples: list[float], sample_rate: int, cutoff: float) -> list[float]:
    time_step = 1 / sample_rate
    resistance_capacitance = 1 / (2 * math.pi * cutoff)
    alpha = resistance_capacitance / (resistance_capacitance + time_step)
    filtered = [0.0] * len(samples)
    previous_input = 0.0
    previous_output = 0.0
    for index, sample in enumerate(samples):
        output = alpha * (previous_output + sample - previous_input)
        filtered[index] = output
        previous_input = sample
        previous_output = output
    return filtered


def _low_pass(samples: list[float], sample_rate: int, cutoff: float) -> list[float]:
    time_step = 1 / sample_rate
    resistance_capacitance = 1 / (2 * math.pi * cutoff)
    alpha = time_step / (resistance_capacitance + time_step)
    filtered = [0.0] * len(samples)
    output = 0.0
    for index, sample in enumerate(samples):
        output += alpha * (sample - output)
        filtered[index] = output
    return filtered


def make_radio_clip(
    samples: Iterable[float],
    source_rate: int,
    profile: RadioProfile,
    seed: int,
    target_rate: int = 16_000,
) -> list[float]:
    processed = _resample([float(sample) for sample in samples], source_rate, target_rate)
    if profile.band_limited:
        processed = _high_pass(processed, target_rate, 300)
        processed = _low_pass(processed, target_rate, 3_400)

    random_source = random.Random(seed)
    processed = [
        sample + random_source.gauss(0, profile.noise_level)
        for sample in processed
    ]

    minimum_start = int(target_rate * 0.5)
    maximum_start = max(minimum_start, len(processed) - int(target_rate * 0.4))
    for _ in range(profile.dropout_count):
        start = random_source.randint(minimum_start, maximum_start)
        length = random_source.randint(
            int(target_rate * 0.035), int(target_rate * 0.09)
        )
        for index in range(start, min(start + length, len(processed))):
            processed[index] *= 0.12

    peak = max((abs(sample) for sample in processed), default=1.0)
    normalization = 0.92 / peak if peak > 0.92 else 1.0
    return [max(-1.0, min(1.0, sample * normalization)) for sample in processed]


def write_pcm16_wav(path: Path, samples: Iterable[float], sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = array(
        "h",
        (
            round(max(-1.0, min(1.0, sample)) * 32_767)
            for sample in samples
        ),
    )
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())

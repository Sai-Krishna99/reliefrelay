# Native Arm64 optimization evidence

This directory is a self-contained evidence bundle for ReliefRelay's
full-precision versus Q5_1 Whisper Tiny English comparison.

![ReliefRelay Arm64 optimization results](../images/arm64-optimization.png)

## Result

| Apple M4 Arm64, 6 threads | Full precision | Q5_1 | Change |
| --- | ---: | ---: | ---: |
| Model size | 74.10 MiB | 30.68 MiB | 58.60% smaller |
| Median inference | 0.273 s | 0.273 s | unchanged |
| P95 inference | 0.307 s | 0.302 s | 1.63% lower |
| Mean WER | 11.23% | 8.79% | 2.44 pp lower |
| Structured-field accuracy | 97.78% | 100.00% | 2.22 pp higher |

The comparison includes two warmups and seven measured runs for each of nine
fixtures under both models. That is 126 measured native Arm64 inferences. Both
models use the same binary, thread count, corpus, and measurement process.

Q5_1's primary optimization win is footprint: it removes 43.42 MiB, or 58.6%,
from the on-device model while holding latency flat. Lower WER and higher task
accuracy were observed on this corpus, but are not claimed as universal model
quality improvements.

## Files

- `arm64-runtime.json`: safe hardware and software environment metadata.
- `arm64-quantization.json`: input/output hashes, sizes, version, and
  quantization duration.
- `arm64-baseline.json`: every full-precision transcript and timing.
- `arm64-optimized.json`: every Q5_1 transcript and timing.
- `arm64-comparison.json`: calculated metrics and each quality-guard decision.
- `arm64-comparison.md`: human-readable summary.

## Reproduce

```bash
uv sync --locked --dev
uv run python scripts/setup_whisper_runtime.py \
  --comparison --metadata-output artifacts/quantization.json
uv run python scripts/runtime_probe.py \
  --require-arm64 --output artifacts/runtime.json
uv run python scripts/benchmark_audio.py \
  --model models/whisper/ggml-tiny.en.bin \
  --label full-precision --threads 6 --runs 7 --warmups 2 \
  --output artifacts/baseline.json
uv run python scripts/benchmark_audio.py \
  --model models/whisper/ggml-tiny.en-q5_1-reliefrelay.bin \
  --label q5_1-reliefrelay --threads 6 --runs 7 --warmups 2 \
  --output artifacts/optimized.json
uv run python scripts/compare_benchmarks.py \
  artifacts/baseline.json artifacts/optimized.json \
  --quantization artifacts/quantization.json \
  --json-output artifacts/comparison.json \
  --markdown-output artifacts/comparison.md
```

## Quality guard

The comparison fails unless:

- architecture, threads, run counts, warmups, binary, and corpus match;
- quantization input/output hashes match the benchmarked models;
- WER regression is at most 2 percentage points;
- absolute optimized WER is at most 20%;
- structured-field accuracy is at least 95% and does not regress;
- the optimized model is smaller;
- median latency regression is at most 5%; and
- p95 latency regression is at most 10%.

## Corpus disclosure

The nine WAVs are deterministic synthetic fixtures: three emergency scenarios,
three voices, and clear/radio/severe signal profiles. Audio hashes, exact source
sentences, expected fields, voice provenance, and signal transformations are in
[`../../src/reliefrelay/static/audio/manifest.json`](../../src/reliefrelay/static/audio/manifest.json).
No real person or incident is represented.

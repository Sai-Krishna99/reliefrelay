# ReliefRelay judge guide

**Track:** Physical AI  
**Evaluation time:** about two minutes  
**Target:** nearby Arm64 edge compute receiving real-world audio and producing
reviewed alert and dispatch decisions

## The 20-second version

ReliefRelay turns degraded emergency-radio audio into structured incidents
without sending operational audio to a cloud AI API. A Q5_1 Whisper model runs
through `whisper.cpp` on Arm64, a safety-aware extractor recovers actionable
fields, and a human confirms the result before acknowledgement or dispatch.
Every source report and operator correction is retained in SQLite.

The submitted optimization makes the model **58.6% smaller** while preserving
median inference latency, slightly improving p95 latency, lowering WER from
11.23% to 8.79%, and increasing structured-field accuracy from 97.78% to 100%
on the committed native Arm64 benchmark.

## Fastest evaluation path

```bash
uv sync --locked --dev
uv run pytest -q -p no:cacheprovider
uv run python scripts/setup_whisper_runtime.py
uv run uvicorn reliefrelay.api:app --app-dir src --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`, choose **Severe**, and select **Transcribe +
Review Report**. The transcript, measured inference time, extracted fields, and
mandatory review form appear together. Correct or confirm the draft, assign a
team, and open the incident to see original reports and audit events.

Runtime setup is checksum-pinned. If downloading model assets is not desirable,
all non-inference behavior can be evaluated with the 35-test suite and the
committed benchmark reports.

## Optimization evidence

| Evidence | Location |
| --- | --- |
| Human-readable comparison | [`benchmarks/arm64-comparison.md`](benchmarks/arm64-comparison.md) |
| Comparison and quality guard | [`benchmarks/arm64-comparison.json`](benchmarks/arm64-comparison.json) |
| Full-precision raw results | [`benchmarks/arm64-baseline.json`](benchmarks/arm64-baseline.json) |
| Q5_1 raw results | [`benchmarks/arm64-optimized.json`](benchmarks/arm64-optimized.json) |
| Model hashes and provenance | [`benchmarks/arm64-quantization.json`](benchmarks/arm64-quantization.json) |
| Native hardware manifest | [`benchmarks/arm64-runtime.json`](benchmarks/arm64-runtime.json) |
| Native Linux Arm CI | [`.github/workflows/arm64-validate.yml`](../.github/workflows/arm64-validate.yml) |

## Rubric map

### Technological implementation — 40 points

- Real local speech inference on Arm64 through pinned `whisper.cpp` v1.9.2.
- Reproducible Q5_1 generation from a SHA-256-verified baseline.
- Native Arm CPU/runtime setup on Ubuntu Arm64 and macOS Arm64.
- Measured latency, p95, real-time factor, WER, model size, and task accuracy.
- CI fails on provenance mismatch, environment mismatch, excessive WER,
  insufficient task accuracy, model-size failure, or latency regression.
- Production path includes bounded inference, timeouts, WAV validation,
  persistent data, report-level review, audit history, and optional API auth.

### User/developer experience — 15 points

- One setup command and one server command.
- WAV upload, browser microphone capture, included radio fixtures, editable
  review form, incident workflow, and responsive dashboard.
- Locked dependencies, Docker/Compose packaging, configuration template, and
  operations guide.

### Potential impact — 20 points

- Addresses field environments where connectivity, privacy, and compute are
  constrained.
- Reusable runtime provisioner, deterministic audio degradation pipeline,
  benchmark harness, comparison guard, and Arm64 CI workflow.
- Human review is part of the design rather than an afterthought for a
  safety-sensitive application.

### WOW factor — 25 points

- A severe, distorted radio clip becomes an actionable incident in roughly a
  quarter-second of local inference on the measured Apple M4 device.
- The live dashboard shows the entire physical-AI loop: sensor input, local AI,
  extraction, operator confirmation, prioritization, assignment, and audit.
- The optimization is visible, reproducible, and honest about its tradeoffs.

## Scope and limitations

This is decision support, not autonomous emergency dispatch. The evaluation
corpus contains nine deterministic synthetic clips representing three semantic
scenarios and three signal conditions. It demonstrates reproducibility, not
population-level speech accuracy. A field pilot would require a larger,
consented, multilingual corpus and organizational security review.

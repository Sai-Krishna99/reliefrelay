# ReliefRelay three-minute demo

Target length: **2:35–2:50**. Record the actual Arm device and dashboard at
1440p or 1080p. Do not use copyrighted music. Upload publicly to YouTube or
Vimeo and verify playback in a signed-out browser.

## 0:00–0:15 — Hook

**Screen:** dashboard overview, system status `OPERATIONAL`, Arm64 visible.

**Narration:**

> When a field radio report arrives during a flood or fire, connectivity and
> audio quality may both be failing. ReliefRelay turns that noisy audio into a
> reviewed response incident locally on Arm—without sending it to a cloud AI.

## 0:15–0:35 — Physical AI loop

**Screen:** point to microphone/upload input, pipeline, incident queue.

**Narration:**

> Audio is the real-world sensor input. A quantized Whisper model runs through
> whisper.cpp on this Arm64 device, extracts operational fields, and produces a
> priority decision. Because this is safety-sensitive, AI output is a draft;
> an operator remains responsible for action.

## 0:35–1:20 — Severe audio demo

**Screen:** choose `Harbor School Medical`, select `Severe`, play two seconds,
then select `Transcribe + Review Report`.

**Narration while it runs:**

> This is the severe condition: band-limited radio audio, added noise, and
> deterministic dropouts. The WAV stays on this ReliefRelay server.

**Screen:** show measured inference, transcript, confidence, warnings, and
editable fields. Correct a field if the transcript is degraded, assign
`Medical Team 7`, then confirm.

**Narration:**

> In roughly a quarter second on the measured M4, ReliefRelay recovers the
> school, medical incident, severity, affected people, and requested team. I can
> correct uncertainty, assign a responder, and only then acknowledge the event.

## 1:20–1:45 — Operational credibility

**Screen:** open incident detail, scroll report history and audit trail, change
status to `dispatched`.

**Narration:**

> The original report is never overwritten. SQLite preserves every source,
> review, assignment, and lifecycle change. A later report cannot silently
> downgrade critical severity, and resolved incidents do not absorb new events.

## 1:45–2:20 — Arm optimization proof

**Screen:** open the README native evidence table, then raw comparison JSON or
GitHub Actions workflow.

**Narration:**

> This is an optimization project, not only an Arm port. ReliefRelay generates
> Q5_1 from a checksum-verified full-precision model with pinned whisper.cpp
> 1.9.2. Across 126 native Arm64 inferences, model size falls 58.6%, from 74.1
> to 30.68 MiB. Median latency stays at 0.273 seconds, p95 improves slightly,
> and structured-field accuracy reaches 100% on the submitted corpus. Every raw
> timing, transcript, hash, and guard decision is committed and reproducible.

## 2:20–2:45 — Close

**Screen:** return to populated operations dashboard and map.

**Narration:**

> ReliefRelay shows what optimized Physical AI on Arm can look like: small,
> fast, private, resilient, measurable, and designed around the human who must
> make the final call. When the network disappears, the response workflow does
> not have to.

## Recording checklist

- Keep the full video below three minutes.
- Show the device architecture in the live dashboard or terminal.
- Use the real severe WAV and real inference result—no mocked animation.
- Keep secrets, browser bookmarks, serial numbers, and personal notifications
  out of frame.
- Show the result table long enough to read `58.6% smaller` and `100%`.
- Add the public video URL to Devpost and `README.md` before the deadline.

# ReliefRelay operations guide

ReliefRelay is local-first decision support. An operator must review extracted
fields before acknowledgement or dispatch. It does not replace emergency call
handling procedures.

## Data and recovery

Operational state is stored in the SQLite file configured by
`RELIEFRELAY_DATABASE`. It contains incidents, every original report, and the
audit trail. Back up the database with SQLite's online backup mechanism or stop
the single application worker before copying it. Restore by replacing the file
while the application is stopped.

Run one application worker per database. SQLite WAL mode supports concurrent
browser access in that process, but multi-node operation should migrate the
store to PostgreSQL first.

## Access control

Keep the default server bound to loopback during development. For a shared
network deployment:

1. Set `RELIEFRELAY_API_TOKEN` to a long random secret.
2. Put the service behind a TLS reverse proxy or private zero-trust gateway.
3. Restrict network access to response-team devices.
4. Rotate the token and restart the service if it may have been exposed.

The browser asks for the token on the first protected API request and retains it
only in that tab's session storage. Health is intentionally unauthenticated for
local supervision.

## Runtime protection

`RELIEFRELAY_MAX_CONCURRENT_INFERENCE` bounds CPU-heavy Whisper processes.
Additional requests wait up to `RELIEFRELAY_QUEUE_TIMEOUT_SECONDS`, then receive
a retryable 503 response. Each transcription is terminated after
`RELIEFRELAY_WHISPER_TIMEOUT_SECONDS`.

Monitor at minimum:

- `/api/health` readiness and process restarts;
- disk space for the SQLite database;
- 422 transcription failures, 503 overload responses, and 504 timeouts;
- incident backlog in `needs_review`;
- database backup completion.

## Incident workflow

New machine-extracted reports enter `needs_review`. An operator corrects the
transcript and fields, then acknowledges or assigns the incident. Supported
states are:

`needs_review → acknowledged → assigned → dispatched → resolved`

`rejected` is for false or non-actionable reports. A new report can return an
open incident to review if it raises the known severity. Resolved and rejected
incidents never absorb later reports.

## Container deployment

The included image does not download model assets. Provision the Linux runtime
and model on the target host, then mount `.local/whisper` and `models` using the
included Compose file. Runtime binaries provisioned on macOS or Windows cannot
be used inside the Linux container.

```bash
docker compose up --build -d
docker compose logs -f reliefrelay
```

The Compose port is loopback-only. Add a secured reverse proxy for remote use.

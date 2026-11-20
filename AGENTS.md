# Team Astra Fly engineering instructions

Read [the implementation blueprint](IMPLEMENTATION_BLUEPRINT.md), [the v1 contracts](docs/CONTRACTS.md), and [the milestone status](docs/STATUS.md) before changing the project. Apply these instructions throughout the workspace.

## MVP architecture

- Deliver one licensed aerial MP4 through OpenCV decode, actual YOLO26n detection, anonymous ByteTrack tracking, explainable rules with source-aware geospatial context, durable incidents, a React dashboard, operator review, and an append-only audit trail.
- Use Python 3.11, FastAPI, Pydantic, SQLAlchemy, Alembic, and SQLite. Use React, Vite, TypeScript, and MapLibre GL JS. Record dependency versions and use reproducible installs on the supported platforms. See [technical decisions and installation risks](docs/DECISIONS.md).
- Use a single Uvicorn worker for the demo without auto-reload. One controlled video worker owns the capture, model, and tracker outside the API event loop. Allow one active replay in the process. Reset tracking and rule state at each run boundary. Bound the latest-frame store and subscriber queues.
- Keep the video reader, vision adapter, projection, rules, storage, API, and UI independently testable. Keep vendor types inside the adapter. Use the installed Ultralytics public API with ByteTrack and persist tracker state only across sequential frames of the same run.
- Persist incidents and audit rows before notifying clients. Enforce uniqueness and review transitions in storage transactions. Serve annotated MJPEG from the latest frame, deliver small WebSocket notifications, and reconcile state against REST after reconnect.
- Scope the MVP to prerecorded replay, the crowd and restricted-zone rules, a bounded evidence thumbnail, and local review. Defer RTSP/MediaMTX/WebRTC, PostGIS, Redis, flight or telemetry integration, face verification, evidence clips, and richer production controls until after the MVP gate and explicit task authorization.

## Correctness, privacy, and licensing

- Real replay requires actual inference. Missing, incompatible, or failed weights, input, or tracker must produce an explicit error. Use synthetic detectors only in isolated tests. Label recorded fallback material as a recording of a prior run and label prerecorded source video as replay.
- Keep track IDs anonymous and scoped to one run. Exclude automatic face identification, face embeddings, watchlists, cross-source identity linkage, covert monitoring, and automated enforcement from the MVP.
- Publish world points only from validated fixed-scene ground-plane calibration. Keep image ROIs in pixels. Never infer a detected person's GPS from drone GPS. Use `null` when a location or uncertainty estimate is unavailable. Serialize geographic coordinates as longitude, latitude.
- Start every incident in `pending` with run and source provenance, footage time, and causal rule measurements. Require an authenticated local operator to acknowledge or dismiss with a reason. Derive reviewer identity server-side and persist the decision and audit row atomically. Candidate alerts carry severity `review`.
- Keep the demo on loopback with explicit allowed UI origins and token protection for writes. Keep credentials, private paths, raw footage, and personal or biometric data out of Git and routine logs. Keep per-frame observations transient. Retain bounded incident evidence privately under source permissions and a documented demo retention policy.
- Use footage with documented permission for processing, display, and any evidence or submission distribution. Record the source owner, origin, license or permission, attribution, permitted uses, and SHA-256. Keep restricted assets out of the repository. Track library and basemap terms independently.
- Record the Ultralytics package version, official YOLO26n weights origin and SHA-256, and the shipped ByteTrack configuration. Ultralytics identifies its toolkit and pretrained weights as AGPL-3.0 by default and offers Enterprise terms. Confirm the team's license path, corresponding-source and notice obligations, and asset redistribution permissions before sharing the integrated demo. [Ultralytics licensing](https://www.ultralytics.com/license)

## Required workflow for every subsequent task

1. Inspect the existing code, applicable instructions, contracts, and status before editing.
2. Make the smallest necessary change. Preserve supported callers and persisted data. Coordinate any breaking contract change before altering the backend and frontend.
3. Run the relevant checks. Use deterministic offline fixtures for unit/API tests. Use real, permissioned media and approved weights for real-inference verification. Test success, relevant failure paths, and retry or concurrency behavior where the change affects them.
4. Record exact commands and pass, fail, or skip results in [docs/STATUS.md](docs/STATUS.md). Mark each affected milestone and list untested functionality and blockers. Include the same results and gaps in the handoff.
5. Report benchmark results only when measured. Record hardware, runtime, model artifact, input, units, and measurement boundaries. Distinguish processing FPS from playback FPS. Use `not measured` for missing results and require labeled ground truth for accuracy claims.

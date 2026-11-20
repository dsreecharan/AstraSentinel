# Astra Fly — Copy/Paste Prompts for ChatGPT Codex

**Use these prompts in order, in a repository/workspace that Codex can edit.** Do not send all prompts at once. Start with Prompt 0, verify completion, and issue the next. They are written for a one- or two-person hackathon team on Windows/WSL or Linux, with a Python API and TypeScript frontend. The full engineering specification is `IMPLEMENTATION_BLUEPRINT.md`; include that file in the repository first or paste it into Codex's context.

## Prompt 0 — Architect, freeze scope, and create AGENTS.md

```text
You are the lead software engineer for Team Astra Fly's CipherCop 2026 Track 1 project. Read IMPLEMENTATION_BLUEPRINT.md in full and inspect the current repository before making changes. Build a real, reproducible MVP: licensed drone/aerial MP4 -> actual person/vehicle detection -> anonymous ByteTrack IDs -> deterministic crowd/intrusion candidate alerts -> source-aware map -> operator review -> persistent audit. The precise product and engineering scope are in the blueprint; do not expand it without marking scope as optional.

Create AGENTS.md with NON-NEGOTIABLE project instructions:
1. Python 3.11 / FastAPI / SQLAlchemy + Alembic / SQLite first; React + Vite + TypeScript + MapLibre; OpenCV; YOLO26n + ByteTrack through current Ultralytics public API. Use dependency versions compatible with actual environment and record them. Don't hardcode a CUDA version.
2. The real model is NEVER secretly replaced by mocks. Fake detector only in unit tests or explicitly labelled simulation mode. If weights cannot load, show a clear startup/configuration failure.
3. Avoid building Kafka, Redis, PostGIS, MediaMTX, PX4, physical drone integration or general AI action recognition until the vertical slice passes tests. Keep adapters for future phases.
4. No real-time public face identification, covert surveillance, 1:N watchlist, or automated enforcement. Facial comparison is optional, opt-in, 1:1, and human-reviewed only.
5. Track IDs are anonymous and scoped to one processing run; no cross-camera linkage. Never copy drone GPS to person GPS. Use map coordinates only with validated geolocation. Uncalibrated video => null world coordinates and a clear label.
6. Every incident has source_id, run_id, video_time_ms, rule measurements, provenance, explicit pending review state and timestamped audit trail.
7. Use small testable modules, typed contracts, bounded queues, error handling, security for mutating routes, and no giant monolithic OpenCV script.
8. In each coding task: inspect existing files, identify exact changes, implement, run available commands/tests, report results and blockers, and DO NOT claim tests passed if they were not run.
9. No credentials or third-party datasets in Git without permission. Record source and model licenses. Use legal image/video footage and volunteer/synthetic data only.
10. Maintain a milestone checklist at docs/STATUS.md with completed, tested, broken and next items; no false implementation claims.

Then create docs/DECISIONS.md explaining why v1 uses MJPEG+SQLite instead of prematurely adding MediaMTX+PostGIS+Redis. Create docs/CONTRACTS.md with the schema and route names from the blueprint (frozen identifiers). Create a phased task list with priorities P0/P1/P2. Do NOT implement unrelated features in this step.

Output: files changed, exact contract decisions, commands run, tests run, and next prompt readiness. Commit with message 'docs: freeze MVP architecture and agent rules' if Git is configured; otherwise show the exact suggested command.
```

## Prompt 1 — Bootstrap a runnable monorepo

```text
Read AGENTS.md, docs/CONTRACTS.md, and IMPLEMENTATION_BLUEPRINT.md. Create the minimal runnable monorepo, not a pretend finished application.

Backend:
- Python 3.11-compatible pyproject.toml with FastAPI, Uvicorn, Pydantic, SQLAlchemy, Alembic, httpx, pytest, OpenCV, plus optional Ultralytics extras so initial unit tests work without model weights.
- app.main exposing GET /api/v1/health returning {status:'ok', version:'0.1.0', inference_status:'not_started'}.
- Pydantic contract definitions from docs/CONTRACTS.md for Source, Run, TrackObservation, Incident, Geofence, Calibration and AuditEntry, preserving video_time_ms and geo_status semantics.
- README with Windows PowerShell and Linux/WSL commands, environment variables, no implicit network access, precise local host/port instructions.
- Backend test smoke test using FastAPI TestClient; pytest config.

Frontend:
- React + Vite + TypeScript shell with an app title 'Astra Fly — Public Safety Command Center' and 3 responsive areas: Video, Map, Incidents. Use honest empty states, no fake counters or stock alerts. Create typed API client using VITE_API_BASE_URL.
- npm lint/typecheck/build scripts (or equivalent package scripts). Configure CORS for an explicitly allowlisted localhost frontend URL.

Repo root:
- .env.example, .gitignore, data/README.md with source-provenance template, docs/STATUS.md, test fixtures directories.
- Do not introduce Docker Compose dependencies yet, but document how to add them later.

Acceptance criteria: backend starts, /health works, frontend builds, no model download required for basic tests, tests pass. Run pytest, npm typecheck and npm build if runtime is installed; report exact outcomes. Do not claim a demo already works.
```

## Prompt 2 — API, persistent incidents, review and audit

```text
Implement the backend service layer now, following AGENTS.md and frozen contracts. Use SQLAlchemy + SQLite with Alembic migration; avoid Redis or PostGIS for this phase.

Create tables for sources, runs, incidents, geofences, calibrations, append-only audit entries. Include foreign keys, uniqueness constraints/idempotency keys, created_at timestamps, and indexes. Raw video and face embeddings must not be persisted by default. Provide a seed command for ONE source record pointing to a local licensed video file path from env; don't seed fabricated emergency incidents.

Implement:
GET /api/v1/sources
GET /api/v1/incidents with status filter, pagination, ordering
GET /api/v1/incidents/{id}
POST /api/v1/incidents/{id}/review with acknowledged|dismissed, nonempty reason and operator identity
GET /api/v1/incidents/{id}/audit
GET/POST /api/v1/geofences with validation of GeoJSON polygon and space_type=('world'|'image')
WS /ws/events with a clear subscription event format and proper disconnect handling.

Use a service function publish_incident(input) that persists first, then broadcasts to clients; repeated idempotency key yields the original incident rather than duplicating. WebSocket broadcast must be safe from the future background video thread: use a bounded async queue or thread-safe event-loop scheduling; avoid calling async objects directly from a plain worker thread.

Protect incident review and other mutating endpoints with configurable local demo operator credentials/token; provide sample local config without committing secrets. Use simple role checks appropriate for localhost demo; document this is not production authentication. CORS allowlist only. Avoid exposing arbitrary filesystem paths.

Implement focused tests: invalid review transitions, duplicate incident idempotency, persistence across app restart / new SQLAlchemy sessions, audit created only on successful review, invalid polygon rejected, unauthorized writes rejected, REST returns identical incidents after WebSocket reconnect.

Provide an explicit test helper creating a synthetic incident fixture, labelled TEST DATA; it must not silently seed the normal UI. Run migrations, pytest, and report results.
```

## Prompt 3 — Real MP4 video inference + anonymous tracking

```text
Build the actual video-processing engine. Read AGENTS.md and the relevant interfaces in docs/CONTRACTS.md. Do NOT simulate detections in production mode.

Create:
- VideoSource/OpenCVVideoSource that validates a source is inside an allowlisted data directory, opens the MP4, exposes frame_index, source_fps and video_time_ms (derive from file timestamps/frame position; document precision). Handle EOS and corrupted/unavailable source.
- VisionEngine protocol returning normalized anonymous per-run detections/tracks (class in person/car/vehicle categories, bbox_xyxy, confidence, run-scoped track_id) independent of vendor-specific result types.
- UltralyticsAdapter using an installed, verified model interface. Default model yolo26n.pt, but verify file availability or supported auto-download behavior before claiming it is loaded. Use persistent ByteTrack state across sequential frames (Ultralytics model.track with persist=True and ByteTrack config, or a separately validated ByteTrack adapter). Do not reset the tracker on every frame.
- VideoWorker with start/stop/status, only one active worker/source, a single model instance in one service process, bounded latest-frame JPEG store and bounded observation queue. The worker must stop on demand and handle EOS cleanly. Inference runs outside the API event loop. Never instantiate the model inside each request or run Uvicorn multiple workers for this MVP.
- Annotated MJPEG StreamingResponse endpoint GET /api/v1/stream/annotated.mjpg. Use latest-frame semantics to avoid unbounded memory. Put 'REPLAY SOURCE' overlay on prerecorded feed.
- Start/stop/status APIs per contracts; use clear model-load/codec errors rather than reverting silently to synthetic detections.

Add deterministic FakeVisionEngine and synthetic frames ONLY for tests. Integration test with a tiny generated test video to verify real frame reading, state transitions, timecodes and clean shutdown; the real pretrained inference smoke test should be a separate optional test that skips with clear reason if weights are absent.

Run tests. If dependencies conflict on Windows or CPU-only hardware, produce a documented supported workaround and preserve the running unit-test path. Show commands that actually processed a real MP4, plus sample observed track counts if model was available; otherwise say model test blocked.
```

## Prompt 4 — Explainable event rules and geospatial correctness

```text
Implement production-path deterministic incident rules and honest geolocation. Do not claim to know an object's GPS coordinates from a pixel or from the drone location alone.

Rules:
- CrowdThresholdRule: count unique active person track IDs inside a configured region, require N consecutive qualifying frames, use count threshold and hysteresis, emit one candidate incident per crossing, and enforce an adjustable cooldown. Return causal measurements, not fabricated probability.
- ZoneEntryRule: for each anonymous track, detect outside->inside transition into a polygon, confirm over configurable frames, dedupe by run_id + track_id + zone_id + entry transition, cooldown and reset on source restart. Don't trigger one new incident every frame.
- Ensure rule state is scoped to run and can be unit-tested with manufactured observation sequences. Return event candidates for IncidentService to persist.

Geospatial:
- Pixel ROI mode for uncalibrated footage: image coordinates, `geo_status='image_roi_only'`, `location=null`. UI must not create a map marker for those incidents.
- Fixed-scene georeferencing mode only: 4+ noncollinear correspondences (pixel↔ground/map), OpenCV homography fitting with validation and reprojection error. Pixel bottom-center projects onto ground plane when scene is stable. Reject missing/bad calibration, invalid polygons, mismatched frame resolution. GeoJSON output uses [longitude, latitude], SRID 4326; validate point bounds. `horizontal_error_m` remains null without measured calibration error bounds.
- If drone telemetry exists later, never assign drone's own GPS to each tracked person. Moving-camera footage should be marked unavailable until dynamic camera pose/intrinsics projection is implemented.

Write unit tests for normal and borderline cases: threshold crossing, cooldown, reentry, occlusion, no geolocation, invalid homography, lon/lat ordering, and cross-run state reset. Wire rules into the real VideoWorker->IncidentService pipeline. All detections/alerts must carry source_id, run_id and video_time_ms.

Expose calibration and geofence configuration through validated file or API interfaces documented in README. Demonstrate a real source where an annotated frame triggers at least one event; if the footage doesn't contain an event, report that honestly and use the controlled scenario fixture.
```

## Prompt 5 — React command dashboard and map

```text
Implement frontend in React/Vite/TypeScript with MapLibre (no fake alert counts or static dashboard demo data). Read docs/CONTRACTS.md and use the actual backend OpenAPI schema; if endpoints are not yet finished, define types with exact contract names and show honest disconnected/empty/error UI rather than invented incidents.

Build:
- Dark professional incident-command dashboard with clear labeling that the product is a hackathon prototype, source is REPLAY and candidates require human review.
- Header: source selector, Start/Stop buttons, status (idle/loading/running/ended/error) and source provenance. Start/Stop connect to real API actions; never label a source 'LIVE' unless it truly is RTSP/live.
- Left pane: annotated video MJPEG stream; show loading, EOS, camera unavailable and model failure states. No silent looping.
- Middle pane: MapLibre map with valid georeferenced incident points, geofences, uncertainty only if actually measured. If the source has no valid calibration, show 'Geolocation unavailable — image-space alert' without plotting arbitrary dots.
- Right pane: incident queue, severity review status, observed video_time_ms, source/run ID, rule measurements, evidence thumbnail, selected incident details, acknowledge/dismiss controls with reason dialog.
- Bottom/status pane: append-only audit timeline for selected incident; measured FPS if available; unknown metrics should show N/A.
- Typed API client, WebSocket subscription and reconnect with backoff; refetch GET /incidents after reconnect to avoid missing durable records. Do not assume WebSocket itself guarantees delivery.
- Keyboard accessible buttons, map status labels, responsive layout suitable for 1366x768 projector.

Add frontend unit/component tests where practical, typecheck and production build. Provide screenshots only from a real running app; if there is no running backend, do not pass mocked screens as end-to-end proof.
```

## Prompt 6 — Vertical-slice integration and verification gate

```text
You are integrating the full Astra Fly MVP. Read AGENTS.md, docs/STATUS.md, and IMPLEMENTATION_BLUEPRINT.md; inspect recent changes before editing. Goal: prove one real source->detection->track->rule->persisted incident->WebSocket/REST->review->audit path.

Work end-to-end: start backend and frontend locally; use a licensed/owned MP4 from data/demo_video (or document exactly how to supply it); configure model weights; execute a real inference run; confirm annotated MJPEG frames appear; verify one rule candidate incident appears in SQLite and dashboard; review it; restart backend and confirm incident/audit still exist. If the source does not contain a rule event, use a transparently marked controlled test fixture or adjust explicit rule thresholds—never fabricate a detector result and claim it came from the model.

Implement useful missing integration pieces only. Add scripts/smoke_test.py for authenticated API and deterministic test incident flow. Add a system smoke-test runbook for real inference. Add structured error messages for missing video, unsupported codec, model weights, calibration, database and server reconnect. Implement source/worker stop cleanup and prevent duplicate workers in reload/multiworker mode.

Record actual hardware, OS, Python/Node package versions, model filename/checksum if available, processing FPS and latency with correct units. Never invent mAP or end-to-end latency. Document measured vs estimated vs unmeasured values separately.

Definition of done: repeatable demonstration on the team's machine from clean instructions; minimum smoke tests and frontend build pass; restart/reconnect works; clear screen recording and screenshots can be captured. Provide a checklist of PASS/FAIL with command output, exact commands to reproduce, and known blockers. No Phase 2 work until this is done.
```

## Prompt 7 — Benchmarks, reliability and submission package

```text
Prepare a credible hackathon submission for Astra Fly based solely on features verified as implemented. Read docs/STATUS.md and inspect code. Do not invent success screenshots, accuracy, latency, aerial ground truth, or dates.

Add scripts/benchmark.py to measure (with warm-up, batch=1, and hardware/runtime metadata): file-read FPS, video decode ms, per-frame inference ms, tracking ms, rule engine ms, processed FPS, alert-generation latency within the local pipeline, CPU/RAM, GPU/VRAM when available. Explain whether metric is measured end-to-end or component-only and whether footage was processed offline or in real-time playback. Do not report detector mAP without an annotated evaluation set.

Add regression tests for review transitions, idempotency, geo unavailable, image-space vs real geo, worker stop/EOS, API auth, stale WebSockets and replay behavior. Add optional bounded evidence thumbnail save tied to actual incident (no unnecessary long-term video retention). Provide data provenance and license table in data/README.md and architecture/limitations documentation.

Create docs/DEMO_SCRIPT.md: 3-minute operator walkthrough, steps to start a successful demo, how to demonstrate crowd threshold or restricted-zone entry, operator review and audit history, explicit replay/uncertainty labels, and an honest fallback pre-recorded screen capture of the same run.

Create docs/SUBMISSION_CHECKLIST.md covering source repo, README, dataset links/rights, slides/PDF (content outline only unless tools support rendering), hardware/benchmark table, ethical and legal limitations. Do not write 'production-ready', 'police-certified', or '100% accurate'. Ensure clean install instructions. Run all tests/builds and show exact results.
```

## Prompt 8 — After MVP only: MediaMTX + RTSP + Redis + PostGIS

```text
STOP if the documented MVP vertical slice is failing. This is Phase 2, not a reason to destabilize the submission. Begin by running the existing full test suite and recording baseline behavior.

Extend the architecture behind explicit interfaces:
1. Add MediaMTX container/config for RTSP publish and WebRTC/HLS browser playback; keep MP4 and MJPEG fallback. Document the exact codec/protocol/localhost ports and access policy. Avoid building a homegrown RTSP/WebRTC server.
2. Add Postgres+PostGIS via SQLAlchemy adapter and Alembic migrations. Preserve existing incident API semantics. Use geography/geometry correctly for 4326 and spatial indices. Include a migration path/test from SQLite demo records, or explicitly keep stores separate by profile.
3. Add Redis Streams for durable event transport between services only if split services need it. Use consumer groups, acknowledgments, idempotency, retry/dead-letter behavior; REST persistence still reconstructs UI state after disconnect.
4. Add optional PX4+Gazebo/MAVSDK telemetry adapter, with correct time sync and explicit uncertainty. Do not pretend drone GPS is object GPS; never imply flight authorization.
5. Keep docker compose profiles or feature flags so full stack can be disabled to run original MVP. Use health checks, clear secrets config, lifecycle cleanup, and a measurable benchmark comparison.

Acceptance: same existing end-to-end tests pass in MVP mode; each advanced module has its own integration test; no dependency forces a physical drone or NVIDIA GPU to start the baseline app; report actual tests and tradeoffs.
```

## Prompt 9 — Optional, separate consented 1:1 identity demonstration

```text
Build this ONLY after the core project works AND only with clear voluntary enrollment images from consenting adult team members or legally authorized synthetic data. The feature must be disabled by default, visible only after an operator enables 'Consent-based Identity Verification Demo', and cannot analyze the general drone stream or operate as a 1:N watchlist.

Create a plug-in IdentityVerifier interface and a workflow to enroll a single consented identity, upload a probe image, perform manual 1:1 comparison against that one enrollment with a legally usable model, show a similarity score plus 'human confirmation required', and delete enrollment on request. Verify both code AND pretrained-weight licensing; InsightFace code is MIT but its distributed pretrained models can have noncommercial research restrictions, so do not assume MIT applies to weights. If no appropriate licensed model or sufficient testing is available, implement the UI/API boundary in DISABLED/NOT IMPLEMENTED state rather than a fake confidence result.

Keep separate from live public-safety tracking; no personal names over detected strangers, no scraped datasets, no biometric embeddings in logs, exports or Git, no automated match/enforcement. Include operator audit, enrollment authorization, safe image upload checks, default short retention, FMR/FNMR testing approach and documentation of model thresholds and limitations. Run targeted privacy, access-control and deletion tests. Report exactly what is actual vs disabled.
```

## Prompt 10 — Iterative repair / code review template (reuse after any failed step)

```text
We have a failing Astra Fly milestone. Do not rewrite unrelated modules or claim the error is fixed without reproducing it. Read AGENTS.md, the exact previous command/output below, and the relevant modules. Identify root cause, minimal safe patch, regression test, and a reproducible verification command. Preserve all frozen API contracts, incident provenance, explicit replay mode, geolocation uncertainty and identity safeguards.

FAILED COMMAND:
<paste command>

ACTUAL OUTPUT:
<paste error logs>

EXPECTED BEHAVIOR:
<paste measurable acceptance condition>

Return: root-cause explanation, changed file list, focused diff summary, exact tests run with results, remaining risks, next action. If tests cannot run here, state the blocker and do not mark PASS.
```

## Recommended Codex operating pattern

1. Add `IMPLEMENTATION_BLUEPRINT.md` and `CODEX_PROMPTS.md` to a new local Git repo; open that repo in Codex.
2. Issue Prompt 0. Inspect contract files and `AGENTS.md`. Do not start Prompt 2 until the bootstrap from Prompt 1 works.
3. Use one prompt per branch or worktree; do not give two coding agents the same file ownership. Engineer A can run Prompt 2/3/4 sequentially; Engineer B can run Prompt 5 once contract definitions are frozen, with isolated frontend files.
4. Run the printed commands on the target machine, especially model inference: a Codex environment without NVIDIA/CUDA or model weights cannot verify hardware behavior.
5. Use Prompt 10 for repairs. Freeze MVP after Prompt 7 and only then run Prompt 8 or 9.

**Success is measured by a real reproducible inference-to-reviewed-incident event, not by the volume of generated code.**

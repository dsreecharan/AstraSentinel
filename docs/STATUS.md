# Astra Fly MVP status and implementation checklist

## Current milestone

**Prompt 8 optional profiles verified locally on Windows and WSL on 2026-11-20.** The default MVP passed the real replay and restart rehearsal before and after the changes. The separate Phase 2 branch adds RTSP browser monitoring, independent PostGIS storage, and a read-only MAVSDK simulator probe. [Phase 2 runbook](PHASE2.md) · [Submission checklist](SUBMISSION_CHECKLIST.md)

The required validation path is licensed aerial MP4 → actual inference → anonymous ByteTrack → crowd and zone rules with geospatial context → SQLite → dashboard → operator review → durable audit.

## P0 · Required MVP gates

### Gate 0 · Scope and contracts

- [x] Read the root blueprint in full and inspect the workspace.
- [x] Document project invariants, v1 interfaces, and dependency and licensing risks in [AGENTS.md](../AGENTS.md), [CONTRACTS.md](CONTRACTS.md), and [DECISIONS.md](DECISIONS.md).
- [x] Record the phased implementation and validation gates below.

### Gate 1 · Runnable foundation

- [x] Scaffold the Python 3.11 backend and React/Vite/TypeScript frontend with the minimum health and empty-state UI.
- [x] Add Pydantic contract types, OpenAPI verification, local settings/CORS, example environment values, ignored paths, dependency pins/lockfiles, and bootstrap instructions for PowerShell and Linux/WSL.
- [x] Verify FastAPI health reports `inference_status: not_started` without weights. Run in-process backend tests, `npm ci`, frontend lint/typecheck, and production build on Windows.
- [x] Initialize the source checkout and select the [AstraSentinel repository](https://github.com/dsreecharan/AstraSentinel).
- [x] Prepare one candidate aerial MP4 and record owner, source, permitted uses, attribution, and checksum. [Local validation source](../data/README.md#local-aerial-replay-validation-source)
- [ ] Resolve the intended Ultralytics licensing path for the submission.

### Gate 2 · Durable API, review, and audit

- [x] Add SQLAlchemy models, SQLite foreign keys and uniqueness constraints, and an Alembic initial migration. Provide explicit source registration by ID and keep its path private.
- [x] Add source, geofence, incident, review, and audit interfaces. Protect writes with local operator credentials and validate input against [CONTRACTS.md](CONTRACTS.md).
- [x] Persist incidents and audit entries before WebSocket notification. Verify duplicate candidates, commit failure, conflicting reviews, unauthorized writes, persistence across restart, and REST recovery after reconnect with isolated `TEST DATA`.

### Gate 3 · Real replay and tracking

- [x] Verify OpenCV decode and footage timestamps on generated MP4s. Install the locked Windows CPU vision profile and configure the verified local checkpoint for normal backend startup.
- [x] Implement the real vision adapter, single active worker, run lifecycle, run-scoped ByteTrack IDs, and bounded annotated MJPEG. Wire model and decoder errors to the API and label the stream as replay.
- [x] Verify start conflict, unavailable media and weights, invalid MP4, stop, EOF, reset, restart recovery, and stale-frame cleanup. Run the real smoke twice in one process using a temporary MP4 made from a public-domain still.
- [x] Run a rights-verified aerial validation MP4 and verify run-scoped vehicle tracks. Verify person tracking separately on the public-domain fixture.

### Gate 4 · Explainable rules and location

- [x] Implement crowd threshold and restricted-zone entry in the replay worker and persist causal values, bounded optional evidence, and stable deduplication keys. Serve retained evidence through the thumbnail endpoint.
- [x] Label image ROIs explicitly and implement fixed-scene projection bound to the verified source checksum. Test invalid geometry, mismatched resolution, coordinate order, and unavailable location. Require calibrated incident locations for future map markers.
- [x] Verify thresholds, consecutive frames, boundary/reentry, occlusion, cooldown, and run reset with deterministic tests. Confirm the annotated evidence belongs to the incident's confirmation frame.

### Gate 5 · Operator dashboard

- [x] Connect source/license display, start/stop, annotated replay, MapLibre, incident queue, evidence, map/ROI context, review with reason, and audit timeline to the v1 API.
- [x] Verify typed builds, projector/mobile layout, backend disconnect/retry, empty states, replay stop/EOF, missing source and weights, uncalibrated map behavior, WebSocket reconnect with REST resync, and terminal reviews.

### Gate 6 · Real vertical-slice acceptance

- [x] On the demo machine, start from documented setup and run the licensed MP4 with real inference. Demonstrate both rule types on the separately labeled public-domain controlled replay.
- [x] Show a pending image-space alert with retained confirmation evidence. Acknowledge it with a reason, restart the backend, reconnect the same browser, and verify the unchanged incident and audit against REST and SQLite.
- [x] Record reproducible commands, pass/fail/skip counts, measured hardware and timings, and a labeled recording of the verified run.

## P1 · Demo and submission readiness

- [x] Package reproducible smoke commands, the operator walkthrough, source and model provenance, license inventory, and verified screenshots and recording.
- [x] Record benchmark hardware, source, model, workload, measurement boundaries, and results.
- [x] Record limitations, untested behavior, and the slide/PDF content outline in the submission material.
- [ ] Confirm the distribution license, collect notices for the selected package, approve media for sharing, and assemble the final slides or PDF.

## P2 · Optional profiles

- [x] MediaMTX on an opt-in Compose profile with authenticated RTSP publishing, local WebRTC/HLS players, and an independent MVP replay path.
- [x] PostGIS on an opt-in Compose profile with separate records, spatial indices, v1 contract coverage and local transaction measurements.
- [x] Read-only MAVSDK simulator probe with clock and uncertainty tests. Native UDP reception and socket cleanup verified with a synthetic MAVLink wire fixture.
- [ ] Run a full PX4/Gazebo session. Redis Streams stay deferred until a split application producer or consumer needs durable cross-process delivery.
- [ ] Evidence clips, configurable retention and richer controls remain outside this phase.
- [ ] Treat any future opt-in 1:1 face comparison as a separately authorized, consented, human-reviewed task. Automatic mass identification and cross-camera identity linkage remain excluded.

## Validation log

| Check or command | Result |
| --- | --- |
| `Get-Content -Raw -LiteralPath 'IMPLEMENTATION_BLUEPRINT.md'` | Read all 12 sections. |
| `rg --files --hidden` and targeted recursive source/manifest/asset searches | Inspected workspace inventory. No application sources, package manifests, demo media, or weights were found. |
| `Get-FileHash` on root and nested engineering-pack copies | Matching SHA-256 hashes for all three pairs. |
| `git rev-parse --show-toplevel` | Exit 1, `fatal: not a git repository (or any of the parent directories): .git`. |
| `python --version`, `py -0p`, `python -m pip --version`, SQLite import/version probe | Python 3.11.0 (64-bit), default Windows launcher target Python 3.14, pip 26.3 for Python 3.11, SQLite 3.38.4. |
| `node --version` and `npm.cmd --version` | Node v24.13.0 and npm 11.6.2. |
| Inline Python documentation validation via `python -` | 5 checks passed, 0 failed. Validated 4 Markdown files, 11 local links, 13 HTTP routes and 1 WebSocket route, 3 consistent JSON examples, and 6 pre-edit file hashes. |

### Bootstrap verification on Windows

CPython 3.11.0, uv 0.13.9, Node v24.13.0, and npm 11.6.2. Commands under `backend/` and `frontend/` use their respective directories.

| Command or check | Result |
| --- | --- |
| Backend `uv lock --python 3.11 --no-python-downloads` and `uv sync --locked --extra test --python 3.11 --no-python-downloads` | Both exit 0. The lock resolves 88 packages across base and optional groups. The test environment excludes the vision extra. |
| Backend `uv pip check` | Exit 0. All 39 installed packages compatible. |
| Backend `.\.venv\Scripts\python.exe -m pytest -q` | Exit 0. 12 passed, 0 failed, 0 skipped, no warnings on the final run. The first run emitted a Starlette TestClient deprecation warning. The test extra now includes its supported `httpx2` transport alongside the requested `httpx`. |
| Inline Python contract and import smoke | Exit 0. All 7 requested models generated JSON schemas, OpenCV 4.14.0 imported, and Ultralytics and Torch were absent. |
| Frontend `npm.cmd ci --no-audit --no-fund` | Exit 0. Installed 142 packages from the lockfile. |
| Frontend `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd run build` | All exit 0. Vite wrote the production files to `frontend/dist/`. |
| Backend `.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --env-file ../.env.example` | Started successfully. `GET /api/v1/health` returned HTTP 200 and exactly `{"status":"ok","version":"0.1.0","inference_status":"not_started"}`. `GET /openapi.json` declared the health path. |
| Built frontend via `node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 5173 --strictPort` with Playwright and Edge | Exit 0. Verified connected health and empty panels at 1366×768 and 390×844, unavailable and Retry behavior, zero page errors, and loopback-only requests from the page. The development server also passed its browser smoke test. |
| WSL Ubuntu prerequisite probes for `python3.11`, `node`, and `uv` | Each returned exit 127. The documented Linux/WSL install and runtime checks remain untested. |

### Durable API verification on Windows

CPython 3.11.0 and SQLite 3.38.4. Backend commands ran from `backend/`.

| Command or check | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m alembic upgrade head` and `.\.venv\Scripts\python.exe -m alembic current` | Both exit 0 on the default local database. Revision `0001 (head)`, six empty application tables. |
| Alembic `downgrade base`, `upgrade head`, `current`, and `check` on a disposable database | All exit 0. `check` reported `No new upgrade operations detected.` |
| `.\.venv\Scripts\python.exe -m pytest -q` | Five consecutive final runs each exited 0 with 38 passed, 0 failed, 0 skipped. Covers registration, invalid geofences, operator authorization and its OpenAPI contract, concurrent deduplication and review, rollback, append-only audit, WebSocket delivery and overflow, REST reconciliation, and restart persistence. |
| Source registration subprocess `python -m app.seed_source`, using an isolated synthetic file | Initial and repeated registration exited 0. The path outside the allowlist exited 1. One source and zero incidents persisted. |
| Single-worker Uvicorn with an isolated migrated database and a loopback HTTP/WebSocket client | Passed. Empty incident list returned HTTP 200. Disallowed WebSocket origin returned HTTP 403. Allowed connections received `ready`, closed with `1008` on a client message, and reconnected successfully. |

During development the first expanded suite reported 34 passed and 2 failed due to SQLite foreign-key error classification. A subsequent run reported 36 passed and 1 failed on a WebSocket teardown race. The final suite covers the corrected behavior.

### Real replay verification on Windows

CPython 3.11.0, OpenCV 4.14.0, Ultralytics 8.4.216, Torch 2.15.0, TorchVision 0.29.2, and LAP 0.5.14. The optional vision environment ran on CPU and was installed outside the base test environment.

| Command or check | Result |
| --- | --- |
| `uv sync --locked --extra test --extra vision --python 3.11 --no-python-downloads` with a separate `UV_PROJECT_ENVIRONMENT` | Exit 0. Installed all locked Windows vision dependencies. Verified the installed `YOLO.track` and `BYTETracker.reset` interfaces. |
| `uv lock --check --python 3.11 --no-python-downloads` | Exit 0. The existing lockfile resolves 88 packages. |
| Base environment `.\.venv\Scripts\python.exe -m pytest -q -rs` from `backend/` | Exit 0. 50 passed, 0 failed, 1 skipped. The optional real smoke skipped because the default workspace weights file was absent. Includes OpenCV decoding of a generated MP4, timestamp fallback, shutdown, restart recovery, bounded observations, and MJPEG lifecycle. |
| Vision environment `python -m pytest -q -s -m real_inference` from `backend/`, with `ASTRA_MODEL_WEIGHTS` and `ASTRA_INFERENCE_SMOKE_MP4` set to the temporary assets below | Exit 0. 1 passed, 0 failed, 0 skipped, 50 deselected. Two runs each observed 12 frames and ended normally. The first six samples at 0, 100, 200, 300, 400, and 500 ms each had one tracked object. A track ID persisted across consecutive frames and used the current run prefix in each replay. |
| `python -m alembic upgrade head`, `python -m app.seed_source`, and `python -m uvicorn app.main:app --host 127.0.0.1 --port <ephemeral> --workers 1` in the isolated vision environment | Migration and registration exited 0. The live smoke started a run, fetched and decoded a 512×512 annotated JPEG over MJPEG with CORS and cache headers, observed `ended`, then received `503 frame_unavailable`. |

- **Checkpoint.** The official `v8.4.0` release asset `yolo26n.pt` matched the published SHA-256 `9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef`. It was downloaded explicitly for the smoke and kept outside the workspace. [Official weights release](https://github.com/ultralytics/assets/releases/tag/v8.4.0)
- **MP4 input.** `nasa-still-smoke.mp4` was encoded with OpenCV from a public-domain NASA sample still via scikit-image v0.25.2, with a small frame-to-frame translation. It was a 12-frame, 10 FPS decoder and tracking fixture. Its SHA-256 was `3c31548f6c1a9d1788fde727c721c656235e51e4f970ee1c2475e08e3ed5dc3d`. [Sample attribution](https://scikit-image.org/docs/0.23.x/api/skimage.data.html#skimage.data.astronaut)

### Downloaded YOLO26 checkpoints

The `YOLO26/` clone is at revision `070ac3c51435984d992ba92eb3f234daf4e4500d`. It contains 25 complete checkpoint files across five sizes and five tasks. The replay adapter uses the nano object detection checkpoint at `YOLO26/yolo26n.pt`. For local replay, this path can be selected with `ASTRA_MODEL_WEIGHTS=YOLO26/yolo26n.pt`. [Ultralytics model repository](https://huggingface.co/Ultralytics/YOLO26)

| Command or check | Result |
| --- | --- |
| `Get-FileHash -Algorithm SHA256` and inline Python comparison with `git -C YOLO26 cat-file blob HEAD:<checkpoint>` | Exit 0 for the comparison. All 25 local sizes and hashes match the checked-out Git LFS manifest. Fresh bulk upstream digest requests were unavailable. |
| `Get-FileHash -Algorithm SHA256 -LiteralPath 'YOLO26/yolo26n.pt'` | The 5,544,453-byte checkpoint matches the previously verified official release SHA-256 recorded above. |
| Vision environment `python -m pytest -q -s -rs` from `backend/`, with `ASTRA_MODEL_WEIGHTS` pointing to the downloaded file and `ASTRA_INFERENCE_SMOKE_MP4` pointing to the NASA fixture | Exit 0. 51 passed, 0 failed, 0 skipped. The downloaded checkpoint completed both 12-frame CPU replays and retained a ByteTrack ID across consecutive frames. Other variants received file-integrity checks. |

### Prompt 3 local configuration and acceptance

The workspace's ignored `.env` selects `ASTRA_MODEL_WEIGHTS=YOLO26/yolo26n.pt` and contains a generated loopback operator token. The normal `backend/.venv` contains the locked CPU vision dependencies. The source and checkpoint paths are resolved relative to the workspace.

| Command or check | Result |
| --- | --- |
| `uv sync --locked --offline --extra test --extra vision --python 3.11 --no-python-downloads` and `uv pip check` from `backend/` | Both exit 0. All 68 installed packages compatible. |
| `.\.venv\Scripts\python.exe -m alembic current` | Exit 0. Workspace database at `0001 (head)`. |
| `uv run --offline --no-sync --env-file ../.env python -m pytest -q -s -rs` from `backend/`, with `ASTRA_INFERENCE_SMOKE_MP4` set to the NASA fixture | Exit 0. 51 passed, 0 failed, 0 skipped. Both real CPU replays reached EOF after 12 frames. In each run, sample counts at 0, 100, 200, 300, 400, and 500 ms were `1, 1, 1, 1, 1, 1`. The same run-scoped ID was observed on consecutive frames. |
| `.\.venv\Scripts\python.exe -m alembic upgrade head`, `.\.venv\Scripts\python.exe -m app.seed_source`, and `.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port <ephemeral> --workers 1 --env-file ../.env` | Passed using the configured checkpoint and operator token with an isolated database and the NASA fixture. A loopback client decoded a 512×512 annotated JPEG with the expected CORS and cache headers, observed `ended`, received `503 frame_unavailable` after EOF, and successfully stopped a second run. |
| `uv run --offline --no-sync --env-file ../.env python -m pytest -q -s -rs` from `backend/`, with `ASTRA_INFERENCE_SMOKE_MP4` set to the registered `data/demo_video/aerial-intersection-validation.mp4` | Exit 0. 51 passed, 0 failed, 0 skipped. Both runs processed 40 frames and reached EOF. Counts of tracked vehicles at 0, 100, 200, 300, 400, and 500 ms were `3, 3, 2, 2, 0, 0` in each run. A run-scoped vehicle ID persisted across consecutive frames. |
| `uv run --offline --no-sync --env-file ../.env python -m pytest -q -s -m real_inference`, with `ASTRA_INFERENCE_SMOKE_MP4` set to the NASA fixture | Exit 0. 1 passed, 0 failed, 0 skipped, 50 deselected. Class output confirmed one tracked person in each of the first six frames of both 12-frame runs. |
| `.\.venv\Scripts\python.exe -m app.seed_source` with the aerial source configuration | Exit 0. Registered `aerial-intersection-validation` in the workspace database using the local excerpt and its verified SHA-256. [Source provenance](../data/README.md#local-aerial-replay-validation-source) |
| `.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port <ephemeral> --workers 1 --env-file ../.env` with the workspace database and registered aerial MP4 | Passed. The authenticated replay streamed a 1080×1920 JPEG, persisted `ended`, and returned `503 frame_unavailable` at EOF. The source checksum matched SQLite, and the incident count stayed at zero. |

The initial aerial excerpt beginning at 00:00 decoded through EOF but produced no stable tracks, so that test run reported 50 passed and one failed. The validated excerpt begins near 00:12. Both used the existing production detector and tracker settings. Once the local source was configured, the first workspace suite also reported 50 passed and one failed because the seed subprocess picked up the demo license URL. The seed fixture now disables dotenv loading for its subprocess, and the final configured suite passed.

### Prompt 4 replay rules and calibration verification

| Command or check | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m alembic upgrade head`, `.\.venv\Scripts\python.exe -m alembic current`, and `.\.venv\Scripts\python.exe -m alembic check` from `backend/` | All exit 0. Workspace at `0002 (head)`, with no new upgrade operations detected. |
| `.\.venv\Scripts\python.exe -m pytest -q -rs` from `backend/` with no smoke environment | Exit 0. 60 passed, 0 failed, one optional real-inference test skipped because no weights path was exported to pytest. |
| `uv run --offline --no-sync --env-file ../.env python -m pytest -q -s -rs` from `backend/`, with `ASTRA_INFERENCE_SMOKE_MP4` set to the registered aerial MP4 | Exit 0. 61 passed, 0 failed, 0 skipped. Both real replays consumed 40 frames. Deterministic tests cover crowd hysteresis and deduplication, zone boundary and reentry, occlusion and expiry, run reset, world-point gating, homography rejection, and thumbnail, incident, and audit delivery through the worker. |
| `.\.venv\Scripts\python.exe -m alembic upgrade head` and inline `.\.venv\Scripts\python.exe -` TestClient replay harness from `backend/`, with the verified workspace YOLO26n checkpoint and isolated rules JSON and SQLite database | Exit 0. The real aerial MP4 produced 40 inference frames with vehicle tracks and zero candidates under person-only rules. The controlled moving-still MP4 produced 38 inference frames with a person track and one pending zone candidate at frame 32, footage time 3,200 ms. It carried `image_roi_only`, null coordinates and uncertainty, and one creation audit entry. `GET /api/v1/incidents/{id}/thumbnail` returned a 34,891-byte annotated JPEG. [Controlled fixture recipe](../data/README.md#controlled-rule-verification-source) |

Controlled MP4 SHA-256 was `ae65af8d6bdce5c07ae4a7abf9352d23d05a2a3baeb42cfde4e6b957dfb5f1e3`. Confirmation JPEG SHA-256 was `0d5ecbc535ddba89aeb5bd0034259cc2b55a066d8ccf08955dcf905a8990cae2`. Evidence and its SQLite database were retained in the private temporary verification directory.

**Untested at Prompt 4.** Linux/WSL, the team's final demo footage, crowd confirmation on real footage, a physically surveyed fixed-camera site, people at aerial scale, browser MJPEG rendering, MapLibre rendering, dashboard review, and field benchmarks. The integrated release license path remains open.

### Prompt 5 dashboard verification on Windows

Node v24.13.0, npm 11.6.2, Vitest 5.1.1, Vite 8.3.8, and MapLibre GL JS 6.19.0. HTTP types were generated with `openapi-typescript` 7.13.0 from the running backend's `/openapi.json`. The browser checks used Edge with Playwright against the production build, one real Uvicorn worker, and a disposable migrated SQLite database.

| Command or check | Result |
| --- | --- |
| `npm.cmd run lint`, `npm.cmd run typecheck`, and `npm.cmd run build` from `frontend/` | All exit 0. Vite warned about its 500 kB threshold. The lazy MapLibre module was 1,064.10 kB minified and its separate worker was 550.37 kB. |
| `npm.cmd test` from `frontend/` | Exit 0. 7 passed in 2 files, 0 failed, 0 skipped. Covers geographic bounds and order, calibrated/source gates, measured-only uncertainty, event envelopes, reconnect backoff, and combined REST refreshes. |
| `.\.venv\Scripts\python.exe -m pytest -q -rs` from `backend/` with `ASTRA_MODEL_WEIGHTS` set to the verified `YOLO26/yolo26n.pt` and `ASTRA_INFERENCE_SMOKE_MP4` set to the registered aerial excerpt | Exit 0. 61 passed, 0 failed, 0 skipped. The real inference smoke was included. |
| `.\.venv\Scripts\python.exe -m alembic upgrade head` and `.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --env-file <verification.env>` from `backend/`, plus `node.exe node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 5173 --strictPort` from `frontend/` | Migrated and served the isolated verification database. Playwright used `http://localhost:5173`, the configured browser origin. |
| `node.exe <verification-directory>/browser.cjs` against those processes | Passed real annotated MJPEG, EOF and Stop, aerial queue remaining empty, real image-space candidate at 3,200 ms with a thumbnail, both terminal reviews and audit reasons, WebSocket reconnect and incident REST refetch, REST outage and recovery, missing media, keyboard review, and 1366×768/390×844 layouts. MapLibre rendered a test-only world geofence. Captures used the aerial and controlled clips and their actual persisted records. |
| `node.exe <verification-directory>/browser.cjs` with `ASTRA_BROWSER_FAILURE=model` and the same Uvicorn command with `ASTRA_MODEL_WEIGHTS` pointing to an absent local checkpoint | Exit 0. The UI showed the real inference failure and no replacement stream. |

The first production browser pass exposed a missing MapLibre worker URL and audit overflow at projector size. The final build uses Vite's bundled local worker and fits the primary panels and audit heading at 1366×768. Review actions stay visible below the scrollable incident details. [MapLibre Vite integration](https://maplibre.org/maplibre-gl-js/docs/)

Desktop replay, pending review, saved audit, and mobile captures are in the workspace's ignored `data/evidence/prompt5/` directory.

**Untested at Prompt 5.** World incident points and measured uncertainty were exercised with unit fixtures. A physically surveyed site, the team's final footage, a real-footage crowd confirmation, browser compatibility beyond Windows Edge, Linux/WSL, and field performance were unverified. Gate 6 and the integrated release license decision were open at this milestone.

### Prompt 6 system integration verification on Windows

The runbook uses a clean, private stage. The production dashboard served from Vite preview and the backend used the normal launcher, real model, SQLite migration `0002`, and operator review. The Playwright harness drove Windows Edge 157.0.4341.60 and requested graceful Uvicorn shutdown from a private orchestration file. The browser stayed open as a new backend process bound the same port. The workspace demo database was independent of the verification stage.

| Check or command | PASS / FAIL and output |
| --- | --- |
| `backend\.venv\Scripts\python.exe scripts/smoke_test.py fixture` from the root | **PASS**, exit 0. `PASS TEST DATA health, durable candidate, idempotency, auth, review, audit, app restart and WebSocket reconnect`. Repeated successfully in the clean Python environment. |
| `backend\.venv\Scripts\python.exe scripts/smoke_test.py prepare --output <fresh-stage> --still <astronaut.png>` from the root | **PASS**, exit 0. `PASS two registered sources and zero seeded incidents`. The controlled MP4 digest was `b7eebbac7fd455257fbf988f07be4a29a8ccd8f75d8170c9e44efbb040f925db`. |
| `uv sync --locked --offline --extra test --extra vision --python 3.11 --no-python-downloads` from `backend/` with a fresh `UV_PROJECT_ENVIRONMENT` | **PASS**, exit 0. Installed 68 packages from the local cache. |
| `npm.cmd ci --offline --no-audit --no-fund` in a fresh directory with the frontend manifests | **PASS**, exit 0. Installed 163 packages from the local cache. Production build also passed in the fresh directory. |
| `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd test`, `npm.cmd run build` from `frontend/` | **PASS**, all exit 0. Vitest reported 7 passed in 2 files, 0 failed, 0 skipped. Vite warned that the lazy MapLibre chunk exceeds 500 kB. |
| `.\.venv\Scripts\python.exe -m pytest -q -rs` from `backend/`, with the checkpoint and aerial MP4 exported as `ASTRA_MODEL_WEIGHTS` and `ASTRA_INFERENCE_SMOKE_MP4` | **PASS**, exit 0. `64 passed in 15.61s`, 0 failed and 0 skipped. Includes real inference, stop and cleanup, second lifespan rejection, structured calibration/storage failures, and restart recovery. |
| `.\.venv\Scripts\python.exe -m app.serve --workers 2` and the same launcher with `--reload` | **PASS** refusal. Both exited 2 and returned `single_worker_required`. A second running process sharing the same stage database failed startup with `worker_in_use` and exit 3. The first process remained healthy. |
| `.\.venv\Scripts\python.exe -m app.serve --env-file <stage>/.env --port 8001` with `ASTRA_ANALYSIS_CONFIG` set to an absent file | **PASS** refusal, exit 1. JSON error code `analysis_config_invalid`, with no private path in its message. |
| `node.exe <stage>/browser_smoke.cjs` from the root, using the backend launcher and `node.exe node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 5173 --strictPort` | **PASS**, exit 0. Real annotated MJPEG reached the browser. Aerial EOF left 0 incidents. The controlled source produced 2 persisted candidates, both WebSocket events and both JPEGs. Review and audit passed before and after restart. The browser reconnected automatically, received `ready`, and refetched incidents. The same assertions are reproducible with the [manual runbook](SMOKE_TEST.md#run-the-real-replay-and-verify-restart). |
| Read-only SQLite and OpenCV artifact validation | **PASS**, exit 0. The crowd row was `pending` at 200 ms. The zone row was `acknowledged` at 3,300 ms with `image_roi_only`, null location, and the exact `created`/ `acknowledged` audit entries. OpenCV decoded all 705 frames of the 28.2 s WebM recording. |

During development one suite run failed on the frozen database error message. The existing envelope was restored and the final suite passed. The browser harness initially expected the wrong Uvicorn startup-failure exit code and needed Playwright's matching FFmpeg to record. Playwright's installer pruned unused browser cache versions. The final recorded browser run passed.

#### Measured on this machine

Windows 11 Home Single Language build 26300, Intel Core 7 240H (10 cores, 16 logical processors), 15.61 GiB reported RAM, NVIDIA GeForce RTX 5050 Laptop GPU and Intel Graphics present. The adapter used CPU at `imgsz=640`. Torch reported no CUDA availability and 10 CPU threads. CPython 3.11.0, SQLite 3.38.4, FastAPI 0.165.0, Uvicorn 0.54.0, SQLAlchemy 2.0.58, Alembic 1.20.1, OpenCV 4.14.0.94, Ultralytics 8.4.216, Torch 2.15.0, TorchVision 0.29.2, and LAP 0.5.14. Node 24.13.0, npm 11.6.2, React 19.3.1, TypeScript 6.0.3, Vite 8.3.8, MapLibre 6.19.0, and Vitest 5.1.1.

Checkpoint `yolo26n.pt` SHA-256 `9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef`. Shipped `bytetrack.yaml` SHA-256 `395701d947a749179dee3e327b1181b730c4ca98e7cac5a2ab05280aae573b8b`. Both inputs reported 10 source FPS.

| Run | Frames / active processing time | Processing FPS | Accepted start → first stored JPEG | Browser start request → first decodable MJPEG |
| --- | --- | ---: | ---: | ---: |
| Aerial, 1080×1920, cold model | 40 / 3.078 s | 12.995 frames/s | 2,906.0 ms | 3,008.9 ms |
| Controlled, 1152×512, same warmed model | 45 / 1.341 s | 33.557 frames/s | 94.0 ms | 190.9 ms |

Processing time includes successful decode, tracking, rules, JPEG encoding, any incident commit, and publishing. It excludes playback pacing, model/file setup, and network delivery. The browser timer spans Playwright's observation of the start request to the first detected decoded MJPEG image. Each row is one observed replay under different input and model conditions. [Timing definitions](SMOKE_TEST.md#read-the-metrics)

**Estimates.** No performance estimates were used. The UI continues to show `N/A` for FPS because the details are in server logs and the v1 response has no throughput field.

**Unmeasured or unverified at Prompt 6.** Capture-to-alert and production network latency, accuracy/mAP, GPU performance, longer permissioned aerial footage with crowd or intrusion events, a surveyed world-calibrated scene, Linux/WSL, and browsers beyond Windows Edge. The team's final-source selection and integrated release license decision were open. The workspace had no root Git metadata at that checkpoint.

The actual 28.2-second fallback recording and screenshots are in the ignored `data/evidence/prompt6/` folder. The recording shows an earlier verified replay and restart.

### Prompt 7 benchmark and submission verification

| Check or exact command | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest -q -rs` from `backend/`, with `ASTRA_MODEL_WEIGHTS` set to `YOLO26/yolo26n.pt`, `ASTRA_INFERENCE_SMOKE_MP4` to the registered aerial MP4 and `ASTRA_DB_PATH` to a temporary file | **PASS**, exit 0, `67 passed in 16.62s`, 0 failed, 0 skipped. Covers real inference, stop/EOF, stale stream run IDs, optional evidence and bounds, review/auth/idempotency, and calibrated versus image-space or unavailable geography. |
| `.\backend\.venv\Scripts\python.exe scripts/smoke_test.py fixture` from the root | **PASS**, exit 0. TEST DATA health, durable candidate, idempotency, auth, review, audit, restart, and WebSocket reconnect. |
| `npm.cmd test`, `npm.cmd run lint`, `npm.cmd run typecheck`, and `npm.cmd run build` from `frontend/` | **PASS**, all exit 0. Vitest reported 7 passed across 2 files, including stale/duplicate socket callbacks and REST refresh. Vite warned about its 500 kB chunk threshold. The lazy MapLibre module was 1,064.10 kB minified. |
| `uv lock --check --offline --python 3.11 --no-python-downloads` and `uv sync --locked --offline --extra test --extra vision --python 3.11 --no-python-downloads` with a fresh `UV_PROJECT_ENVIRONMENT` from `backend/` | **PASS**, both exit 0. Resolved 88 locked packages and installed 68 in the fresh vision/test environment. |
| `npm.cmd ci --offline --no-audit --no-fund` in a fresh directory with the frontend manifests | **PASS**, exit 0, 163 packages installed. |
| `.\backend\.venv\Scripts\python.exe scripts/benchmark.py --video data/demo_video/aerial-intersection-validation.mp4 --warmup 8 --frames 300 --output <new-aerial-report.json>` from the root | **PASS**, exit 0. Processed 40 frames, 0 candidates. |
| `.\backend\.venv\Scripts\python.exe scripts/benchmark.py --source-id controlled-rule-verification --video <stage>/media/controlled-two-tracks.mp4 --rules <stage>/rules.json --geofence <stage>/zone.json --warmup 8 --frames 300 --output <new-controlled-report.json>` from the root | **PASS**, exit 0. Processed 45 frames, with two real candidates and an opt-in thumbnail for each. Crowd at 200 ms and image zone entry at 3,300 ms. Read-back validated the JSON sample counts and absent aerial alert timings. |
| `.\backend\.venv\Scripts\python.exe scripts/smoke_test.py prepare --output <fresh-stage> --still <astronaut.png>` and the prior `node.exe <fresh-stage>/browser_smoke.cjs` rehearsal procedure | **PASS**, both exit 0. Licensed aerial MJPEG reached EOF with an empty queue. Both controlled candidates reached the dashboard. The reviewed zone incident and audit survived graceful backend restart and browser reconciliation. Direct SQLite queries verified two thumbnails of 34,411 and 32,373 bytes and the saved acknowledgement. |
| OpenCV read-back of the screen recording | **PASS**, exit 0, 694 decoded frames at 25 encoded FPS, 27.76 s. Captures and both final benchmark JSONs are under the ignored `data/evidence/prompt7/` directory. |
| Inline Python Markdown link and anchor check | **PASS**, exit 0. Validated 38 local link targets across 7 package documents. |

#### Measured offline CPU workload

Same Windows 11 build 26300 machine and checkpoint as Prompt 6. Intel Core 7 240H, 10 physical and 16 logical cores, 15,987.07 MiB reported system RAM. Python 3.11.0, OpenCV 4.14.0, SQLite 3.38.4, Ultralytics 8.4.216, Torch 2.15.0, ByteTrack from the shipped `bytetrack.yaml`, batch one, CPU, `imgsz=640`. The weights and config checksums are in both JSON reports and the [previous hardware log](#measured-on-this-machine).

| Measurement | Aerial 1080×1920, 40 frames | Controlled 1152×512, 45 frames |
| --- | ---: | ---: |
| Source playback FPS | 10 | 10 |
| Warmed frames before measured pass | 8 | 8 |
| Decode-only file-read FPS | 172.033 | 708.782 |
| MP4 read/decode mean / p95, in pipeline | 5.104 / 7.414 ms | 1.387 / 1.741 ms |
| YOLO26n forward mean / p95 per frame | 28.825 / 38.767 ms | 23.140 / 30.134 ms |
| ByteTrack update mean / p95 per frame | 0.736 / 1.189 ms | 0.583 / 0.991 ms |
| Geography and rule dispatch mean / p95 | 0.030 / 0.067 ms | 0.183 / 0.258 ms |
| Unpaced local pipeline | 21.578 frames/s | 32.357 frames/s |
| Confirmation frame read → candidate, mean | Unmeasured, 0 candidates | 24.698 ms, 2 candidates |
| Confirmation frame read → local incident commit, mean | Unmeasured, 0 candidates | 50.154 ms, 2 candidates |
| Process CPU across 16 logical cores | 49.26% | 49.15% |
| Peak sampled process RSS | 534.06 MiB | 449.91 MiB |

Each column shows one measured pass with its own input and active rules. The aerial baseline had no configured crowd threshold or zone. The controlled run used both rules and retained thumbnails in the disposable database. The RTX 5050 laptop GPU, driver 617.42, reported 0% utilization and 223 MiB used of 8,151 MiB before and after each pass. The inference workload was on CPU. Raw reports are `aerial-final.json` and `controlled-final.json`. [Timing definitions and reproduction commands](BENCHMARKS.md)

**Unmeasured or unverified.** Accuracy/mAP, real aerial crowd events, capture-to-alert and production-network latency, GPU inference, surveyed calibration, Linux/WSL, and other browsers. Integrated model distribution terms and capture sharing approval remain open. The slides/PDF deliverable is a content outline.

### GitHub source publication checks

| Command or check | Result |
| --- | --- |
| First-commit staged file audit and `git diff --cached --check` | Passed. Source, fixtures, dependency lockfiles and project documentation are staged for `main`. Local secrets, model checkout, footage, database files, verification captures, and pre-implementation presentation material are excluded. |
| `.\.venv\Scripts\python.exe -m pytest -q -rs` from `backend/` with an isolated database, the local YOLO26n weights and the aerial excerpt | Exit 0. 67 passed in 18.40 s, 0 failed, 0 skipped. The deliberately invalid MP4 fixture emitted the expected decoder diagnostic. |
| `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd test`, and `npm.cmd run build` from `frontend/` | All exit 0. Seven tests passed in two files, 0 failed and 0 skipped. The production build retained the MapLibre chunk-size warning. |

The source target is [AstraSentinel on GitHub](https://github.com/dsreecharan/AstraSentinel). Repository publication does not settle the pending media-sharing and integrated-model distribution decisions. Platform and runtime coverage stays as recorded above.

### Prompt 8 Phase 2 verification

Windows 11, Intel Core 7 240H, Python 3.11.0, Edge and Node 24.13.0. Ran the optional Compose services using the existing Ubuntu WSL 2 Docker daemon (Engine 29.1.3, Compose 2.40.3) in its root context. Tested PostgreSQL 17.12, PostGIS 3.7.0, MediaMTX 1.21.4, FFmpeg 8.1.3, Psycopg 3.3.9 and MAVSDK 4.2.1.

| Check | Exact result |
| --- | --- |
| Before edits, `python -m pytest -q -rs` with the approved YOLO26n weights, real aerial smoke MP4 and isolated SQLite | Exit 0, 67 passed in 16.86 s, zero failures or skips. |
| Before and after edits, `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd test`, `npm.cmd run build` from `frontend/` | All exit 0 on both runs. Seven tests passed each time. Vite reported the same MapLibre chunk-size warning. |
| Before and after edits, `scripts/smoke_test.py prepare` and the existing Edge/Playwright smoke rehearsal from Prompt 6 | Both rehearsals exit 0. Aerial MJPEG rendered and reached EOF with zero incidents. The real controlled replay triggered both rules. The review and audit remained equal after backend restart and browser reconciliation. |
| `uv sync --locked --offline --extra test --extra vision --python 3.11 --no-python-downloads` in a fresh environment, then the MVP `python -m pytest -q -rs` with the real model/footage | Exit 0, 68 passed, four opt-in infrastructure tests skipped, no failures. Verified Psycopg and MAVSDK were absent from that environment. |
| `docker compose -f compose.phase2.yml config --services` with no profiles, then `--profile media --profile postgis up -d --wait` with a private environment file | The default selection was empty. With both profiles selected, both containers became healthy. |
| `python -m alembic upgrade head` and `python -m alembic check` for both profiles | Both passed. SQLite advanced a scratch copy of revision `0002` to `0003`; PostGIS migrated its separate database. Alembic warns during reflection about the native geometry column type and reports no new upgrade operations. |
| `python -m pytest -q -rs -s -m phase2` with the three service test settings in the runbook | Exit 0, four passed, 68 deselected. Covers authenticated RTSP ingest, HLS serving, native spatial queries, unchanged REST/review/WebSocket semantics, restart, append-only audit and native MAVSDK UDP cleanup. |
| `python -m pytest -q -rs` with both the real model/footage and all Phase 2 integration settings | Exit 0, 72 passed in 31.05 s, zero failures or skips. |
| `python scripts/smoke_test.py fixture` | Exit 0, authenticated deterministic API, review/audit persistence and reconnect passed. |
| `node scripts/check_media.cjs` with Edge and an authorized 320×180, 10 FPS H.264 test pattern publisher | Exit 0. Each player decoded and advanced video. The then-running HLS playlist had been checked before navigation. |
| `VITE_RTSP_MONITOR=true npm run build` in a temporary output directory and the default build's asset check | Exit 0. The media-only player links appeared in the opt-in assets. Both builds succeeded. |
| Compose `down --volumes` for the disposable verification project | Exit 0. Both test containers, both networks, and the scratch volume were removed. |

The initial media HTTP test followed neither the HLS playlist redirect nor its target. Enabling redirects in the test verified the actual playlist. The initial MAVSDK test found the pinned package exposed a native subscription callback, which the adapter now uses. The initial PostGIS schema check reflected extension-owned tables. The PostgreSQL migration filter is now limited to application tables.

| Local comparison | Observed result |
| --- | ---: |
| SQLite median incident creation plus review, including audit commits | 7.175 ms |
| PostGIS median for the same workload | 8.730 ms |
| WebRTC browser navigation to advancing decoded video | 1,330.9 ms |
| HLS browser navigation to advancing decoded video | 100.7 ms |

The storage figures are from the same test, with 30 measured synthetic incidents per profile and five warm-ups. PostGIS includes the local WSL connection. Player startup figures are one observation each with an active publisher and a prewarmed HLS manifest. They do not compare transport latency or prove sustained throughput. Follow the [exact setup and commands](PHASE2.md).

**Unverified.** Full PX4/Gazebo SITL, real airframes, sustained or remote media traffic, capture-to-display latency, and other browser/platform combinations. The PostGIS profile is a separate store. Redis remains deferred because the Astra Fly application still has one producer.

Use these commands for the planning commit in the intended Git checkout.

```text
git add -- AGENTS.md docs/CONTRACTS.md docs/DECISIONS.md docs/STATUS.md
git commit -m "docs: freeze MVP architecture and agent rules"
```

For each subsequent task, update the gates and append the exact verification commands, pass/fail/skip counts, and remaining untested functionality here.

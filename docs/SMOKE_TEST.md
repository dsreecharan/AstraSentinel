# Astra Fly system smoke test

Run this on the demo machine after installing the locked dependencies. Use a fresh private verification directory each time. The team database and its existing records are independent of this walkthrough.

## Inputs

- Put the approved four-second aerial excerpt in `data/demo_video/aerial-intersection-validation.mp4`. Its expected SHA-256 is `2b08fdd659f337e7ce4898098b09c64a3f49c204854cdfb02beb623ba8ea71b7`. Obtain the exact excerpt from the team's private copy. For replacement footage, register the team's own approved MP4 with its own source ID, digest, and attribution using the README. [Aerial source record](../data/README.md#local-aerial-replay-validation-source) · [Register an approved MP4](../README.md#register-one-licensed-mp4)
- Use the trusted YOLO26n detection checkpoint at `YOLO26/yolo26n.pt`, or pass its local path with `--weights`. The checkpoint used in verification had SHA-256 `9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef`. [Official weights release](https://github.com/ultralytics/assets/releases/tag/v8.4.0)
- Obtain the pinned NASA sample `astronaut.png` from scikit-image v0.25.2. Its expected SHA-256 is `88431cd9653ccd539741b555fb0a46b61558b301d4110412b5bc28b5e3ea6cb5`. The controlled replay uses a moving and a fixed copy of the same public-domain still to exercise two detected person tracks. It depicts a controlled rule scenario. [Pinned PNG](https://github.com/scikit-image/scikit-image/blob/v0.25.2/skimage/data/astronaut.png) · [NASA attribution and terms](https://scikit-image.org/docs/0.26.x/api/skimage.data.html#skimage.data.astronaut)

The stage script verifies the two source digests, builds the controlled MP4 at 1152×512 and 10 source FPS, migrates SQLite, registers both sources, and writes local operator credentials and rules. It starts with zero incidents. The runtime uses local files.

## Prepare once per verification run

Start from the project root in PowerShell. Preinstall uv and the runtimes listed in the README. Initial dependency installation uses the configured package registries or a populated local cache.

```powershell
Set-Location backend
uv sync --locked --extra test --extra vision --python 3.11 --no-python-downloads
Set-Location ..
$Python = '.\backend\.venv\Scripts\python.exe'
$Demo = Join-Path (Get-Location).Path 'data/evidence/prompt6-run'
$Still = 'C:\path\to\astronaut.png'
& $Python scripts/smoke_test.py fixture
& $Python scripts/smoke_test.py prepare --output $Demo --still $Still
Set-Location frontend
npm.cmd ci --no-audit --no-fund
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
```

The fixture command exercises auth, idempotency, candidate and review events, audit, and reopening the same disposable database. It prints `PASS TEST DATA …`. For another real walkthrough, pick a new `$Demo` directory. On Linux/WSL use [the installed runtimes and paths](../README.md#linux-or-wsl), `backend/.venv/bin/python`, and `npm`.

## Run the real replay and verify restart

From the project root in a backend terminal.

```powershell
$Demo = Join-Path (Get-Location).Path 'data/evidence/prompt6-run'
Set-Location backend
.\.venv\Scripts\python.exe -m app.serve --env-file (Join-Path $Demo '.env')
```

From the project root in a frontend terminal.

```powershell
Set-Location frontend
node.exe node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 5173 --strictPort
```

From the project root in a third terminal, register the controlled image ROI once for this database. Read the token privately when entering it into the dashboard and keep it out of screenshots and recordings.

```powershell
$Demo = Join-Path (Get-Location).Path 'data/evidence/prompt6-run'
$Api = 'http://127.0.0.1:8000/api/v1'
$TokenLine = Get-Content -LiteralPath (Join-Path $Demo '.env') | Where-Object { $_.StartsWith('ASTRA_OPERATOR_TOKEN=') }
$DemoToken = $TokenLine.Substring('ASTRA_OPERATOR_TOKEN='.Length) | ConvertFrom-Json
Invoke-RestMethod -Uri "$Api/geofences" -Method Post -Headers @{ Authorization = "Bearer $DemoToken" } -ContentType 'application/json' -InFile (Join-Path $Demo 'zone.json')
```

1. Open the dashboard and wait for **Backend online** and **Events connected**. Use **Operator access** and the private token from the stage. [Local dashboard](http://localhost:5173)
2. Select **Aerial intersection - licensed excerpt** and start replay. Check that the video shows **REPLAY** and annotated vehicle tracks. Wait for **End of replay**. The verified aerial excerpt has zero person-rule candidates.
3. Select **Controlled fixture - NASA still with two tracks** and start. The crowd rule confirms two person tracks against the explicit threshold of one over three frames. The zone rule confirms three frames of an observed entry into the pixel ROI at x=385. Expect two pending candidates with actual evidence. Check the zone candidate has the image-space alert label, no geographic marker, and a run-scoped track ID.
4. Acknowledge the zone candidate with a reason. In **Audit timeline**, check **Candidate created** and **Acknowledged**, the server-derived actor, and the reason. Keep that candidate selected.
5. Press Ctrl+C in the backend terminal and wait for shutdown. Wait for **Backend unavailable** or **Events reconnecting** in the same browser tab. Start the backend again using the same command, stage, and SQLite database. Keep Vite running.
6. Wait for **Backend online** and **Events connected**. Check the selected incident and its audit reason again. The browser gets a fresh WebSocket `ready` and refetches REST state. Query the same incident and audit via REST before and after the restart if checking exact persistence.

```powershell
$Recent = (Invoke-RestMethod "$Api/incidents").items
$Zone = $Recent | Where-Object { $_.event_type -eq 'zone_intrusion' } | Select-Object -First 1
Invoke-RestMethod "$Api/incidents/$($Zone.id)"
Invoke-RestMethod "$Api/incidents/$($Zone.id)/audit"
```

Capture the replay, evidence and saved audit from the running app. Label a fallback screen recording **Recorded verification of an earlier replay**. Keep the stage database and captured media private.

## Error and shutdown checks

| Condition | Observable result or recovery |
| --- | --- |
| MP4 missing, moved outside the media root, or changed | Run error `video_unavailable` or `video_changed`. Restore the registered bytes or register a new source ID. |
| Unreadable MP4 or unsupported codec | Run error `decode_failed`. Check the source file and verify it decodes in the installed OpenCV FFmpeg backend. |
| Missing or incompatible checkpoint | Run error `model_unavailable`. Correct the trusted local `.pt` path and restart the backend. |
| Invalid rules or calibration file | Startup error `analysis_config_invalid`. Check file readability, source checksum, scene and controls. Runtime analysis mismatches produce the same run error. Configurations that do not apply to a particular frame yield no geographic point. |
| SQLite unavailable, unwritable or unmigrated | Startup or HTTP error `storage_unavailable`. Check directory permissions, path and Alembic revision. |
| Server disconnects | Backend unavailable message and WebSocket reconnect state. On `ready`, the UI reconciles with REST. **Retry backend** triggers a manual refresh. |
| Stop pressed | The latest JPEG clears immediately. The worker releases capture and commits `stopped` after any in-flight native call returns. Shutdown joins the worker and releases the model reference. |
| `--workers 2` or `--reload` | The launcher rejects either flag with `single_worker_required`, exit 2. A second process using the same database is rejected at application startup with `worker_in_use`. The per-database lock is released when its owner closes. |

## Read the metrics

Each completed replay logs one `replay_metrics` JSON object. `processing_fps` is frames published divided by the time spent reading successful frames and processing them through tracking, rules, JPEG, applicable SQLite commits, and publishing. It excludes deliberate replay pacing, model/file setup, final EOF read, and network or browser rendering. The first frame's inference warm-up is included. `source_fps` is OpenCV metadata. `accepted_to_first_jpeg_ms` starts after the start record commits and ends when the first JPEG is stored. It includes opening, validation, model setup or tracker reset and processing that frame. `post_setup_wall_seconds` includes pacing and starts when source and model setup finish.

Record per-run numbers, runtime versions, hardware, source size, and the model digest. Use the status log as the run-specific record. [Verification results](STATUS.md)

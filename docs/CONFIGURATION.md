# Configuration and development reference

## Environment and verification

For a custom source, copy `.env.example` to `.env` at the repository root and set a private operator token. The backend launcher, Alembic, source registration, and Vite read that file. Restart the relevant process after changing it. `VITE_` variables are public browser configuration. Keep credentials outside them. Relative storage and media directories are resolved from the workspace root. The database parent directory must exist and be writable.

| Variable | Default | Purpose |
| --- | --- | --- |
| `ASTRA_FRONTEND_ORIGIN` | `http://localhost:5173` | Exact loopback browser origin accepted by CORS. Use the origin you open in the browser. |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Backend base URL used by the typed frontend client. |
| `ASTRA_DB_PATH` | `data/astra.sqlite3` | Private SQLite database file. |
| `ASTRA_MEDIA_DIR` | `data/demo_video` | Allowed local source directory. |
| `ASTRA_MODEL_WEIGHTS` | `data/weights/yolo26n.pt` | Local trusted Ultralytics YOLO26n detection checkpoint. |
| `ASTRA_ANALYSIS_CONFIG` | Empty | Optional workspace-relative JSON file with source-specific rules, calibration, and thumbnail permission. |
| `ASTRA_OPERATOR_NAME` | `local-operator` | Server-side actor recorded on a successful review. |
| `ASTRA_OPERATOR_TOKEN` | Empty | Private bearer token for the local operator role. An empty value leaves write routes disabled. |

Open [the health endpoint](http://127.0.0.1:8000/api/v1/health) in a browser or use `curl.exe -fsS http://127.0.0.1:8000/api/v1/health` on Windows and `curl -fsS http://127.0.0.1:8000/api/v1/health` on Linux. The expected result is HTTP 200 with this body.

```json
{"status":"ok","version":"0.1.0","inference_status":"not_started"}
```

The [OpenAPI document](http://127.0.0.1:8000/openapi.json) describes the implemented HTTP routes. The [contracts](CONTRACTS.md) also specify the WebSocket envelopes and remaining v1 routes. See [status](STATUS.md) for verification and coverage.

## Register one licensed MP4

Complete the [source provenance template](../data/README.md) and put the approved footage in the allowed media directory. In the root `.env`, set `ASTRA_SOURCE_ID`, `ASTRA_SOURCE_TITLE`, `ASTRA_SOURCE_VIDEO_PATH`, `ASTRA_SOURCE_RIGHTS_NOTE`, and `ASTRA_SOURCE_ATTRIBUTION`. Set `ASTRA_SOURCE_LICENSE_URL` when applicable. The file must resolve inside `ASTRA_MEDIA_DIR`, including after following symlinks. Relative file names are resolved from that directory.

Run the migration and register the source from `backend/`.

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.seed_source
```

```bash
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.seed_source
```

Registration saves one source and computes its SHA-256. Re-running with the same source and metadata keeps the existing row. Use a new source ID for changed footage. Source paths stay private, and registration leaves the incident queue empty.

## Run a real replay

From `backend/`, install the pinned vision extra explicitly.

```text
uv sync --locked --extra test --extra vision --python 3.11 --no-python-downloads
```

Place the trusted detection checkpoint at `ASTRA_MODEL_WEIGHTS` and verify its release SHA-256. Download and installation are setup steps. The replay service uses the configured local file and disables Ultralytics online checks and automatic dependency installs. The Windows CPU profile was verified with Ultralytics 8.4.216, Torch 2.15.0, TorchVision 0.29.2, and LAP 0.5.14. Ultralytics provides YOLO26 weights under its AGPL-3.0 and Enterprise licensing options. [Official YOLO26 release](https://github.com/ultralytics/assets/releases/tag/v8.4.0) · [Ultralytics license](https://www.ultralytics.com/license)

The Windows validation setup uses `ASTRA_MODEL_WEIGHTS=YOLO26/yolo26n.pt` in the workspace `.env`. Its local source ID is `aerial-intersection-validation`. [Footage attribution and SHA-256](../data/README.md#local-aerial-replay-validation-source)

On Windows, use the [one-click launcher](../README.md#one-click-start-on-windows) to start both servers with the root `.env`. To start them separately, run `.\.venv\Scripts\python.exe -m app.serve --env-file ../.env` on Windows or `.venv/bin/python -m app.serve --env-file ../.env` on Linux from `backend/`. In a second terminal with the installed frontend dependencies, run `npm.cmd run dev` on Windows or `npm run dev` on Linux from `frontend/`. The API launcher rejects reload and multiple workers and holds a process lock for the SQLite database. For API clients, send the registered source ID and `mode: "replay"` to `POST /api/v1/runs/start` with the local operator bearer token. Follow `GET /api/v1/runs/status` or the WebSocket `run_status` notifications.

During replay, `GET /api/v1/stream/annotated.mjpg` serves the latest annotated JPEG and ends at stop, EOF, or error. A browser served from the allowlisted origin should use a CORS-enabled `<img crossorigin="anonymous">` for the stream. To stop playback, send `{"run_id":"<run-id>"}` to `POST /api/v1/runs/stop` with the operator token. The worker stops cooperatively after any in-flight native decode or inference call returns.

The OpenCV FFmpeg reader checks the registered file's SHA-256 and prefers the decoded timestamp from `CAP_PROP_POS_MSEC`, relative to the first frame and rounded to milliseconds. If timestamps stall, regress, or are unavailable, it estimates time from the zero-based frame index and reported FPS while preserving a nondecreasing timecode. This estimate can drift on variable-frame-rate media. A failed first read or a read that falls short of a known frame count produces a decode error. After a successful read, OpenCV can report ordinary EOF and an undetectable truncation the same way when the file has no reliable frame count. Capture UTC stays null when the source supplies no verified capture time. Geographic coordinates require valid fixed-scene calibration.

The worker uses source time to pace playback when it can keep up. One JPEG slot serves all viewers. The transient observation queue holds the newest eight observations and drops the oldest on overflow. ByteTrack state is reset once at each run boundary, with IDs scoped to that run.

## Configure incident rules and geolocation

Set `ASTRA_ANALYSIS_CONFIG` to a trusted JSON file and restart the backend to apply changes. Geofences are configured through the API and snapshotted when a run starts. An empty analysis configuration still allows enabled geofences to use the default zone rule. The crowd rule is enabled per source.

```json
{
  "sources": {
    "your-source-id": {
      "crowd": {
        "threshold_count": 5,
        "clear_count": 3,
        "consecutive_frames": 3,
        "min_detector_confidence": 0.25,
        "cooldown_ms": 5000,
        "region_id": null
      },
      "zone": {
        "consecutive_frames": 3,
        "cooldown_ms": 5000,
        "track_expiry_ms": 2000
      },
      "retain_thumbnails": false
    }
  }
}
```

- Crowd confirmation uses unique person IDs at or above the confidence floor. It triggers only above `threshold_count` and rearms at or below `clear_count`. Set `region_id` to a returned, enabled image geofence ID to count within that region. `null` selects the entire frame.
- Zone entry requires an observed outside-to-inside transition of a person. Polygon boundaries count as inside. A missing observation interrupts confirmation. The last observed side survives until the configured track expiry. Both rules use video time for cooldown and require a new crossing after one is suppressed.
- Create and inspect geofences with `POST /api/v1/geofences` and `GET /api/v1/geofences?source_id=your-source-id`. POST requires the operator token. An image ROI uses `space_type: "image"`, the exact decoded `frame_size_px: [width, height]`, and a closed pixel-coordinate ring. A world fence uses `space_type: "world"`, `frame_size_px: null`, and a closed GeoJSON ring in longitude, latitude order. The worker ignores a fence on frames whose coordinate requirements are unmet. [Geofence schema](CONTRACTS.md#geographic-context-and-geofences)
- For an operator-verified stationary camera and planar ground, add `calibration` under the source entry. Supply `camera: "fixed"`, the registered `video_sha256`, `frame_size_px`, at least four paired `pixel_points` and `geo_points`, and optionally an inclusive `valid_for_frame_range`. Ground points are WGS 84 `[longitude, latitude]`. The file loader rejects degenerate or ill-conditioned fits, a horizon through the control area, and fits exceeding 2 px RMS or 4 px at an individual control. The fit is for a local scene within 2 km of the control centroid and away from the poles. The worker logs the pixel RMS and projects only within the control hull at the declared resolution and frame range. [OpenCV homography documentation](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html)
- Use pixel ROIs for moving or uncalibrated video. Image incidents carry `geo_status: "image_roi_only"` and `location: null`. Whole-frame crowd alerts have no world point. Render map markers only for calibrated incidents with a valid Point. Target uncertainty stays null because control-point reprojection error does not measure target-location uncertainty.
- Enable `retain_thumbnails` only when the source permits local evidence retention. Candidate thumbnails use the annotated confirmation frame and are bounded to 640 pixels on the long edge and 128 KiB. The demo keeps them in private SQLite for the verification session. Keep evidence runs in a disposable database for temporary retention, then dispose of that database at the end of verification. If there is no retained thumbnail, the incident has a null evidence URL.

### Optional real-inference smoke

Use the vision environment, a local trusted checkpoint, and a short permissioned MP4 with visible people or vehicles so the test can verify an ID across consecutive frames. This uses an isolated test database. With weights absent, the test reports a skip.

```powershell
$env:ASTRA_MODEL_WEIGHTS = 'D:\path\to\yolo26n.pt'
$env:ASTRA_INFERENCE_SMOKE_MP4 = 'D:\path\to\approved-short.mp4'
.\.venv\Scripts\python.exe -m pytest -q -s -m real_inference
```

```bash
ASTRA_MODEL_WEIGHTS=/path/to/yolo26n.pt ASTRA_INFERENCE_SMOKE_MP4=/path/to/approved-short.mp4 \
  .venv/bin/python -m pytest -q -s -m real_inference
```

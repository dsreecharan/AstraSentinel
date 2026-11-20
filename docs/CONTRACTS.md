# Astra Fly v1 API and event contracts

Use these names and semantics in Pydantic, FastAPI OpenAPI, and the TypeScript client. JSON keys use snake_case. Except where a field is marked optional, include it even when its value is `null`. Validate request models strictly. IDs are opaque strings except for the run-scoped track ID format below. Timestamps are ISO 8601 UTC strings with `Z`. Millisecond offsets are nonnegative integers.

## HTTP and streaming

| Method and path | Input | Success response |
| --- | --- | --- |
| `GET /api/v1/health` | — | `200 Health` |
| `GET /api/v1/sources` | — | `200 {items: Source[]}` |
| `POST /api/v1/runs/start` | `{source_id, mode: "replay"}` | `202 Run` with `status: "starting"` |
| `POST /api/v1/runs/stop` | `{run_id}` | `202 Run` with `status: "stopping"`, or `200 Run` if already terminal |
| `GET /api/v1/runs/status` | — | `200 {run: Run or null}` with the active run or most recently created run |
| `GET /api/v1/stream/annotated.mjpg` | Optional `run` query parameter pins the requested replay ID | `200 multipart/x-mixed-replace` stream of annotated JPEG frames for the matching current run |
| `GET /api/v1/incidents` | Optional `review_status`, `run_id`, `limit` (default 50, range 1–100), `offset` (default 0) | `200 {items: Incident[], total: integer}` filtered, newest first by `created_at` then `id` descending |
| `GET /api/v1/incidents/{id}` | — | `200 Incident` |
| `POST /api/v1/incidents/{id}/review` | `{decision: "acknowledged" or "dismissed", reason: string}` | `200 Incident` after commit |
| `GET /api/v1/incidents/{id}/audit` | — | `200 {items: AuditEntry[]}` in append order |
| `GET /api/v1/incidents/{id}/thumbnail` | — | `200 image/jpeg` for saved evidence |
| `GET /api/v1/geofences` | Optional `source_id` | `200 {items: Geofence[]}` |
| `POST /api/v1/geofences` | `GeofenceInput` | `201 Geofence` |
| `WS /ws/events` | Read-only browser connection with an allowed origin | JSON `EventEnvelope` messages |

All POSTs require `Authorization: Bearer <operator-token>` from local configuration. Resolve the actor to a stable operator label on the server and keep the credential out of URLs, logs, and the built frontend. Bind the demo to loopback and configure explicit UI origins for CORS and the WebSocket handshake. Serve video and evidence with `Cache-Control: no-store` and restrict cross-site embedding. Source registration, rule settings, and calibration use trusted local configuration. Keep runtime paths private and resolve source files under the allowed media directory, including symlink checks.

HTTP errors use `{error: {code: string, message: string}}`, including request validation errors. Codes below are stable for clients. Sanitize messages to avoid leaking local paths or secrets.

| Status | Code and condition |
| --- | --- |
| `401` | `unauthorized` for absent or invalid operator credentials |
| `404` | `source_not_found`, `run_not_found`, `incident_not_found`, or `evidence_unavailable` when the requested resource is unknown or the thumbnail is absent |
| `409` | `run_active` if a run already owns the worker or `review_conflict` if the incident has left `pending` |
| `422` | `validation_error` for malformed or invalid input |
| `503` | `frame_unavailable` if the requested run has no available frame or differs from the current frame's run. `storage_unavailable` if storage prevents the request from completing. |

## Source, health, and run

- **Source** has `id`, `title`, `video_sha256` (64 lowercase hex characters), `rights_note`, `attribution`, `license_url` (string or `null`), and `geo_mode` (`calibrated` or `unavailable`) describing configured calibration eligibility. Register new asset content under a new source ID so historical incidents retain provenance.
- **Health** has `status` (`ok` or `degraded`), `version` (application version), and `inference_status` (`not_started`, `loading`, `ready`, or `error`). Before the model is exercised, report `not_started`. HTTP readiness and model readiness are separate signals.
- **Run** has `id`, `source_id`, `mode` (always `replay`), `status`, `started_at`, `stopped_at` (timestamp or `null`), `error` (the HTTP error body's inner `{code, message}` object or `null`), and `model` (model provenance or `null` until verified). Model provenance has `name` (`yolo26n`), `weights_sha256`, `ultralytics_version`, and `tracker` (`bytetrack`).

Accepting a start records `starting` and `started_at`, then reserves the process's single worker. Enter `running` after video/model/tracker initialization succeeds. A stop transitions an active run through `stopping` to `stopped` and releases resources. Repeating a stop while stopping returns the same stopping run. A normal end of file transitions to `ended`. A worker failure transitions to `error`, with a sanitized error such as `model_unavailable`, `tracker_failed`, `video_unavailable`, or `decode_failed`. Set `stopped_at` for each terminal state (`stopped`, `ended`, `error`). Recognize interrupted active runs after restart and mark them `error` with `run_interrupted`. Snapshot rule settings, geofences, and calibration per run. A new run begins with fresh tracking and rule state.

The demo launcher requires one worker with reload disabled. The application acquires a per-database process lock before recovering interrupted runs. An invalid trusted rules/calibration file can prevent startup with `analysis_config_invalid`. An incompatible run configuration uses the same code in the run error. An invalid or unsupported MP4 codec uses `decode_failed` because OpenCV cannot always distinguish a missing decoder from damaged input. The latest JPEG is cleared when a stop is requested.

The MJPEG response supplies the latest annotated frame to each connection without a backlog. Mark it `REPLAY SOURCE` and end the response when its run terminates. Clear stale frames at run boundaries. Loading, input/model errors, and terminal states come from run status.

## Frame and track observation

`TrackObservation` is internal, transient, and versioned. It contains `schema_version` (`1.0`), `run_id`, `source_id`, `frame_index` (zero-based decoded frame index), `video_time_ms` (nondecreasing footage time), `captured_at` (source capture time or `null`), `processed_at` (processing time), `mode` (`replay`), `geo_status`, and `tracks` (array, possibly empty). Use a reliable file timestamp when available or document the frame-index/FPS estimate. Signal an explicit error if neither supplies a valid timebase.

Each track has `track_id` (`<run_id>:<tracker-local-id>`), `object_class` (`person` or `vehicle`), `detector_confidence` (finite number in [0, 1]), `bbox_xyxy` (four finite pixel coordinates with positive width and height), `bottom_center_px` (two finite pixel coordinates), `location` (Point or `null`), and `horizontal_error_m` (nonnegative measured uncertainty or `null`). Pixel origin is the top left, x rightward, y downward. Normalize supported vehicle classes at the adapter. Only results assigned a ByteTrack ID enter rule evaluation.

### Example observation

```json
{
  "schema_version": "1.0",
  "run_id": "run_demo_001",
  "source_id": "drone_replay_01",
  "frame_index": 120,
  "video_time_ms": 4000,
  "captured_at": null,
  "processed_at": "2026-11-20T13:05:00Z",
  "mode": "replay",
  "geo_status": "image_roi_only",
  "tracks": [
    {
      "track_id": "run_demo_001:7",
      "object_class": "person",
      "detector_confidence": 0.82,
      "bbox_xyxy": [122.0, 220.0, 165.0, 332.0],
      "bottom_center_px": [143.5, 332.0],
      "location": null,
      "horizontal_error_m": null
    }
  ]
}
```

## Geographic context and geofences

- A world `Point` is `{"type":"Point","coordinates":[longitude,latitude]}` using WGS 84 (SRID 4326 in a future PostGIS store). Validate finite longitude in [-180, 180] and latitude in [-90, 90]. [GeoJSON, RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)
- A frame's `geo_status` is `calibrated` when a validated calibration applies, `image_roi_only` when only configured pixel geometry applies, or `unavailable` otherwise. A single track can lack a valid ground intersection even in a calibrated frame.
- An incident is `calibrated` only when it has a valid world point. Use `image_roi_only` for incidents based on an image ROI and `unavailable` when neither a world point nor an image ROI describes the event. Both latter states require `location: null`. Use `horizontal_error_m: null` until measured uncertainty exists. The UI plots only calibrated incident points and displays image ROIs on the video.
- **GeofenceInput** has `source_id`, a nonempty `label`, `space_type` (`world` or `image`), `enabled` (boolean), `geometry` (`{type: "Polygon", coordinates: [[position, ...]]}`), and `frame_size_px` (`[width, height]` for image polygons, `null` for world polygons). **Geofence** adds `id`. Support a single closed, simple, nonzero-area exterior ring with at least three distinct vertices. World positions use longitude and latitude. Image positions use x and y pixels within the reference frame and remain image-coordinate data. Ignore a zone for frames where its resolution or coordinate requirements fail.
- **Calibration** has `id`, `source_id`, `method` (`homography`), `frame_size_px`, `pixel_points`, `geo_points`, `reprojection_error_px` (finite, nonnegative measured residual), and `valid_for_frame_range` (inclusive `[first_index, last_index]` or `null` for all frames of a verified stable source). Require at least four matched, nondegenerate pixel↔world control points, compatible resolution, a stable camera and a near-planar ground surface. Fit and validate in a suitable local ground coordinate system and convert the track footpoint to WGS 84 for output. Reject ill-conditioned fits and document the residual acceptance criteria. A fit residual alone supplies no target-uncertainty estimate. Camera GPS describes the camera.

## Rule candidates and incident records

Both rules use footage time for cooldowns and configurable consecutive-frame confirmation. Use run-local state and reset an interrupted confirmation on a missing frame or missing qualifying observation. Persist the relevant settings and measured values in `rule_details`. Candidate triggers carry a stable internal idempotency key based on the run, rule, scoped entity/region, and first qualifying frame of the crossing. A repeated key returns the existing incident without appending an audit row or broadcasting a duplicate.

Frame indices, counts, and cooldowns are nonnegative integers. `consecutive_frames` is the positive integer number of qualifying consecutive frames at confirmation. `min_detector_confidence` is a finite number in [0, 1]. `zone_id`, `region_id` (when present), and `track_id` are IDs.

| `event_type` | `rule_name` | `rule_details` and trigger |
| --- | --- | --- |
| `crowd_threshold` | `crowd_count_above_threshold` | `trigger_frame_index`, `person_count`, `threshold_count`, `clear_count`, `min_detector_confidence`, `consecutive_frames`, `cooldown_ms`, `region_id` (image geofence ID or `null` for whole frame). Count unique active person tracks at or above the confidence floor, using footpoint membership for the region when configured. Confirm when count stays strictly above `threshold_count`. Re-arm when count is at or below `clear_count` (lower than the configured threshold). Emit once per qualifying crossing outside cooldown. Use `location: null` for aggregate crowd alerts. |
| `zone_intrusion` | `restricted_zone_entry` | `trigger_frame_index`, `zone_id`, `track_id`, `consecutive_frames`, `cooldown_ms`. Confirm an observed outside→inside transition of a person's footpoint, including the polygon boundary as inside. Tracks first seen inside need an observed outside state before they become eligible. Use per-track/per-zone cooldown and re-arm on observed exit. A temporary missing observation interrupts confirmation and preserves the last stable inside/outside state until the track expires. Evaluate world zones only with a projected track point. |

`trigger_frame_index` refers to the confirmation frame, as do the incident `video_time_ms`, `observed_at`, and evidence image. `observed_at` comes from verified capture time when available, otherwise `null`. `created_at` is the server timestamp for creating the record. `severity` is always `review`. Evidence must come from the actual run and be bounded. When evidence is retained, return the relative thumbnail route. If the bounded thumbnail cannot be retained, use `evidence_url: null` and surface evidence unavailability.

### Example incident

```json
{
  "id": "inc_000042",
  "run_id": "run_demo_001",
  "source_id": "drone_replay_01",
  "event_type": "zone_intrusion",
  "severity": "review",
  "rule_name": "restricted_zone_entry",
  "rule_details": {
    "trigger_frame_index": 120,
    "consecutive_frames": 4,
    "cooldown_ms": 5000,
    "zone_id": "area_1",
    "track_id": "run_demo_001:7"
  },
  "video_time_ms": 4000,
  "observed_at": null,
  "created_at": "2026-11-20T13:05:00Z",
  "location": null,
  "geo_status": "image_roi_only",
  "horizontal_error_m": null,
  "evidence_url": "/api/v1/incidents/inc_000042/thumbnail",
  "review_status": "pending",
  "reviewer": null,
  "reviewed_at": null
}
```

## Review, audit, and delivery

- **Review.** Every incident starts `pending`. The only transitions are `pending → acknowledged` and `pending → dismissed`. Require a reason of 1–500 characters after trimming and derive `reviewer` from the authenticated operator. Set `reviewed_at` on transition. Concurrent or repeated attempts after the first commit receive `409 review_conflict` and can refetch. An acknowledgement records the operator's review decision.
- **Audit.** An `AuditEntry` has `id`, `incident_id`, `actor`, `action` (`created`, `acknowledged`, or `dismissed`), `reason` (string or `null`), and `created_at`. Append `created` with actor `system` and `reason: null` in the same transaction as incident creation. Append exactly one review audit row using the operator and supplied reason in the same transaction as the review update. Review conflicts and rolled-back writes leave the audit unchanged. Expose audit rows read-only.
- **Persistence.** Use source, run, incident, audit, geofence, and calibration entities with foreign keys. Store the unique candidate key, causal details, and evidence reference with the incident. Keep run model provenance and server-only source paths. SQLite is authoritative for reads and WebSocket recovery.

`EventEnvelope` is `{schema_version: "1.0", type: string, emitted_at: timestamp, data: object}`. The first message is `ready` with `data: {}` after subscription is installed. Domain messages are notifications of committed state:

| `type` | `data` |
| --- | --- |
| `candidate_incident` | `{incident_id, run_id, source_id}` after creation and its audit row commit |
| `incident_reviewed` | `{incident_id, run_id, source_id}` after review and its audit row commit |
| `run_status` | `{run_id, source_id, status}` after a run transition commits |

```json
{
  "schema_version": "1.0",
  "type": "candidate_incident",
  "emitted_at": "2026-11-20T13:05:00Z",
  "data": {
    "incident_id": "inc_000042",
    "run_id": "run_demo_001",
    "source_id": "drone_replay_01"
  }
}
```

Use a thread-safe handoff from the worker to the event loop and bound subscriber queues. Close a slow subscriber on overflow with WebSocket code `1013`. The client connects with backoff after a disconnect, waits for `ready`, then reloads incident and run status from REST. Ignore notifications and callbacks from replaced or closed sockets. Treat accepted events as invalidations and refetch affected state. If a notification arrives during a refresh, schedule another refresh after it finishes. Use REST whenever the client needs the current state or recovers from a missed notification. Keep video, per-frame detections, and raw footage off this channel.

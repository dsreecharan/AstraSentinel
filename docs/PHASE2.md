# Optional Phase 2 runbook

The default remains the SQLite, MP4, and annotated MJPEG stack in the [MVP runbook](SMOKE_TEST.md). Start the backend and frontend on the host as before. Docker, Psycopg, and MAVSDK are optional. These profiles keep the v1 incident, review, audit, and WebSocket contracts.

## Media profile

From the repo root, copy `.env.phase2.example` to ignored `.env.phase2` and set `ASTRA_MEDIA_PUBLISH_PASSWORD` to a distinct random URL-safe secret. Start MediaMTX with Docker Compose v2.

```powershell
docker compose --env-file .env.phase2 -f compose.phase2.yml --profile media up -d --wait
```

| Endpoint | Host binding and policy |
| --- | --- |
| `rtsp://127.0.0.1:8554/monitor` | RTSP over TCP. User `publisher` needs the configured password to publish to this one path. Existing publishers own the path until disconnect. Local RTSP readers may subscribe. |
| [WebRTC player](http://127.0.0.1:8889/monitor/) | Loopback HTTP player and WHEP on TCP 8889. ICE on loopback UDP/TCP 8189, with a TCP fallback and no public STUN/TURN servers. |
| [HLS player](http://127.0.0.1:8888/monitor/) | Loopback HTTP fragmented MP4 HLS, with a three-segment rolling window and one-second keyframe target. |

Browser playback is local and anonymous. Protect access to the host and its Docker daemon. RTMP, SRT, MoQ, recording, and the control API are disabled. The health check reads a metrics endpoint inside the container. It checks process readiness independently of the publisher. [MediaMTX configuration reference](https://mediamtx.org/docs/references/configuration-file) · [MediaMTX browser players](https://mediamtx.org/docs/read/web-browsers)

Publish an approved file from a local FFmpeg with `libx264`. Use H.264 constrained baseline, 8-bit `yuv420p`, no B-frames, no audio, and 10 FPS with a keyframe every ten frames. Enter the private password into the variable `$PublishPassword` without printing it.

```powershell
ffmpeg -re -i 'data/demo_video/approved.mp4' -an -vf fps=10 -c:v libx264 -pix_fmt yuv420p -profile:v baseline -preset ultrafast -tune zerolatency -bf 0 -g 10 -f rtsp -rtsp_transport tcp "rtsp://publisher:${PublishPassword}@127.0.0.1:8554/monitor"
```

For a browser comparison, keep the publisher running while you open both players, or run the browser check below. Use a permissioned clip long enough for both connections. Stop FFmpeg with Ctrl+C.

Set `VITE_RTSP_MONITOR=true` in the frontend environment and rebuild or restart Vite to display links in the dashboard's Video panel. The links open the MediaMTX player as **media only**. The MVP inference worker continues to process registered MP4 replays and serve its own annotated MJPEG. The external feed has no inferred tracks or incident linkage in this profile.

## PostGIS profile

Set `ASTRA_POSTGIS_PASSWORD` in the same ignored Compose file. You can start PostGIS without the media profile.

```powershell
docker compose --env-file .env.phase2 -f compose.phase2.yml --profile postgis up -d --wait
Set-Location backend
uv sync --locked --extra test --extra vision --extra postgis --python 3.11 --no-python-downloads
# Read the locally configured password privately. Reserve alphanumeric secrets for this example.
$env:ASTRA_POSTGIS_URL = "postgresql+psycopg://astra:${PostgisPassword}@127.0.0.1:55432/astra_phase2"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.serve
```

A nonempty `ASTRA_POSTGIS_URL` selects its own PostgreSQL store. Register sources for that profile with the existing `python -m app.seed_source` path. Keep source files in their normal host allowlist. The loopback port requires database credentials. The example uses the development container's database owner. The SQLite and PostGIS stores are separate and start with independent history. To return to SQLite, stop the backend, remove that setting in the backend shell and its environment file, and start it again. SQLite migration `0003` advances the revision without changing its tables.

PostGIS generates and indexes two native columns from the validated v1 GeoJSON. Incident points and world geofence polygons are WGS 84 `geometry` with SRID 4326 and longitude first. Image-space data has a null native geometry. Use `ST_Covers` for containment and cast to `geography` if a future query needs metre distances. Generated geometry and the GiST indexes are managed by the migration. HTTP responses keep their existing GeoJSON shape. PostgreSQL retains idempotent inserts, the append-only audit trigger, and a per-database worker lock. [PostGIS container documentation](https://github.com/postgis/docker-postgis)

## Optional simulator telemetry

Install `--extra telemetry` in the backend environment. Use PX4 SITL with Gazebo installed independently, with MAVLink simulator datagrams delivered to UDP `127.0.0.1:14540` on the machine or environment running the receiver. Run the adapter alongside the simulator so its loopback address is meaningful. [PX4 simulation setup](https://docs.px4.io/main/en/simulation/) · [MAVSDK connection syntax](https://mavsdk.mavlink.io/main/en/cpp/guide/connections.html)

```powershell
.\.venv\Scripts\python.exe -m app.telemetry --port 14540 --timeout 5
```

The command takes one read-only sample labeled `simulator_vehicle` and releases its socket. A bounded discovery timeout and a bounded GPS receive timeout apply separately. The default reports UTC receipt and a local monotonic receipt clock and preserves the device's raw microsecond value. With `--expect-source-utc`, enable source wall time only after confirming the simulator emits epoch values. The adapter accepts a plausible epoch value within five seconds of receipt and leaves quantified alignment uncertainty null. A positive finite horizontal uncertainty reported by MAVSDK is carried as vehicle uncertainty. Missing uncertainty stays null. GPS fix qualification and camera synchronization are outside this diagnostic path. The command does not arm, fly, or authorize a flight, and the sample cannot enter incident geolocation. [MAVSDK raw GPS fields](https://mavsdk.mavlink.io/main/en/cpp/api_reference/structmavsdk_1_1_telemetry_1_1_raw_gps.html)

## Integration checks and cleanup

From `backend/`, point `ASTRA_TEST_POSTGIS_URL` to the local disposable Compose profile. The test requires permission to create and drop a fresh scratch database. Keep `ASTRA_POSTGIS_URL` unset while running the suite so standard tests use SQLite. Set `ASTRA_TEST_MEDIA_CONTAINER` to the MediaMTX container name from `docker compose ps` and `ASTRA_TEST_TELEMETRY=1` to enable the native UDP test. The optional `ASTRA_TEST_DOCKER_COMMAND` accepts a JSON argument array for a host with a WSL Docker CLI.

```powershell
.\.venv\Scripts\python.exe -m pytest -q -rs -s -m phase2
```

The media test publishes a finite synthetic H.264 fixture, checks credential enforcement, probes RTSP stream properties, and reads the HLS playlist. The separate browser check measures navigation to decoded and advancing video. With a publisher running, run the following from the root. The browser tooling installs into a temporary directory.

```powershell
$CheckTools = Join-Path $env:TEMP 'astra-phase2-browser-tools'
npm.cmd install --prefix $CheckTools --save-exact playwright-core@1.65.1
$env:ASTRA_PLAYWRIGHT_MODULE = Join-Path $CheckTools 'node_modules/playwright-core'
$env:ASTRA_BROWSER_EXECUTABLE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
node.exe scripts/check_media.cjs
```

The storage comparison uses 30 measured create-and-review operations after five warm-ups for each profile. It reports service-level transaction timing, including the audit writes. The browser timing starts on player navigation and ends at advancing decoded video, using an already-publishing source. Camera-to-display latency remains unmeasured. [Measured results](STATUS.md#prompt-8-phase-2-verification)

Stop the app and publisher before shutting down the services. The command below preserves the PostGIS volume. Remove it only for a deliberately disposable verification stack.

```powershell
docker compose --env-file .env.phase2 -f compose.phase2.yml --profile media --profile postgis down
```

## Event transport

The media server and PostGIS profiles introduce infrastructure services. Astra Fly still has one incident producer with REST backed by committed database state and an in-process WebSocket broker. Redis Streams is deferred until an application service needs cross-process durable delivery. At that point use an outbox committed with incident changes, consumer groups with acknowledgments after idempotent processing, bounded retries and dead-letter recovery. REST continues to reconstruct the UI after reconnect.

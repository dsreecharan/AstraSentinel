# Architecture and limitations

Astra Fly is a loopback hackathon prototype for human review of rule candidates during prerecorded replay.

```mermaid
flowchart LR
    MP4[Licensed local MP4] --> Decode[OpenCV decode and footage clock]
    Decode --> Vision[YOLO26n and ByteTrack]
    Vision --> Rules[Run-local geography and rules]
    Rules --> Evidence[Latest annotated JPEG and optional confirmation thumbnail]
    Rules --> SQLite[SQLite incident and creation audit]
    Evidence --> UI[React dashboard]
    SQLite --> Delivery[REST and WebSocket notifications]
    Delivery --> UI
    UI --> Review[Authenticated decision and reason]
    Review --> SQLite
```

- One lifecycle-owned worker validates the source path and checksum, runs one model on sequential frames, and resets tracker and rule state on replay restart. Frames carry footage time and track IDs scoped to one run. The worker uses a latest-frame store and a bounded transient observation queue. EOF ends the replay and stop clears the stream.
- The crowd rule counts accepted anonymous person tracks over consecutive frames and uses hysteresis and cooldown. The zone rule requires an observed outside-to-inside crossing and confirms over configured frames. These are deterministic rule candidates with causal fields for the operator.
- SQLite is authoritative. The service commits a candidate with its creation audit entry before notifying subscribers. A unique key deduplicates retries. A review updates a pending incident and appends the reason in one transaction. The client waits for `ready` after reconnect, then fetches current state from REST. A run-pinned stream cannot switch to a later replay.
- Image ROIs remain pixel coordinates. World points require a checksum-bound fixed-scene calibration, matching resolution, and a valid ground projection. A report of an image-space alert carries null geographic location and uncertainty. The prior browser demo exercised a world geofence with test-only controls. A surveyed site is still unverified.
- The optional confirmation thumbnail is stored privately with the incident. It is off by default. Raw video stays in the registered source directory. Per-frame detections remain transient and the saved visual evidence is one bounded thumbnail per incident. [Data provenance and retention](../data/README.md)

## Interpretation and deployment limits

- The licensed aerial excerpt validated vehicle tracking and the media path. Both alert rules were demonstrated separately on a controlled NASA-still composite. Performance on real aerial crowds remains unmeasured.
- Field accuracy, capture-to-alert latency, geographic uncertainty, and deployment reliability remain unmeasured. Ground-truth tracking labels are unavailable. Unpaced CPU figures measure the local workload documented with the results. [Benchmark methods](BENCHMARKS.md)
- Anonymous tracks provide local temporal continuity. Human review is the only decision path. Facial identification, cross-source identity linkage, and automated enforcement are outside the MVP scope.
- Token auth, SQLite, one process, and loopback access match the demonstration scope. Evaluate access, retention, permission, and applicable law before any real-world use. The team still needs to resolve integrated distribution terms and verify release rights for the chosen captures. [Submission checklist](SUBMISSION_CHECKLIST.md)

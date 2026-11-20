# Astra Fly submission checklist

## Source, demo, and verification

- [x] Repository contents include setup instructions, environment template, contract, Python and npm lockfiles, and test fixtures. [README](../README.md)
- [x] Clean dependency installs from the locked Windows cache passed. The local smoke workflow has a reproducible isolated source, rules, token, and SQLite setup. [System smoke test](SMOKE_TEST.md)
- [x] Verified local replay, real YOLO26n and ByteTrack, actual controlled incidents, human review with a reason, and persistent audit after restart. [Three-minute walkthrough](DEMO_SCRIPT.md)
- [x] Verified per-component CPU benchmark on the two documented inputs. [Methods and commands](BENCHMARKS.md) · [Measured results and exact verification output](STATUS.md#prompt-7-benchmark-and-submission-verification)
- [x] Local screenshots and a recording cover the demonstrated path. Keep the **recorded prior replay** label on the fallback.
- [x] Select the source repository and use the submitted `main` commit SHA as the revision. [AstraSentinel](https://github.com/dsreecharan/AstraSentinel)
- [ ] Resolve the team's Ultralytics distribution license and gather corresponding source and notices as applicable. Confirm the exact assets, recordings, and screenshots approved for submission. [Provenance and license inventory](../data/README.md#provenance-and-release-inventory)
- [ ] Complete the slides or PDF from the outline below using the approved captures. Check readability at projector size and test the links in the final packet.

## Hardware and measured workload

Intel Core 7 240H (10 cores / 16 logical), 15.61 GiB RAM, Windows 11 build 26300. Python 3.11.0, OpenCV 4.14.0, YOLO26n on CPU at 640 with ByteTrack, batch one, eight warm-up frames per input. Both MP4s report 10 source FPS. The laptop has an RTX 5050 with 8,151 MiB reported VRAM. Device snapshots are in the measurement log.

| Offline workload | Measured frames | Decode-only file-read FPS | Warmed local pipeline FPS | Mean frame read → local incident commit |
| --- | ---: | ---: | ---: | ---: |
| Licensed aerial traffic, 1080×1920 | 40 | 172.033 | 21.578 | Unmeasured. The run emitted zero candidates. |
| Controlled NASA-still composite, 1152×512 | 45 | 708.782 | 32.357 | 50.154 ms across two candidates |

The controlled latency starts on the confirmation frame. Capture-to-alert, external network latency, detector accuracy, and surveyed geolocation are unmeasured. [Metric boundaries](BENCHMARKS.md#metric-boundaries)

## Slides or PDF outline

1. **Problem and scope.** Approved prerecorded replay, anonymous tracking, and operator review for explainable candidates.
2. **MVP architecture.** MP4 → OpenCV → YOLO26n and ByteTrack → rules → SQLite → REST/WebSocket → dashboard → review and audit. Show a diagram from the architecture document.
3. **Evidence from the demo.** Show the real aerial replay with zero incidents and the separately labeled controlled replay. Explain the crowd threshold and image-zone entry using the actual thumbnail, timecode, and rule measurements.
4. **Operator workflow and reliability.** Show the saved reason and audit after restart. Explain single-worker ownership, idempotent commits, and REST recovery.
5. **Benchmark.** Give hardware, clip dimensions, sample sizes, CPU workload, and the timing boundaries. Include results from the table and note the two-sample alert timing.
6. **Privacy, geospatial, and release.** Explain anonymous run IDs, optional bounded thumbnails, human review, image-space uncertainty, asset credits, and the remaining release decision.

## Ethical and legal limits to state

- Candidates are evidence for human review. Training, deployment, and accuracy claims require evidence from an appropriate authorized dataset.
- Tracking is anonymous and scoped to one replay. Facial identification, cross-source identity linkage, and automated enforcement are outside scope.
- Define image ROIs in pixels and disclose unavailable world coordinates or uncertainty. A moving aerial camera requires a separate verified projection method before geographic inference.
- Use footage with permission for the planned processing, display, and distribution. Keep private video, credentials, and review evidence out of the source packet. Retain only authorized evidence for the agreed period. [Source provenance and retention](../data/README.md)
- The demo uses a loopback token, one SQLite process, and a local MapLibre style. Real deployments require a separate assessment of purpose, authorization, privacy, and legal obligations. [Architecture and limitations](ARCHITECTURE.md)

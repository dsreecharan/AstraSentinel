# CPU benchmark

`scripts/benchmark.py` profiles the implemented pipeline in offline, unpaced mode. It uses the same OpenCV reader, YOLO26n and ByteTrack adapter, replay rules, JPEG code, and incident service as the demo. A migrated temporary SQLite database receives actual candidates and optional confirmation evidence. Closing the run removes the database and any benchmark-only evidence. Network, server delivery, and browser rendering are outside this command.

## Reproduce on Windows

From the repository root, use the locked Python vision environment. The smoke runbook prepares the controlled MP4, the analysis JSON, and the pixel-zone input. Use a new output directory for each report. [Clean setup and source files](SMOKE_TEST.md)

```powershell
$Python = '.\backend\.venv\Scripts\python.exe'
$Demo = Join-Path (Get-Location).Path 'data/evidence/prompt6-run'
$Results = Join-Path (Get-Location).Path 'data/evidence/prompt7-measurement'
New-Item -ItemType Directory -Path $Results
& $Python scripts/benchmark.py --video 'data/demo_video/aerial-intersection-validation.mp4' --warmup 8 --frames 300 --output (Join-Path $Results 'aerial.json')
& $Python scripts/benchmark.py --source-id controlled-rule-verification --video (Join-Path $Demo 'media/controlled-two-tracks.mp4') --rules (Join-Path $Demo 'rules.json') --geofence (Join-Path $Demo 'zone.json') --warmup 8 --frames 300 --output (Join-Path $Results 'controlled.json')
```

Supply `--weights` to select a different trusted local **YOLO26n** checkpoint. A benchmark uses batch one and CPU with `imgsz=640`. It runs a separate decode-only pass, warms the model with eight input frames, resets ByteTrack, reopens the file and measures from frame 0 with fresh rule state. It records the actual warm-up count and stops at EOF or the configured frame limit. The checksum and package versions are in each JSON report. Run the two commands sequentially and record any competing load if extending the study.

## Metric boundaries

| Metric | What was timed |
| --- | --- |
| Decode-only file-read FPS | Successful decoded frames divided by the sum of timed OpenCV file reads in a pass without inference. These reads include demux, decode and the footage clock. File-open, hashing and the unsuccessful EOF call are excluded. This is a read-and-decode rate on the OS cache available during the run. |
| Decode milliseconds per frame | The same successful read operation measured again inside the inference pipeline. |
| Inference milliseconds per frame | Ultralytics batch-one forward time from `Results.speed`. Preprocessing, postprocessing and ByteTrack run outside this timer. |
| Tracking milliseconds per frame | Wall time inside the actual `BYTETracker.update` call. Vendor result conversion and wrapper overhead are outside this timer. |
| Geospatial and rule milliseconds | Wall time inside `ReplayAnalysis.process`. Observation construction is outside this timer. |
| Processed FPS | Processed frames divided by the unpaced loop wall time. Includes reading, preprocessing, forward pass, postprocessing, tracking, rules, JPEG encoding, any thumbnail and SQLite work, and loop/resource-sampling overhead. Model setup, warm-up, pacing, and network delivery are excluded. |
| Local alert generation | Time from the start of the **confirmation frame's** read to an in-memory candidate, and separately to durable SQLite commit. Earlier frames needed for rule confirmation are outside both timers. With no candidates these metrics are null. |
| CPU and RAM | Benchmark-process CPU time normalized across reported logical cores. Resident memory is sampled before and after processed frames. The observed maximum is the peak sampled RSS. |
| GPU and VRAM | If available, `nvidia-smi` supplies device-wide utilization and VRAM snapshots before and after the measured pass. These are host-device snapshots on a CPU workload. |

The JSON includes sample count, mean, median, and nearest-rank p95 for per-frame stages and candidate latencies. An alert p95 from two samples conveys very little about repeatability. The controlled composite is a rule exercise. Detector mAP, production-network latency, and capture-to-alert latency are unmeasured. [Actual hardware and CPU results](STATUS.md#prompt-7-benchmark-and-submission-verification)

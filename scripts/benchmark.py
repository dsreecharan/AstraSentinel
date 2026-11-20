"""Measure the local Astra Fly replay pipeline on a permissioned MP4."""

import argparse
import csv
import json
import math
import os
import platform
import shutil
import sqlite3
import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from statistics import mean, median
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns

from smoke_test import ROOT, migrate

import cv2
import psutil
from sqlalchemy.orm import sessionmaker

from app.analysis.config import AnalysisSettings, SourceAnalysis
from app.analysis.replay import ReplayAnalysis
from app.contracts.events import Source
from app.contracts.geo import Geofence, GeofenceInput
from app.db.models import GeofenceRow
from app.db.runs import RunStore
from app.db.session import sqlite_engine
from app.media import file_sha256, resolve_mp4
from app.seed_source import register_source
from app.services.events import EventBroker
from app.services.incidents import IncidentService
from app.vision.frames import annotate_frame, evidence_thumbnail, frame_jpeg
from app.vision.source import OpenCVVideoSource
from app.vision.ultralytics_adapter import DEVICE, IMAGE_SIZE, TRACKER_CONFIG, UltralyticsAdapter
from app.vision.worker import observation_for

MIB = 1024 ** 2


def duration_ms(start_ns: int) -> float:
    return (perf_counter_ns() - start_ns) / 1_000_000


def summary(values: list[float]) -> dict | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "samples": len(values), "mean_ms": round(mean(values), 3), "p50_ms": round(median(values), 3),
        "p95_ms": round(ordered[math.ceil(0.95 * len(values)) - 1], 3),
    }


def cpu_name() -> str:
    if platform.system() == "Windows":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    if platform.system() == "Linux":
        try:
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    return line.partition(":")[2].strip()
        except OSError:
            pass
    return platform.processor() or platform.machine()


def gpu_snapshot() -> list[dict] | None:
    program = shutil.which("nvidia-smi")
    if program is None:
        return None
    try:
        result = subprocess.run([
            program, "--query-gpu=name,driver_version,utilization.gpu,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ], check=True, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return [
        {"name": name, "driver": driver, "utilization_pct": int(util) if util.isdecimal() else None,
         "vram_used_mib": int(used) if used.isdecimal() else None,
         "vram_total_mib": int(total) if total.isdecimal() else None}
        for name, driver, util, used, total in csv.reader(result.stdout.splitlines(), skipinitialspace=True)
    ]


def read_fences(files: list[Path], source_id: str) -> tuple[Geofence, ...]:
    fences = []
    for index, path in enumerate(files):
        data = json.loads(path.read_bytes())
        if isinstance(data, dict) and "id" not in data:
            data = GeofenceInput.model_validate(data).model_dump()
            data["id"] = f"benchmark-zone-{index + 1}"
        fence = Geofence.model_validate(data)
        if fence.source_id != source_id:
            raise ValueError("Geofence source_id must match the benchmark source ID")
        fences.append(fence)
    return tuple(fences)


def decode_probe(reader, frame_limit: int) -> dict:
    samples = []
    with reader() as source:
        for _ in range(frame_limit):
            started = perf_counter_ns()
            frame = source.read()
            if frame is None:
                break
            samples.append(duration_ms(started))
        return {
            "frames": len(samples), "source_fps": source.source_fps,
            "file_read_fps": round(1000 * len(samples) / sum(samples), 3) if samples else None,
            "read_decode_ms": summary(samples),
        }


def measure_pipeline(args, reader, digest: str, settings: SourceAnalysis, fences: tuple[Geofence, ...], database: Path) -> dict:
    migrate(database)
    engine = sqlite_engine(database)
    try:
        return measure_with_storage(args, reader, digest, settings, fences, sessionmaker(engine))
    finally:
        engine.dispose()


def measure_with_storage(args, reader, digest: str, settings: SourceAnalysis, fences: tuple[Geofence, ...], sessions) -> dict:
    source = Source(id=args.source_id, title=args.video.name, video_sha256=digest, attribution="Local benchmark input",
                    rights_note="Permissioned input supplied by the operator", geo_mode="unavailable", license_url=None)
    register_source(sessions, source, args.video)
    with sessions.begin() as session:
        session.add_all(GeofenceRow(**fence.model_dump()) for fence in fences)
    runs = RunStore(sessions)
    run, asset = runs.create(source.id)
    incidents = IncidentService(sessions, EventBroker())

    adapter = UltralyticsAdapter(args.weights)
    model = adapter.start_run("benchmark-warmup")
    warmup_frames = 0
    with reader() as capture:
        for _ in range(args.warmup):
            frame = capture.read()
            if frame is None:
                break
            adapter.track(frame.image)
            warmup_frames += 1
    if warmup_frames == 0:
        raise RuntimeError("The video did not provide a warm-up frame")

    adapter.start_run(run.id)
    analysis = ReplayAnalysis(run.id, digest, settings, asset.geofences)
    runs.transition(run.id, "running", model=model)
    timings = defaultdict(list)
    alerts = []
    frames = 0
    frames_with_tracks = 0
    max_tracks = 0
    process = psutil.Process()
    rss = []
    gpu_before = gpu_snapshot()

    with reader() as capture:
        rss.append(process.memory_info().rss)
        started = perf_counter_ns()
        cpu_started = process_time_ns()
        for _ in range(args.frames):
            frame_start = perf_counter_ns()
            frame = capture.read()
            if frame is None:
                break
            timings["read_decode"].append(duration_ms(frame_start))
            detections, vision = adapter.track_timed(frame.image)
            timings["inference_forward"].append(vision.inference_ms)
            timings["bytetrack_update"].append(vision.tracking_ms)
            height, width = frame.image.shape[:2]
            observation = observation_for(run, frame, detections)
            rule_start = perf_counter_ns()
            result = analysis.process(observation, (width, height))
            timings["geo_and_rules"].append(duration_ms(rule_start))
            if result.candidates:
                timings["frame_read_to_candidate"].extend([duration_ms(frame_start)] * len(result.candidates))

            annotated = annotate_frame(frame.image, detections, result.image_regions, len(result.candidates))
            frame_jpeg(annotated)
            thumbnail = evidence_thumbnail(annotated) if result.candidates and analysis.retain_thumbnails else None
            for candidate in result.candidates:
                incident = incidents.publish_incident(candidate, thumbnail)
                timings["frame_read_to_incident_commit"].append(duration_ms(frame_start))
                alerts.append({
                    "event_type": incident.event_type, "video_time_ms": incident.video_time_ms,
                    "geo_status": incident.geo_status, "has_thumbnail": incident.evidence_url is not None,
                })
            track_count = len(result.observation.tracks)
            frames_with_tracks += int(track_count > 0)
            max_tracks = max(max_tracks, track_count)
            frames += 1
            rss.append(process.memory_info().rss)
        cpu_seconds = (process_time_ns() - cpu_started) / 1_000_000_000
        wall_seconds = duration_ms(started) / 1000

    if frames == 0:
        raise RuntimeError("The measured pass processed zero frames")
    gpu_after = gpu_snapshot()
    runs.transition(run.id, "ended" if frames < args.frames else "stopped")
    cpu_one_core_pct = 100 * cpu_seconds / wall_seconds
    timing_names = ("read_decode", "inference_forward", "bytetrack_update", "geo_and_rules",
                    "frame_read_to_candidate", "frame_read_to_incident_commit")
    return {
        "model": {**model.model_dump(), "filename": args.weights.name},
        "input_size_px": [width, height], "warmup_frames": warmup_frames, "frames": frames,
        "frames_with_tracks": frames_with_tracks, "max_tracks_in_frame": max_tracks,
        "processed_fps": round(frames / wall_seconds, 3), "wall_seconds": round(wall_seconds, 6),
        "latency": {name: summary(timings[name]) for name in timing_names}, "alerts": alerts,
        "resources": {
            "process_cpu_seconds": round(cpu_seconds, 6), "process_cpu_pct_one_logical_core": round(cpu_one_core_pct, 2),
            "process_cpu_pct_all_logical_cores": round(cpu_one_core_pct / (psutil.cpu_count() or 1), 2),
            "process_rss_start_mib": round(rss[0] / MIB, 2), "process_rss_peak_sampled_mib": round(max(rss) / MIB, 2),
            "gpu_device_before": gpu_before, "gpu_device_after": gpu_after,
        },
    }


def benchmark(args) -> dict:
    args.video = resolve_mp4(args.video.resolve().parent, args.video.resolve())
    args.source_id = args.source_id or args.video.stem
    digest = file_sha256(args.video)
    fences = read_fences(args.geofence, args.source_id)
    settings = AnalysisSettings.read(args.rules).sources.get(args.source_id, SourceAnalysis()) if args.rules else SourceAnalysis()

    def reader():
        return OpenCVVideoSource(args.video.parent, args.video, digest)

    decode = decode_probe(reader, args.frames)
    with TemporaryDirectory(prefix="astra-benchmark-") as folder:
        os.environ.setdefault("YOLO_CONFIG_DIR", str(Path(folder) / "vision-config"))
        os.environ["YOLO_VERBOSE"] = "false"
        pipeline = measure_pipeline(args, reader, digest, settings, fences, Path(folder) / "benchmark.sqlite3")

    ultralytics = metadata.distribution("ultralytics")
    tracker_path = Path(ultralytics.locate_file(f"ultralytics/cfg/trackers/{TRACKER_CONFIG}"))
    return {
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "mode": "offline_unpaced_local_pipeline", "batch_size": 1, "device": DEVICE, "model_imgsz": IMAGE_SIZE,
        "scope": "MP4 read to local SQLite commit and in-memory JPEG. Browser, network and capture timing are excluded.",
        "source": {"id": args.source_id, "filename": args.video.name, "sha256": digest, "bytes": args.video.stat().st_size},
        "configuration": {
            "frame_limit": args.frames, "warmup_requested": args.warmup, "crowd": settings.crowd.model_dump() if settings.crowd else None,
            "zone": settings.zone.model_dump(), "geofences": [fence.model_dump() for fence in fences],
            "fixed_calibration": settings.calibration is not None, "thumbnails_enabled": settings.retain_thumbnails,
            "rules_file_sha256": file_sha256(args.rules) if args.rules else None,
        },
        "hardware": {
            "os": platform.platform(), "cpu": cpu_name(), "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(), "system_ram_mib": round(psutil.virtual_memory().total / MIB, 2),
        },
        "runtime": {
            "python": platform.python_version(), "sqlite": sqlite3.sqlite_version, "opencv": cv2.__version__,
            "packages": {package: metadata.version(package) for package in
                         ("opencv-python", "ultralytics", "torch", "torchvision", "lap", "psutil", "numpy", "sqlalchemy")},
            "tracker_config_sha256": file_sha256(tracker_path),
        },
        "decode_probe": decode, "pipeline": pipeline,
    }


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--weights", type=Path, default=ROOT / "YOLO26/yolo26n.pt")
    parser.add_argument("--source-id")
    parser.add_argument("--rules", type=Path, help="Existing source-indexed analysis JSON")
    parser.add_argument("--geofence", type=Path, action="append", default=[], help="Geofence input or API response JSON")
    parser.add_argument("--warmup", type=positive_int, default=8)
    parser.add_argument("--frames", type=positive_int, default=300, help="Maximum frames after warm-up")
    parser.add_argument("--output", type=Path, help="New JSON output file. Output is also printed to stdout.")
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("--output must be a new file")
    try:
        result = json.dumps(benchmark(args), indent=2, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as output:
                output.write(result)
        print(result, end="")
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Benchmark failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

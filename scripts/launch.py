"""Start both configured MVP servers from the Windows launcher."""

import argparse
import json
import msvcrt
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from tempfile import mkdtemp
from urllib.request import ProxyHandler, build_opener

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VITE = FRONTEND / "node_modules/vite/bin/vite.js"
HOST = "127.0.0.1"
API_URL = f"http://{HOST}:8000"
DEFAULT_DASHBOARD = "http://localhost:5173"
LOCAL_HTTP = build_opener(ProxyHandler({}))


def prepare_judge() -> Path:
    from smoke_test import prepare

    from app.runtime import exclusive_worker

    evidence = ROOT / "data/evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    env_file = evidence / "judge.env"
    with exclusive_worker(evidence / "judge-preparation"):
        if env_file.is_file():
            return env_file
        default_weights = ROOT / "data/weights/yolo26n.pt"
        if not default_weights.is_file():
            default_weights = ROOT / "YOLO26/yolo26n.pt"
        weights = ROOT / os.getenv("ASTRA_MODEL_WEIGHTS", str(default_weights))
        if not weights.is_file():
            raise RuntimeError("Place the licensed YOLO26n checkpoint at data/weights/yolo26n.pt. See README.md.")
        stage = Path(mkdtemp(prefix="judge-", dir=evidence)) / "replay"
        prepare(stage, ROOT / "data/samples/astronaut.png", weights, judge=True)
        (stage / ".env").replace(env_file)
    return env_file


def ensure_running(services: dict[str, subprocess.Popen]) -> None:
    for name, process in services.items():
        if (code := process.poll()) is not None:
            raise RuntimeError(f"{name} stopped with exit code {code}. See its output above.")


def wait_for_servers(services: dict[str, subprocess.Popen]) -> None:
    pending = {"Backend": f"{API_URL}/api/v1/health", "Dashboard": f"http://{HOST}:5173"}
    deadline = time.monotonic() + 30
    while pending and time.monotonic() < deadline:
        ensure_running(services)
        for name, url in list(pending.items()):
            try:
                with LOCAL_HTTP.open(url, timeout=1) as response:
                    if response.status == 200:
                        del pending[name]
            except OSError:
                continue
        if pending:
            time.sleep(0.15)
    ensure_running(services)
    if pending:
        raise RuntimeError(f"Timed out waiting for {' and '.join(pending)}. See the server output above.")

    try:
        with LOCAL_HTTP.open(f"{API_URL}/api/v1/sources", timeout=3) as response:
            sources = json.load(response)["items"]
    except (OSError, ValueError, KeyError):
        raise RuntimeError("Could not read replay sources. Check the SQLite database and migrations in README.md.") from None
    if not sources:
        raise RuntimeError("No replay sources are registered. Follow the demo or source setup in README.md.")


def stop_services(services: dict[str, subprocess.Popen]) -> None:
    for process in services.values():
        if process.poll() is None:
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
            except OSError:
                process.terminate()
    for process in services.values():
        try:
            process.wait(timeout=12)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="Use an existing replay configuration instead of the default judge demo")
    parser.add_argument("--check", action="store_true", help="Check startup and stop both servers without opening a browser")
    args = parser.parse_args()
    services: dict[str, subprocess.Popen] = {}
    try:
        node = shutil.which("node.exe")
        if not node or not VITE.is_file():
            raise RuntimeError("Install Node.js 24 and run npm.cmd ci from frontend. See README.md.")
        for port in (8000, 5173):
            with socket.socket() as probe:
                probe.settimeout(0.5)
                if probe.connect_ex((HOST, port)) == 0:
                    raise RuntimeError(f"Port {port} is already in use. Stop the running server or close its launcher first.")
        env_file = args.env_file or prepare_judge()
        if not env_file.is_file():
            raise RuntimeError("The replay .env file is missing. Follow the one-time setup in README.md.")
        config = {name: value for name, value in dotenv_values(env_file).items() if value is not None}
        config.update(os.environ)
        dashboard = config.get("ASTRA_FRONTEND_ORIGIN", DEFAULT_DASHBOARD)
        if dashboard not in {DEFAULT_DASHBOARD, f"http://{HOST}:5173"}:
            raise RuntimeError("Use http://localhost:5173 or http://127.0.0.1:5173 as ASTRA_FRONTEND_ORIGIN.")
        weights = config.get("ASTRA_MODEL_WEIGHTS", "data/weights/yolo26n.pt")
        if not (ROOT / weights).is_file():
            raise RuntimeError("The configured local YOLO26n checkpoint is missing. Check ASTRA_MODEL_WEIGHTS in your .env.")
        print("Starting the AstraSentinel backend and dashboard...")
        services["Backend"] = subprocess.Popen(
            [sys.executable, "-m", "app.serve", "--env-file", str(env_file.resolve())],
            cwd=BACKEND, stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        services["Dashboard"] = subprocess.Popen(
            [node, str(VITE), "dev"], cwd=FRONTEND, stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            env={**os.environ, "VITE_API_BASE_URL": API_URL},
        )
        wait_for_servers(services)
        print(f"AstraSentinel is ready at {dashboard}")
        if args.check:
            return 0
        if config.get("ASTRA_JUDGE_MODE") == "1":
            print("Local judge mode. Start a sample replay or upload an MP4 in the dashboard.")
        else:
            print("Enter ASTRA_OPERATOR_TOKEN from the selected private .env under Operator access.")
        print("Press Enter in this window to stop both servers.")
        webbrowser.open(dashboard)
        while True:
            ensure_running(services)
            if msvcrt.kbhit() and msvcrt.getwch() == "\r":
                return 0
            time.sleep(0.2)
    except KeyboardInterrupt:
        return 0
    except (OSError, RuntimeError) as error:
        print(f"AstraSentinel could not run: {error}", file=sys.stderr)
        return 1
    finally:
        if services:
            stop_services(services)
            print("AstraSentinel servers stopped.")


if __name__ == "__main__":
    raise SystemExit(main())

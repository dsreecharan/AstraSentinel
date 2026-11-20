import argparse
import json
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from .config import PROJECT_ROOT
from .errors import StartupError


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Astra Fly single-worker replay service.")
    parser.add_argument("--host", choices=("127.0.0.1", "::1"), default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    if args.reload or args.workers != 1:
        parser.exit(2, '{"error":{"code":"single_worker_required","message":"Use one worker with reload disabled"}}\n')
    load_dotenv(args.env_file)
    server = uvicorn.Server(uvicorn.Config(
        "app.main:app", host=args.host, port=args.port, workers=1, reload=False, lifespan="on",
        timeout_graceful_shutdown=5,
    ))
    try:
        server.run()
    except StartupError as error:
        parser.exit(1, json.dumps({"error": {"code": error.code, "message": error.message}}) + "\n")
    return 0 if server.started else 1


if __name__ == "__main__":
    raise SystemExit(main())

import json
import os
import shlex
import subprocess
from time import monotonic, sleep

import httpx
import pytest


@pytest.mark.phase2
def test_mediamtx_rtsp_auth_and_hls_manifest():
    container = os.getenv("ASTRA_TEST_MEDIA_CONTAINER")
    if not container:
        pytest.skip("Set ASTRA_TEST_MEDIA_CONTAINER to the Compose MediaMTX container")
    docker = json.loads(os.getenv("ASTRA_TEST_DOCKER_COMMAND", '["docker"]'))
    ffmpeg = docker + ["exec", container, "ffmpeg", "-nostdin", "-loglevel", "error", "-re",
                       "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10", "-an", "-c:v", "libx264",
                       "-pix_fmt", "yuv420p", "-profile:v", "baseline", "-preset", "ultrafast",
                       "-tune", "zerolatency", "-bf", "0", "-g", "10"]
    rtsp_output = ["-f", "rtsp", "-rtsp_transport", "tcp"]
    unauthorized = subprocess.run(ffmpeg + ["-t", "1"] + rtsp_output + ["rtsp://127.0.0.1:8554/monitor"],
                                  capture_output=True, timeout=12)
    assert unauthorized.returncode != 0 and b"401" in unauthorized.stderr

    # The container already has the per-run secret. Avoid expanding it on the test host.
    publish = docker + ["exec", "-i", container, "/bin/sh", "-e"]
    script = "exec " + shlex.join(ffmpeg[len(docker) + 2:] + ["-t", "12"] + rtsp_output) + (
        ' "rtsp://publisher:${MTX_AUTHINTERNALUSERS_0_PASS}@127.0.0.1:8554/monitor"\n'
    )
    with subprocess.Popen(publish, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as publisher:
        publisher.stdin.write(script.encode())
        publisher.stdin.close()
        try:
            endpoint = "http://127.0.0.1:8888/monitor/index.m3u8"
            deadline = monotonic() + 15
            with httpx.Client(timeout=5, trust_env=False, follow_redirects=True) as client:
                while monotonic() < deadline:
                    response = client.get(endpoint)
                    if response.status_code == 200 and "#EXTM3U" in response.text:
                        break
                    assert publisher.poll() is None
                    sleep(0.25)
                else:
                    pytest.fail("HLS playlist never became available")
                assert client.get("http://127.0.0.1:8889/monitor/").status_code == 200
            probe = subprocess.run(docker + [
                "exec", container, "ffprobe", "-v", "error", "-rtsp_transport", "tcp", "-select_streams", "v:0",
                "-show_entries", "stream=codec_name,width,height", "-of", "json", "rtsp://127.0.0.1:8554/monitor",
            ], capture_output=True, timeout=10, check=True)
            assert json.loads(probe.stdout)["streams"] == [{"codec_name": "h264", "width": 320, "height": 180}]
        finally:
            # The in-container publisher has a finite duration even if the test client detaches.
            publisher.wait(timeout=20)

import asyncio
import os
import socket
import struct
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.telemetry import EPOCH, MavsdkTelemetry, sample_from_gps


def test_telemetry_distinguishes_receipt_boot_time_and_reported_epoch():
    receipt = datetime(2026, 11, 20, tzinfo=UTC)
    raw = SimpleNamespace(
        timestamp_us=12345, longitude_deg=78.4, latitude_deg=17.4, horizontal_uncertainty_m=float("nan"),
    )
    boot = sample_from_gps(raw, 1, receipt, 17, True)
    assert boot.source_time_utc is None and boot.timestamp_status == "source_utc_unusable"
    assert boot.horizontal_uncertainty_m is None and boot.time_alignment_uncertainty_ms is None
    raw.timestamp_us = int((receipt - EPOCH).total_seconds() * 1_000_000)
    raw.horizontal_uncertainty_m = 2.5
    assert sample_from_gps(raw, 1, receipt, 17, False).source_time_utc is None
    epoch = sample_from_gps(raw, 1, receipt, 17, True)
    assert epoch.source_time_utc == receipt and epoch.timestamp_status == "source_utc_plausible"
    assert epoch.horizontal_uncertainty_m == 2.5


def mavlink_fixture_packet(message_id: int, extra: int, seq: int, payload: bytes) -> bytes:
    """Minimal MAVLink v1 wire fixture for HEARTBEAT and GPS_RAW_INT."""
    body = bytes((len(payload), seq % 256, 1, 1, message_id)) + payload
    crc = 0xFFFF
    for byte in body + bytes([extra]):
        value = (byte ^ crc) & 255
        value = (value ^ (value << 4)) & 255
        crc = (crc >> 8) ^ (value << 8) ^ (value << 3) ^ (value >> 4)
    return b"\xfe" + body + struct.pack("<H", crc)


@pytest.mark.phase2
def test_native_mavsdk_receives_udp_fixture_and_releases_receiver():
    if os.getenv("ASTRA_TEST_TELEMETRY") != "1":
        pytest.skip("Set ASTRA_TEST_TELEMETRY=1 after installing the telemetry extra")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]

    async def exchange():
        address = ("127.0.0.1", port)
        reader = asyncio.create_task(MavsdkTelemetry(port, timeout=4).read_one())
        heartbeat = struct.pack("<IBBBBB", 0, 2, 12, 0, 4, 3)
        gps = struct.pack("<QiiiHHHHBB", 123456, 174000000, 784000000, 200000, 100, 100, 0, 0, 3, 10)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            for seq in range(0, 120, 2):
                if reader.done():
                    break
                sender.sendto(mavlink_fixture_packet(0, 50, seq, heartbeat), address)
                sender.sendto(mavlink_fixture_packet(24, 24, seq + 1, gps), address)
                await asyncio.sleep(0.08)
        return await reader

    sample = asyncio.run(exchange())
    assert sample.subject == "simulator_vehicle" and sample.system_id == 1
    assert sample.vehicle_location.coordinates == pytest.approx((78.4, 17.4))
    assert sample.timestamp_status == "receiver_only" and sample.source_time_utc is None
    assert sample.received_at_utc.tzinfo is UTC and sample.received_monotonic_ns > 0
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind(("127.0.0.1", port))

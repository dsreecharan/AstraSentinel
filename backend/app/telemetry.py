"""Optional read-only PX4 simulator vehicle telemetry."""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from math import isfinite
from time import monotonic_ns
from typing import Literal, Protocol

from pydantic import BaseModel

from .contracts.geo import Point

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
MAX_UTC_SKEW = timedelta(seconds=5)


class VehicleSample(BaseModel):
    subject: Literal["simulator_vehicle"] = "simulator_vehicle"
    system_id: int
    vehicle_location: Point
    horizontal_uncertainty_m: float | None
    received_at_utc: datetime
    received_monotonic_ns: int
    raw_timestamp_us: int | None
    source_time_utc: datetime | None
    timestamp_status: Literal["receiver_only", "source_utc_plausible", "source_utc_unusable"]
    time_alignment_uncertainty_ms: None = None


class TelemetrySource(Protocol):
    async def read_one(self) -> VehicleSample: ...


def sample_from_gps(raw, system_id: int, received_utc: datetime, received_ns: int, source_utc: bool) -> VehicleSample:
    reported_time = raw.timestamp_us or None
    timestamp = None
    status = "source_utc_unusable" if source_utc else "receiver_only"
    if source_utc and reported_time:
        # Compare integer offsets before constructing a datetime from untrusted device data.
        receipt_us = (received_utc - EPOCH) // timedelta(microseconds=1)
        if abs(receipt_us - reported_time) <= MAX_UTC_SKEW // timedelta(microseconds=1):
            timestamp = EPOCH + timedelta(microseconds=reported_time)
            status = "source_utc_plausible"
    uncertainty = raw.horizontal_uncertainty_m
    return VehicleSample(
        system_id=system_id,
        vehicle_location=Point(type="Point", coordinates=(raw.longitude_deg, raw.latitude_deg)),
        horizontal_uncertainty_m=uncertainty if isfinite(uncertainty) and uncertainty > 0 else None,
        received_at_utc=received_utc, received_monotonic_ns=received_ns,
        raw_timestamp_us=reported_time, source_time_utc=timestamp, timestamp_status=status,
    )


class MavsdkTelemetry:
    def __init__(self, port: int = 14540, timeout: float = 5.0, expect_source_utc: bool = False):
        if not 0 < port < 65536 or not isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("Use a valid simulator UDP port and a receive timeout of at most 60 seconds")
        self.port = port
        self.timeout = timeout
        self.expect_source_utc = expect_source_utc

    async def read_one(self) -> VehicleSample:
        try:
            from mavsdk import ComponentType, Configuration, ConnectionResult, Mavsdk
            from mavsdk.plugins.telemetry import Telemetry
        except ImportError:
            raise RuntimeError("Install the optional telemetry extra for MAVSDK") from None
        config = Configuration.create_with_component_type(ComponentType.GROUND_STATION)
        try:
            with Mavsdk(config) as sdk:
                result = sdk.add_any_connection(f"udpin://127.0.0.1:{self.port}")
                if result != ConnectionResult.SUCCESS:
                    raise RuntimeError(f"Cannot bind the loopback simulator receiver ({result.name})")
                discovery = asyncio.create_task(asyncio.to_thread(sdk.first_autopilot, self.timeout))
                try:
                    system = await asyncio.shield(discovery)
                except asyncio.CancelledError:
                    # Finish the bounded native call before destroying its SDK handle.
                    await discovery
                    raise
                if system is None:
                    raise TimeoutError("No simulator heartbeat received")
                telemetry = Telemetry(system)
                loop = asyncio.get_running_loop()
                reading = loop.create_future()

                def deliver(raw, receipt_utc, receipt_ns):
                    if not reading.done():
                        reading.set_result((raw, receipt_utc, receipt_ns))

                def receive(raw, _user_data):
                    loop.call_soon_threadsafe(deliver, raw, datetime.now(UTC), monotonic_ns())

                handle = telemetry.subscribe_raw_gps(receive)
                try:
                    raw, receipt_utc, receipt_ns = await asyncio.wait_for(reading, timeout=self.timeout)
                    return sample_from_gps(
                        raw, system.get_system_id(), receipt_utc, receipt_ns, self.expect_source_utc,
                    )
                finally:
                    telemetry.unsubscribe_raw_gps(handle)
        finally:
            config.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description="Read one GPS sample from a loopback PX4 simulator.")
    parser.add_argument("--port", type=int, default=14540)
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--expect-source-utc", action="store_true", help="Use only with a verified epoch-time simulator source")
    args = parser.parse_args()
    try:
        sample = asyncio.run(MavsdkTelemetry(args.port, args.timeout, args.expect_source_utc).read_one())
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"Telemetry unavailable: {error or 'no simulator GPS message received'}\n")
    print(sample.model_dump_json())


if __name__ == "__main__":
    main()

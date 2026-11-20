import { describe, expect, it } from "vitest";
import type { Geofence, Incident, Source } from "../api/client";
import { mapData, measuredError, validPosition } from "./data";

const source: Source = {
  id: "test-source", title: "Unit test fixture", attribution: "Test", rights_note: "Test",
  geo_mode: "calibrated", video_sha256: "a".repeat(64), license_url: null,
};

const point: Incident = {
  id: "test-incident", source_id: source.id, run_id: "test-run", event_type: "zone_intrusion",
  severity: "review", rule_name: "restricted_zone_entry",
  rule_details: { zone_id: "test-zone", track_id: "test-run:1", trigger_frame_index: 16, consecutive_frames: 3, cooldown_ms: 5000 },
  review_status: "pending", reviewer: null, reviewed_at: null, evidence_url: null,
  video_time_ms: 1600, observed_at: null, created_at: "2026-11-20T07:53:00Z",
  geo_status: "calibrated", location: { type: "Point", coordinates: [78.001, 17.002] }, horizontal_error_m: null,
};

const fence: Geofence = {
  id: "test-zone", source_id: source.id, label: "Boundary", space_type: "world", enabled: true, frame_size_px: null,
  geometry: { type: "Polygon", coordinates: [[[78, 17], [78.002, 17], [78.002, 17.002], [78, 17]]] },
};

describe("map geometry gate", () => {
  it("rejects invalid positions without swapping axes", () => {
    expect(validPosition([78, 17])).toBe(true);
    expect(validPosition([17, 91])).toBe(false);
    expect(validPosition([NaN, 17])).toBe(false);
    expect(validPosition(["78", 17])).toBe(false);
  });

  it("plots calibrated points and enabled matching world fences", () => {
    const polygon = { ...fence, space_type: "image" as const };
    const data = mapData(source, [point, { ...point, source_id: "another" }], [
      fence, polygon, { ...fence, enabled: false },
    ], point.id);
    expect(data.features).toHaveLength(2);
    expect(data.features[1]).toMatchObject({
      geometry: { type: "Point", coordinates: [78.001, 17.002] },
      properties: { kind: "incident", selected: true },
    });
  });

  it("renders no geographic data for an uncalibrated source or image-space incident", () => {
    expect(mapData({ ...source, geo_mode: "unavailable" }, [point], [fence], null).features).toEqual([]);
    const imageOnly: Incident = { ...point, geo_status: "image_roi_only", horizontal_error_m: 10 };
    expect(mapData(source, [imageOnly], [], null).features).toEqual([]);
    expect(measuredError(imageOnly)).toBeNull();
  });

  it("draws uncertainty only from measured, finite values", () => {
    const measured = { ...point, horizontal_error_m: 15 };
    expect(mapData(source, [measured], [], null).features.map(({properties}) => properties?.kind))
      .toEqual(["uncertainty", "incident"]);
    expect(mapData(source, [{ ...point, horizontal_error_m: Infinity }], [], null).features).toHaveLength(1);
    expect(measuredError(point)).toBeNull();
  });
});

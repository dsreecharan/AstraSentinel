import type { Feature, FeatureCollection, Geometry, Polygon } from "geojson";
import type { Geofence, Incident, Source } from "../api/client";

type Position = [number, number];
export const emptyData: FeatureCollection = { type: "FeatureCollection", features: [] };

export function validPosition(value: unknown): value is Position {
  return Array.isArray(value) && value.length === 2 &&
    Number.isFinite(value[0]) && Math.abs(value[0]) <= 180 &&
    Number.isFinite(value[1]) && Math.abs(value[1]) <= 90;
}

export function measuredError(incident: Incident): number | null {
  const value = incident.horizontal_error_m;
  return incident.geo_status === "calibrated" && incident.location?.type === "Point" &&
    validPosition(incident.location.coordinates) && typeof value === "number" &&
    Number.isFinite(value) && value >= 0 ? value : null;
}

function uncertainty(center: Position, meters: number): Polygon | null {
  if (meters === 0) return null;
  const radians = Math.PI / 180;
  const [longitude, latitude] = center.map((value) => value * radians);
  const distance = meters / 6_378_137;
  const points: Position[] = [];
  for (let step = 0; step < 48; step++) {
    const bearing = step * 2 * Math.PI / 48;
    const lat = Math.asin(Math.sin(latitude) * Math.cos(distance) +
      Math.cos(latitude) * Math.sin(distance) * Math.cos(bearing));
    const lon = longitude + Math.atan2(Math.sin(bearing) * Math.sin(distance) * Math.cos(latitude),
      Math.cos(distance) - Math.sin(latitude) * Math.sin(lat));
    points.push([lon / radians, lat / radians]);
  }
  // Preserve the marker when the uncertainty area does not fit a single GeoJSON ring.
  if (!points.every(validPosition)) return null;
  return { type: "Polygon", coordinates: [[...points, points[0]]] };
}

export function mapData(source: Source | undefined, incidents: Incident[], fences: Geofence[], selected: string | null) {
  const features: Feature<Geometry>[] = [];
  if (source?.geo_mode !== "calibrated") return emptyData;
  for (const fence of fences) {
    const ring = fence.geometry?.coordinates?.[0];
    if (fence.source_id !== source.id || fence.space_type !== "world" || !fence.enabled ||
        fence.geometry?.type !== "Polygon" || !Array.isArray(ring) || ring.length < 4 ||
        !ring.every(validPosition)) continue;
    const last = ring[ring.length - 1];
    if (last[0] !== ring[0][0] || last[1] !== ring[0][1]) continue;
    features.push({
      type: "Feature", properties: { kind: "geofence", id: fence.id },
      geometry: { type: "Polygon", coordinates: [ring] },
    });
  }
  for (const incident of incidents) {
    const point = incident.location;
    if (incident.source_id !== source.id || incident.geo_status !== "calibrated" ||
        point?.type !== "Point" || !validPosition(point.coordinates)) continue;
    const meters = measuredError(incident);
    const area = meters === null ? null : uncertainty(point.coordinates, meters);
    if (area) {
      features.push({ type: "Feature", properties: { kind: "uncertainty", id: incident.id }, geometry: area });
    }
    features.push({
      type: "Feature", properties: { kind: "incident", id: incident.id, selected: incident.id === selected },
      geometry: { type: "Point", coordinates: point.coordinates },
    });
  }
  return { type: "FeatureCollection" as const, features };
}

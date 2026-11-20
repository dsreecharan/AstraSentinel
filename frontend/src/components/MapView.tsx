import { useEffect, useRef, useState } from "react";
import { LngLatBounds, Map, NavigationControl, ScaleControl, setWorkerUrl } from "maplibre-gl";
import type { GeoJSONSource, StyleSpecification } from "maplibre-gl";
import type { FeatureCollection, Position } from "geojson";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";

import { emptyData } from "../map/data";

setWorkerUrl(workerUrl);

const sourceName = "replay-geometry";
const localStyle: StyleSpecification = {
  version: 8,
  sources: { [sourceName]: { type: "geojson", data: emptyData } },
  layers: [
    { id: "ground", type: "background", paint: { "background-color": "#142433" } },
    {
      id: "zone-fill", type: "fill", source: sourceName, filter: ["==", ["get", "kind"], "geofence"],
      paint: { "fill-color": "#62d5c1", "fill-opacity": 0.18 },
    },
    {
      id: "zone-outline", type: "line", source: sourceName, filter: ["==", ["get", "kind"], "geofence"],
      paint: { "line-color": "#62d5c1", "line-width": 2 },
    },
    {
      id: "uncertainty", type: "fill", source: sourceName, filter: ["==", ["get", "kind"], "uncertainty"],
      paint: { "fill-color": "#f0b979", "fill-opacity": 0.23, "fill-outline-color": "#f0b979" },
    },
    {
      id: "incidents", type: "circle", source: sourceName, filter: ["==", ["get", "kind"], "incident"],
      paint: {
        "circle-color": "#ffb861", "circle-stroke-color": "#08111d", "circle-stroke-width": 2,
        "circle-radius": ["case", ["boolean", ["get", "selected"], false], 9, 6],
      },
    },
  ],
};

function fit(map: Map, data: FeatureCollection) {
  const bounds = new LngLatBounds();
  for (const item of data.features) {
    if (item.geometry.type === "Point") bounds.extend(item.geometry.coordinates as [number, number]);
    if (item.geometry.type === "Polygon") {
      for (const point of item.geometry.coordinates[0] as Position[]) bounds.extend(point as [number, number]);
    }
  }
  if (!bounds.isEmpty()) map.fitBounds(bounds, { maxZoom: 17, padding: 42, duration: 0 });
}

export default function MapView({ data, onSelect }: { data: FeatureCollection; onSelect: (id: string) => void }) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const selected = useRef(onSelect);
  const lastBounds = useRef("");
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => { selected.current = onSelect; }, [onSelect]);

  useEffect(() => {
    if (!container.current) return;
    let map: Map;
    try {
      map = new Map({ container: container.current, style: localStyle, attributionControl: false, renderWorldCopies: false });
    } catch {
      setFailed(true);
      return;
    }
    mapRef.current = map;
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new ScaleControl({ unit: "metric" }), "bottom-left");
    map.on("load", () => setReady(true));
    map.on("error", () => setFailed(true));
    map.on("click", "incidents", (event) => {
      const id = event.features?.[0]?.properties.id;
      if (typeof id === "string") selected.current(id);
    });
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const source = map.getSource<GeoJSONSource>(sourceName);
    if (!source) return;
    void source.setData(data).catch(() => setFailed(true));
    const extentKey = JSON.stringify(data.features.map(({ geometry }) => geometry));
    if (lastBounds.current !== extentKey) {
      fit(map, data);
      lastBounds.current = extentKey;
    }
  }, [ready, data]);

  return (
    <div className="map-view">
      <div ref={container} className="map-canvas" role="region" aria-label="Map of calibrated incident points and geofences" />
      {failed && <p className="map-message" role="status">Map renderer unavailable. Incident details remain available in the queue.</p>}
    </div>
  );
}

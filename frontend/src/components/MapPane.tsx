import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { api, messageOf, type Geofence, type Incident, type Source } from "../api/client";
import { mapData } from "../map/data";

const MapView = lazy(() => import("./MapView"));

export function MapPane({ source, incident, incidents, simulated, revision, onSelect }: {
  source?: Source; incident: Incident | null; incidents: Incident[]; simulated: boolean;
  revision: unknown; onSelect: (id: string) => void;
}) {
  const sourceId = source?.id;
  const calibrated = source?.geo_mode === "calibrated";
  const [fenceResult, setFenceResult] = useState<{ sourceId: string; items: Geofence[]; error?: string }>();
  useEffect(() => {
    if (!sourceId || !calibrated) return;
    const controller = new AbortController();
    void api.geofences(sourceId, controller.signal).then((result) => {
      if (!controller.signal.aborted) setFenceResult({ sourceId, items: result.items });
    }).catch((error) => {
      if (!controller.signal.aborted) setFenceResult({ sourceId, items: [], error: messageOf(error) });
    });
    return () => controller.abort();
  }, [sourceId, calibrated, revision]);

  const fences = fenceResult?.sourceId === sourceId ? fenceResult : undefined;
  const data = useMemo(() => mapData(source, incidents, fences?.items ?? [], incident?.id ?? null),
    [source, incidents, fences, incident?.id]);
  const imageOnly = incident?.geo_status === "image_roi_only";
  const emptyTitle = source
    ? (calibrated && !imageOnly ? "No calibrated locations to display" : "Geolocation unavailable")
    : "No source selected";

  return (
    <section className="panel map-panel" aria-labelledby="map-heading">
      <header className="panel-header">
        <h2 id="map-heading">Map</h2>
        <span className="chip tone-muted">{!source ? "Awaiting source" : simulated ? "Simulated coordinates" :
          calibrated ? "Calibration configured" : "Image space"}</span>
      </header>
      <div className="map-stage">
        {data.features.length > 0 ? <Suspense fallback={<div className="empty-state" role="status">Loading calibrated map…</div>}><MapView key={sourceId} data={data} onSelect={onSelect} /></Suspense> : (
          <div className="empty-state map-empty">
            <span className="map-grid-icon" aria-hidden="true"><i /><i /><i /><i /></span>
            <strong>{imageOnly ? "Geolocation unavailable — image-space alert" : emptyTitle}</strong>
            {source && <p>{calibrated && !imageOnly
              ? "World geofences and incident points appear here when available."
              : "Image-space regions are shown in the annotated replay."}</p>}
          </div>
        )}
      </div>
      <footer className="panel-footer">
        {fences?.error ? <span className="error-text">Geofences unavailable · {fences.error}</span> : (
          <>
            <span>{imageOnly && data.features.length ? "Selected alert is image-space" : source?.title ?? "Source context unavailable"}</span>
            {data.features.length > 0 && <span className="mono">WGS 84</span>}
          </>
        )}
      </footer>
    </section>
  );
}

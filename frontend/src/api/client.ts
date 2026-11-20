import type { components } from "./schema";

type Schemas = components["schemas"];
export type Source = Schemas["Source"];
export type Run = Schemas["Run"];
export type Incident = Schemas["Incident"];
export type IncidentPage = Schemas["IncidentPage"];
export type Geofence = Schemas["Geofence"];
export type AuditEntry = Schemas["AuditEntry"];
export type ReviewInput = Schemas["ReviewInput"];
export type Health = Schemas["Health"];
export type AccessPolicy = Schemas["AccessPolicy"];

const apiBase = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
export const INCIDENT_PAGE_SIZE = 50;

export class ApiError extends Error {
  constructor(readonly status: number, readonly code: string, message: string) {
    super(message);
  }
}

async function request<T>(path: string, options: {
  signal?: AbortSignal;
  write?: { token: string; body: object; headers?: Record<string, string> };
} = {}): Promise<T> {
  const { signal, write } = options;
  const binary = write?.body instanceof Blob;
  const timeout = AbortSignal.timeout(binary ? 120_000 : 5000);
  let response: Response;
  try {
    response = await fetch(`${apiBase}${path}`, {
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
      cache: "no-store",
      method: write ? "POST" : "GET",
      headers: write ? {
        ...(write.token ? { Authorization: `Bearer ${write.token}` } : {}),
        "Content-Type": binary ? "video/mp4" : "application/json",
        ...write.headers,
      } : {},
      body: write?.body instanceof Blob ? write.body : write ? JSON.stringify(write.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "network", "Unable to reach the replay backend.");
  }
  if (!response.ok) {
    const body: Schemas["ErrorEnvelope"] | null = await response.json().catch(() => null);
    throw new ApiError(
      response.status, body?.error?.code || "request_failed",
      body?.error?.message || `Request failed (HTTP ${response.status}).`,
    );
  }
  return response.json() as Promise<T>;
}

const incidentPath = (id: string) => `/api/v1/incidents/${encodeURIComponent(id)}`;

export const api = {
  health: (signal?: AbortSignal) => request<Health>("/api/v1/health", { signal }),
  access: (signal?: AbortSignal) => request<AccessPolicy>("/api/v1/access", { signal }),
  sources: (signal?: AbortSignal) => request<Schemas["SourceList"]>("/api/v1/sources", { signal }),
  upload: (file: File, title: string, attribution: string, token: string) => request<Source>("/api/v1/sources/upload", {
    write: {
      token, body: file, headers: {
        "X-Astra-Title": encodeURIComponent(title),
        "X-Astra-Attribution": encodeURIComponent(attribution),
        "X-Astra-Rights-Confirmed": "true",
      },
    },
  }),
  runStatus: (signal?: AbortSignal) => request<Schemas["RunSnapshot"]>("/api/v1/runs/status", { signal }),
  incidents: (offset: number, signal?: AbortSignal) => request<IncidentPage>(
    `/api/v1/incidents?limit=${INCIDENT_PAGE_SIZE}&offset=${offset}`, { signal },
  ),
  audit: (id: string, signal?: AbortSignal) => request<Schemas["AuditList"]>(`${incidentPath(id)}/audit`, { signal }),
  geofences: (id: string, signal?: AbortSignal) => request<Schemas["GeofenceList"]>(
    `/api/v1/geofences?source_id=${encodeURIComponent(id)}`, { signal },
  ),
  start: (sourceId: string, token: string) => request<Run>("/api/v1/runs/start", {
    write: { token, body: { source_id: sourceId, mode: "replay" } satisfies Schemas["RunStart"] },
  }),
  stop: (runId: string, token: string) => request<Run>("/api/v1/runs/stop", {
    write: { token, body: { run_id: runId } satisfies Schemas["RunStop"] },
  }),
  review: (id: string, body: ReviewInput, token: string) => request<Incident>(`${incidentPath(id)}/review`, {
    write: { token, body },
  }),
};

export function eventUrl() {
  const url = new URL(`${apiBase}/ws/events`, window.location.href);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.href;
}

export function replayUrl(runId: string, attempt: number) {
  return `${apiBase}/api/v1/stream/annotated.mjpg?run=${encodeURIComponent(runId)}&attempt=${attempt}`;
}

export function thumbnailUrl(incident: Incident): string | null {
  const path = `${incidentPath(incident.id)}/thumbnail`;
  return incident.evidence_url === path ? `${apiBase}${path}` : null;
}

export function messageOf(error: unknown) {
  return error instanceof ApiError ? error.message : "The backend response could not be read.";
}

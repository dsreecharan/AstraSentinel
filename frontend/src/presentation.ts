import type { Incident, Run } from "./api/client";

export const isActive = (run: Run | null | undefined) =>
  run?.status === "starting" || run?.status === "running" || run?.status === "stopping";

export function footageTime(ms: number) {
  const minutes = String(Math.floor(ms / 60_000)).padStart(2, "0");
  const seconds = String(Math.floor(ms / 1000) % 60).padStart(2, "0");
  return `${minutes}:${seconds}.${String(ms % 1000).padStart(3, "0")}`;
}

export const eventTitle = (incident: Incident) =>
  incident.event_type === "zone_intrusion" ? "Restricted-zone entry" : "Crowd threshold exceeded";

export const reviewLabels = {
  pending: "Pending review",
  acknowledged: "Acknowledged",
  dismissed: "Dismissed",
};

export const runLabels: Record<Run["status"], string> = {
  starting: "Loading",
  running: "Running",
  stopping: "Stopping",
  stopped: "Stopped",
  ended: "Ended",
  error: "Error",
};

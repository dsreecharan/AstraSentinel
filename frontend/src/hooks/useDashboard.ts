import { useCallback, useEffect, useRef, useState } from "react";
import { api, eventUrl, messageOf, type AccessPolicy, type Health, type IncidentPage, type Run, type Source } from "../api/client";
import { serializeRefresh, subscribeEvents, type EventConnection } from "../api/events";

interface Snapshot {
  health: Health;
  access: AccessPolicy;
  sources: Source[];
  simulatedSourceIds: string[];
  run: Run | null;
  incidents: IncidentPage;
  offset: number;
}

export function useDashboard(offset: number) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [events, setEvents] = useState<EventConnection>("connecting");
  const currentRefresh = useRef<() => void>(() => {});
  const refresh = useCallback(() => currentRefresh.current(), []);

  useEffect(() => {
    const controller = new AbortController();
    const load = serializeRefresh(async () => {
      if (controller.signal.aborted) return;
      try {
        const signal = controller.signal;
        const [health, access, sources, run, incidents] = await Promise.all([
          api.health(signal), api.access(signal), api.sources(signal), api.runStatus(signal), api.incidents(offset, signal),
        ]);
        if (!signal.aborted) {
          setSnapshot({ health, access, sources: sources.items, simulatedSourceIds: sources.simulated_source_ids ?? [],
            run: run.run, incidents, offset });
          setError("");
        }
      } catch (issue) {
        if (!controller.signal.aborted) setError(messageOf(issue));
      }
    });
    currentRefresh.current = () => { void load(); };
    refresh();
    // REST also reconciles missed notifications while the socket is unavailable.
    const poll = setInterval(refresh, 3500);
    return () => {
      controller.abort();
      clearInterval(poll);
      currentRefresh.current = () => {};
    };
  }, [offset, refresh]);

  useEffect(() => subscribeEvents(eventUrl(), setEvents, refresh), [refresh]);

  return { snapshot, error, events, refresh };
}

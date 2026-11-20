const eventTypes = ["ready", "candidate_incident", "incident_reviewed", "run_status"] as const;
type EventType = (typeof eventTypes)[number];

export type EventConnection = "connecting" | "connected" | "reconnecting";

export function parseEventType(message: unknown): EventType | undefined {
  if (typeof message !== "string") return;
  try {
    const value: unknown = JSON.parse(message);
    if (value && typeof value === "object" && "schema_version" in value && value.schema_version === "1.0" &&
        "emitted_at" in value && typeof value.emitted_at === "string" &&
        "data" in value && value.data && typeof value.data === "object" && !Array.isArray(value.data) &&
        "type" in value) {
      return eventTypes.find((type) => type === value.type);
    }
  } catch {
    // Only envelopes matching the backend contract invalidate the REST snapshot.
  }
}

export function reconnectDelay(failures: number) {
  return Math.min(8000, 250 * 2 ** Math.min(failures, 5));
}

export function subscribeEvents(
  url: string, onState: (state: EventConnection) => void, invalidate: () => void,
) {
  let disposed = false;
  let failures = 0;
  let socket: WebSocket | undefined;
  let retry: ReturnType<typeof setTimeout> | undefined;
  let readyTimeout: ReturnType<typeof setTimeout> | undefined;

  function reconnect() {
    if (disposed) return;
    onState("reconnecting");
    retry = setTimeout(connect, reconnectDelay(failures++));
  }

  function connect() {
    if (disposed) return;
    let connection: WebSocket;
    try {
      connection = new WebSocket(url);
    } catch {
      reconnect();
      return;
    }
    socket = connection;
    let ready = false;
    readyTimeout = setTimeout(() => { if (socket === connection) connection.close(); }, 7000);
    connection.onmessage = (event) => {
      if (disposed || socket !== connection) return;
      const type = parseEventType(event.data);
      if (type === "ready" && !ready) {
        ready = true;
        failures = 0;
        clearTimeout(readyTimeout);
        onState("connected");
        invalidate();
      } else if (ready && type && type !== "ready") {
        invalidate();
      }
    };
    connection.onerror = () => { if (socket === connection) connection.close(); };
    connection.onclose = () => {
      if (socket !== connection) return;
      socket = undefined;
      clearTimeout(readyTimeout);
      reconnect();
    };
  }

  onState("connecting");
  connect();
  return () => {
    disposed = true;
    clearTimeout(retry);
    clearTimeout(readyTimeout);
    if (socket) {
      socket.onclose = null;
      socket.close();
    }
  };
}

export function serializeRefresh(load: () => Promise<void>) {
  let running = false;
  let dirty = false;
  return async () => {
    dirty = true;
    if (running) return;
    running = true;
    try {
      while (dirty) {
        dirty = false;
        await load();
      }
    } finally {
      running = false;
    }
  };
}

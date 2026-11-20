import { afterEach, expect, it, vi } from "vitest";
import { parseEventType, reconnectDelay, serializeRefresh, subscribeEvents } from "./events";

const envelope = (type: string, version = "1.0") => JSON.stringify({
  schema_version: version, type, emitted_at: "2026-11-20T07:50:00Z", data: {},
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it("recognizes current notification envelopes and ignores malformed or unsupported messages", () => {
  expect(parseEventType(envelope("candidate_incident"))).toBe("candidate_incident");
  expect(parseEventType(envelope("ready", "2.0"))).toBeUndefined();
  expect(parseEventType(envelope("unknown"))).toBeUndefined();
  expect(parseEventType("broken")).toBeUndefined();
  expect(parseEventType('{"type":"ready"}')).toBeUndefined();
});

it("coalesces invalidations during a REST request into a follow-up request", async () => {
  let complete!: () => void;
  const pending = new Promise<void>((resolve) => { complete = resolve; });
  const load = vi.fn<() => Promise<void>>().mockReturnValueOnce(pending).mockResolvedValue(undefined);
  const refresh = serializeRefresh(load);
  const first = refresh();
  await refresh();
  await refresh();
  expect(load).toHaveBeenCalledTimes(1);
  complete();
  await first;
  expect(load).toHaveBeenCalledTimes(2);
});

it("backs off disconnects and invalidates REST again on reconnect readiness", async () => {
  vi.useFakeTimers();
  const sockets: TestSocket[] = [];
  class TestSocket {
    onclose: (() => void) | null = null;
    onmessage: ((event: { data: string }) => void) | null = null;
    constructor() { sockets.push(this); }
    close() { this.onclose?.(); }
    sendFromServer(type: string) { this.onmessage?.({ data: envelope(type) }); }
  }
  vi.stubGlobal("WebSocket", TestSocket);
  const invalidate = vi.fn();
  const status = vi.fn();
  const dispose = subscribeEvents("ws://localhost/ws/events", status, invalidate);
  sockets[0].sendFromServer("candidate_incident");
  expect(invalidate).not.toHaveBeenCalled();
  sockets[0].sendFromServer("ready");
  sockets[0].sendFromServer("incident_reviewed");
  expect(invalidate).toHaveBeenCalledTimes(2);
  sockets[0].close();
  expect(status).toHaveBeenLastCalledWith("reconnecting");
  sockets[0].sendFromServer("ready");
  sockets[0].sendFromServer("candidate_incident");
  expect(invalidate).toHaveBeenCalledTimes(2);
  expect(status).toHaveBeenLastCalledWith("reconnecting");
  await vi.advanceTimersByTimeAsync(249);
  expect(sockets).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(1);
  expect(sockets).toHaveLength(2);
  sockets[0].close();
  sockets[0].sendFromServer("incident_reviewed");
  await vi.advanceTimersByTimeAsync(250);
  expect(sockets).toHaveLength(2);
  sockets[1].sendFromServer("ready");
  sockets[1].sendFromServer("ready");
  expect(invalidate).toHaveBeenCalledTimes(3);
  expect(status).toHaveBeenLastCalledWith("connected");
  expect(reconnectDelay(4)).toBe(4000);
  expect(reconnectDelay(10)).toBe(8000);
  dispose();
  sockets[1].sendFromServer("run_status");
  expect(invalidate).toHaveBeenCalledTimes(3);
});

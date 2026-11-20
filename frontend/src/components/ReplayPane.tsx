import { useEffect, useState } from "react";
import { replayUrl, type Run } from "../api/client";
import { runLabels } from "../presentation";

function ReplayImage({ id }: { id: string }) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<"loading" | "rendered" | "retrying">("loading");
  const giveUp = attempt >= 6 && state === "retrying";

  useEffect(() => {
    if (state !== "retrying" || giveUp) return;
    const timer = setTimeout(() => {
      setAttempt((value) => value + 1);
      setState("loading");
    }, Math.min(1500, 200 * 2 ** attempt));
    return () => clearTimeout(timer);
  }, [attempt, giveUp, state]);

  return (
    <div className="replay-image">
      {!giveUp && (
        <img
          key={attempt} className={state === "retrying" ? "stream-image stream-hidden" : "stream-image"}
          crossOrigin="anonymous" src={replayUrl(id, attempt)} alt="Annotated footage from this replay run"
          onLoad={() => setState("rendered")} onError={() => setState("retrying")}
        />
      )}
      {state !== "rendered" && (
        <div className="stream-status" role="status">
          {giveUp ? "Annotated frames unavailable." : "Waiting for annotated frames…"}
          {giveUp && <button type="button" onClick={() => { setAttempt(0); setState("loading"); }}>Retry stream</button>}
        </div>
      )}
    </div>
  );
}

function emptyReplay(run: Run | null, disconnected: boolean) {
  if (disconnected) return ["Backend unavailable", "Reconnect the backend to view this replay."];
  if (!run) return ["Replay is idle", "Select a registered source and start a replay."];
  switch (run.status) {
    case "starting": return ["Preparing replay", "Opening the footage and loading the inference model."];
    case "stopping": return ["Stopping replay", "Waiting for the processing worker to stop."];
    case "stopped": return ["Replay stopped", "Start a new run when you’re ready."];
    case "ended": return ["End of replay", "Start a new run to play the source again."];
    case "error": {
      const code = run.error?.code;
      const label = {
        model_unavailable: "Inference failed", tracker_failed: "Inference failed",
        video_unavailable: "Replay source unavailable", video_changed: "Replay source changed",
        decode_failed: "Replay cannot be decoded", timebase_unavailable: "Replay timing unavailable",
        analysis_config_invalid: "Rule or calibration settings invalid", storage_unavailable: "Replay storage unavailable",
        run_interrupted: "Replay interrupted by server restart",
      } as Record<string, string>;
      return [label[code ?? ""] ?? "Replay failed", run.error?.message ?? "The backend stopped this run."];
    }
    default: return ["Awaiting replay", ""];
  }
}

export function ReplayPane({ run, disconnected }: { run: Run | null; disconnected: boolean }) {
  const [title, help] = emptyReplay(run, disconnected);
  return (
    <section className="panel video-panel" aria-labelledby="video-heading">
      <header className="panel-header">
        <h2 id="video-heading">Video</h2>
        <span className="chip tone-cyan">REPLAY</span>
      </header>
      <div className="video-stage">
        {run?.status === "running" && !disconnected ? <ReplayImage key={run.id} id={run.id} /> : (
          <div className="empty-state" role="status">
            <span className="play-icon" aria-hidden="true"><i /></span>
            <strong>{title}</strong>
            {help && <p>{help}</p>}
          </div>
        )}
      </div>
      <footer className="panel-footer">
        <span>{run ? runLabels[run.status] : "Idle"}</span>
        {run && <span className="mono" title={run.id}>Run {run.id.slice(0, 10)}</span>}
      </footer>
      {import.meta.env.VITE_RTSP_MONITOR === "true" && (
        <nav className="panel-footer" aria-label="RTSP media-only monitor">
          <span>RTSP monitor · media only</span>
          <a href="http://127.0.0.1:8889/monitor/" target="_blank" rel="noreferrer">WebRTC</a>
          <a href="http://127.0.0.1:8888/monitor/" target="_blank" rel="noreferrer">HLS</a>
        </nav>
      )}
    </section>
  );
}

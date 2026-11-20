import { useState } from "react";
import { api, messageOf, type ReviewInput } from "./api/client";
import { AccessDialog, ReviewDialog, UploadDialog } from "./components/Dialogs";
import { AuditPane, IncidentPane } from "./components/IncidentPane";
import { MapPane } from "./components/MapPane";
import { ReplayPane } from "./components/ReplayPane";
import { useDashboard } from "./hooks/useDashboard";
import { isActive, runLabels } from "./presentation";

function licenseLink(value: string | null | undefined) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

export default function App() {
  const [offset, setOffset] = useState(0);
  const [preferredSource, setPreferredSource] = useState("");
  const [selection, setSelection] = useState("");
  const [token, setToken] = useState("");
  const [modal, setModal] = useState<"access" | "upload" | { id: string; decision: ReviewInput["decision"] } | null>(null);
  const [runAction, setRunAction] = useState<"start" | "stop" | null>(null);
  const [actionError, setActionError] = useState("");
  const { snapshot, error, events, refresh } = useDashboard(offset);

  const sources = snapshot?.sources ?? [];
  const currentRun = snapshot?.run ?? null;
  const active = isActive(currentRun);
  const chosen = (active && currentRun ? sources.find(({ id }) => id === currentRun.source_id) : undefined) ??
    sources.find(({ id }) => id === preferredSource) ?? sources.find(({ id }) => id === currentRun?.source_id) ?? sources[0];
  const run = currentRun?.source_id === chosen?.id ? currentRun : null;
  const page = snapshot?.offset === offset ? snapshot.incidents : undefined;
  const incidents = page?.items ?? [];
  const incident = incidents.find(({ id }) => id === selection) ?? incidents.find(({ source_id }) => source_id === chosen?.id) ?? null;
  const mapSource = incident ? sources.find(({ id }) => id === incident.source_id) : chosen;
  const simulated = !!mapSource && !!snapshot?.simulatedSourceIds.includes(mapSource.id);
  const license = licenseLink(chosen?.license_url);
  const backendLabel = error ? "Backend unavailable" :
    snapshot?.health.status === "degraded" ? "Backend degraded" : snapshot ? "Backend online" : "Connecting to backend";
  const writeReady = !!snapshot && !error && !runAction;
  const judgeMode = snapshot?.access.mode === "judge";
  const canOperate = judgeMode || !!token;

  async function act(action: "start" | "stop") {
    if (!writeReady) return;
    if (!canOperate) { setModal("access"); return; }
    setActionError("");
    setRunAction(action);
    try {
      if (action === "start" && chosen) await api.start(chosen.id, token);
      if (action === "stop" && currentRun) await api.stop(currentRun.id, token);
    } catch (issue) {
      setActionError(messageOf(issue));
    } finally {
      refresh();
      setRunAction(null);
    }
  }

  function openReview(decision: ReviewInput["decision"]) {
    if (incident) setModal(canOperate ? { id: incident.id, decision } : "access");
  }

  async function upload(file: File, title: string, attribution: string) {
    const source = await api.upload(file, title, attribution, token);
    setPreferredSource(source.id);
    setSelection("");
    setOffset(0);
    setActionError("");
    setModal(null);
    refresh();
  }

  async function review(id: string, body: ReviewInput) {
    try {
      await api.review(id, body, token);
      setModal(null);
    } finally {
      refresh();
    }
  }

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true"><i /><i /></span>
          <div>
            <h1>Astra Fly <span>— Public Safety Command Center</span></h1>
            <p>CipherCop 2026 <span aria-hidden="true">·</span> Hackathon prototype</p>
          </div>
        </div>
        <div className="header-controls">
          <span className="service-status" data-health={error ? "unavailable" : snapshot?.health.status} role="status">
            {backendLabel}
          </span>
          {judgeMode ? <span className="chip tone-cyan">Local judge demo</span> : <button className="subtle" type="button" onClick={() => setModal("access")}>
            {token ? "Operator access set" : "Operator access"}
          </button>}
        </div>
      </header>

      {error && (
        <div className="connection-error" role="alert">
          <span>{error}</span>
          <button className="subtle" type="button" onClick={refresh}>Retry backend</button>
        </div>
      )}

      <section className="source-console" aria-label="Replay controls">
        <div className="source-controls">
          <div className="source-field">
            <label htmlFor="replay-source">Replay source</label>
            <select id="replay-source" value={chosen?.id ?? ""} disabled={active || !snapshot || !!error}
              onChange={(event) => { setPreferredSource(event.target.value); setSelection(""); setActionError(""); }}>
              {sources.length === 0 && <option value="">{!snapshot && !error ? "Loading sources…" : "No registered sources"}</option>}
              {sources.map((source) => <option key={source.id} value={source.id}>{source.title}</option>)}
            </select>
          </div>
          <div className="replay-controls">
            <button className="subtle" type="button" disabled={!writeReady || active}
              onClick={() => setModal(canOperate ? "upload" : "access")}>Upload MP4</button>
            <button className="primary start-control" type="button" disabled={!writeReady || active || !chosen}
              onClick={() => { void act("start"); }}>
              <span className="icon-start" aria-hidden="true" />{runAction === "start" ? "Starting…" : "Start replay"}
            </button>
            <button className="subtle stop-control" type="button"
              disabled={!writeReady || !active || currentRun?.status === "stopping"} onClick={() => { void act("stop"); }}>
              <span className="icon-stop" aria-hidden="true" />{runAction === "stop" ? "Stopping…" : "Stop"}
            </button>
            <span className={`chip replay-status ${run?.status === "error" ? "tone-amber" : active ? "tone-cyan" : "tone-muted"}`}
              role="status">{run ? runLabels[run.status] : "Idle"}</span>
          </div>
        </div>
        {chosen && (
          <div className="source-provenance">
            <span title={chosen.attribution}>{chosen.attribution}</span>
            {license && <a href={license} target="_blank" rel="noreferrer">License ↗</a>}
            <details>
              <summary>Source provenance</summary>
              <dl>
                <dt>Source ID</dt><dd>{chosen.id}</dd>
                <dt>Rights</dt><dd>{chosen.rights_note}</dd>
                <dt>SHA-256</dt><dd className="mono">{chosen.video_sha256}</dd>
              </dl>
            </details>
          </div>
        )}
        {actionError && <p className="error-text source-error" role="alert">{actionError}</p>}
      </section>

      <main className="workspace">
        <ReplayPane run={run} disconnected={!!error} />
        <MapPane source={mapSource} incident={incident} incidents={incidents} simulated={simulated}
          revision={snapshot} onSelect={setSelection} />
        <IncidentPane
          page={page} offset={offset} selected={incident} onSelect={setSelection} onReview={openReview}
          onPage={(value) => { setOffset(value); setSelection(""); }} unavailable={!!error}
          loading={!page && !error} canWrite={writeReady} simulated={simulated}
        />
        <AuditPane incident={incident} revision={snapshot} />
      </main>
      <footer className="workspace-status">
        <span>{judgeMode ? "Face verification unavailable · Consent and a licensed model required" : "Replay operations"}</span>
        <span className="event-connection" data-events={events} role="status">
          Events {events === "connected" ? "connected" : events === "reconnecting" ? "reconnecting" : "connecting"}
        </span>
      </footer>

      {modal === "access" && (
        <AccessDialog hasToken={!!token} onClose={() => setModal(null)}
          onSave={(value) => { setToken(value); setModal(null); setActionError(""); }} />
      )}
      {modal === "upload" && <UploadDialog onClose={() => setModal(null)} onSubmit={upload} />}
      {modal && typeof modal === "object" && (
        <ReviewDialog key={modal.id} decision={modal.decision}
          onClose={() => setModal(null)} onSubmit={(body) => review(modal.id, body)} />
      )}
    </div>
  );
}

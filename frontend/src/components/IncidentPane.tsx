import { useEffect, useState } from "react";
import { api, INCIDENT_PAGE_SIZE, messageOf, thumbnailUrl, type AuditEntry, type Incident, type IncidentPage,
  type ReviewInput } from "../api/client";
import { measuredError } from "../map/data";
import { eventTitle, footageTime, reviewLabels } from "../presentation";

function ReviewStatus({ incident }: { incident: Incident }) {
  return <span className={`chip ${incident.review_status === "pending" ? "tone-amber" : "tone-muted"}`}>
    {reviewLabels[incident.review_status]}
  </span>;
}

function Measurements({ incident }: { incident: Incident }) {
  const details = incident.rule_details;
  const meters = measuredError(incident);
  return (
    <dl className="measurements">
      <dt>Source ID</dt><dd title={incident.source_id}>{incident.source_id}</dd>
      <dt>Run ID</dt><dd className="mono" title={incident.run_id}>{incident.run_id}</dd>
      <dt>Footage time</dt><dd className="mono">{footageTime(incident.video_time_ms)}</dd>
      <dt>Confirmation</dt><dd>{details.consecutive_frames} frames · frame {details.trigger_frame_index}</dd>
      {"zone_id" in details ? (
        <>
          <dt>Zone</dt><dd title={details.zone_id}>{details.zone_id}</dd>
          <dt>Track ID</dt><dd className="mono" title={details.track_id}>{details.track_id}</dd>
        </>
      ) : (
        <>
          <dt>Count / threshold</dt><dd>{details.person_count} / {details.threshold_count} people</dd>
          <dt>Clear count</dt><dd>{details.clear_count}</dd>
          <dt>Confidence floor</dt><dd>{details.min_detector_confidence}</dd>
        </>
      )}
      <dt>Cooldown</dt><dd>{details.cooldown_ms} ms</dd>
      {meters !== null && <><dt>Horizontal uncertainty</dt><dd>±{meters} m</dd></>}
      {incident.reviewer && <><dt>Reviewer</dt><dd>{incident.reviewer}</dd></>}
    </dl>
  );
}

function IncidentEvidence({ incident }: { incident: Incident }) {
  const url = thumbnailUrl(incident);
  const [failed, setFailed] = useState(false);
  if (!url || failed) return <p className="muted evidence-message">Evidence thumbnail unavailable.</p>;
  return <img className="evidence" alt="Annotated incident confirmation frame" crossOrigin="anonymous" src={url}
    onError={() => setFailed(true)} />;
}

export function IncidentPane({ page, offset, onPage, selected, onSelect, onReview, unavailable, loading, canWrite }: {
  page?: IncidentPage; offset: number; onPage: (offset: number) => void; selected: Incident | null;
  onSelect: (id: string) => void; onReview: (decision: ReviewInput["decision"]) => void;
  unavailable: boolean; loading: boolean; canWrite: boolean;
}) {
  const items = page?.items ?? [];
  const total = page?.total;
  return (
    <section className="panel incidents-panel" aria-labelledby="incidents-heading">
      <header className="panel-header">
        <h2 id="incidents-heading">Incident queue</h2>
        {total !== undefined && !unavailable && <span className="count" aria-label={`${total} incidents`}>{total}</span>}
      </header>
      <div className="panel-scroll">
        <p className="queue-note"><span aria-hidden="true">◇</span> Candidates require human review</p>
        {unavailable && items.length > 0 &&
          <p className="section-note error-text" role="status">Incident queue unavailable. Showing the last loaded records.</p>}
        {items.length === 0 && (
          <div className="empty-state queue-empty" role="status">
            <span className="queue-icon" aria-hidden="true"><i /><i /><i /></span>
            <strong>{loading ? "Loading incidents" : unavailable ? "Incident queue unavailable" : "No incidents recorded"}</strong>
            {!loading && !unavailable && <p>Rule candidates appear here after they are saved.</p>}
          </div>
        )}
        {items.length > 0 && (
          <ul className="incident-list" aria-label="Recorded incidents">
            {items.map((item) => (
              <li key={item.id}>
                <button type="button" className="incident-select" aria-pressed={item.id === selected?.id}
                  onClick={() => onSelect(item.id)}>
                  <span><strong>{eventTitle(item)}</strong><small className="mono">{footageTime(item.video_time_ms)}</small></span>
                  <ReviewStatus incident={item} />
                </button>
              </li>
            ))}
          </ul>
        )}
        {(offset > 0 || (total ?? 0) > INCIDENT_PAGE_SIZE) && (
          <div className="queue-pagination">
            <button type="button" className="subtle" disabled={offset === 0 || loading || unavailable}
              onClick={() => onPage(Math.max(0, offset - INCIDENT_PAGE_SIZE))}>Previous</button>
            <button type="button" className="subtle" disabled={offset + INCIDENT_PAGE_SIZE >= (total ?? 0) || loading || unavailable}
              onClick={() => onPage(offset + INCIDENT_PAGE_SIZE)}>Next</button>
          </div>
        )}
        {selected && (
          <article className="incident-details" aria-label="Selected incident">
            <div className="detail-heading"><h3>Selected incident</h3><span className="tone-amber">Review severity</span></div>
            <Measurements incident={selected} />
            <IncidentEvidence key={selected.id} incident={selected} />
          </article>
        )}
      </div>
      {selected?.review_status === "pending" && (
        <footer className="review-actions" aria-label="Review selected incident">
          <button type="button" className="subtle" disabled={!canWrite} onClick={() => onReview("dismissed")}>Dismiss</button>
          <button type="button" className="primary" disabled={!canWrite} onClick={() => onReview("acknowledged")}>Acknowledge</button>
        </footer>
      )}
    </section>
  );
}

const auditLabels: Record<AuditEntry["action"], string> = {
  created: "Candidate created", acknowledged: "Acknowledged", dismissed: "Dismissed",
};

export function AuditPane({ incident, revision }: { incident: Incident | null; revision: unknown }) {
  const id = incident?.id;
  const [data, setData] = useState<{ id: string; entries: AuditEntry[]; error?: string }>();
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    void api.audit(id, controller.signal).then((result) => {
      if (!controller.signal.aborted) setData({ id, entries: result.items });
    }).catch((error) => {
      if (!controller.signal.aborted) setData({ id, entries: [], error: messageOf(error) });
    });
    return () => controller.abort();
  }, [id, revision]);
  const current = id && data?.id === id ? data : undefined;
  return (
    <section className="panel audit-panel" aria-labelledby="audit-heading">
      <header className="panel-header">
        <h2 id="audit-heading">Audit timeline</h2>
        <span className="panel-metric">Processing FPS <strong className="mono">N/A</strong></span>
      </header>
      {current?.entries.length ? (
        <ol className="audit-list">
          {current.entries.map((entry) => (
            <li key={entry.id}>
              <span className="audit-action">{auditLabels[entry.action]}</span>
              <span className="muted">{entry.actor}</span>
              {entry.reason && <span className="audit-reason">{entry.reason}</span>}
              <time className="mono" dateTime={entry.created_at}>{entry.created_at.replace("T", " ").replace(/\.\d+Z$/, "Z")}</time>
            </li>
          ))}
        </ol>
      ) : <p className={`section-note ${current?.error ? "error-text" : "muted"}`} role="status">
        {current?.error ? `Audit unavailable · ${current.error}` :
          id ? current ? "No audit entries recorded." : "Loading audit timeline…" : "Select an incident to view its review history."}
      </p>}
    </section>
  );
}

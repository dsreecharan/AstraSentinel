import { useEffect, useId, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { messageOf, type ReviewInput } from "../api/client";

function Dialog({ title, busy = false, onClose, children }: {
  title: string; busy?: boolean; onClose: () => void; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return (
    <dialog
      ref={ref} className="modal" aria-labelledby={titleId}
      onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}
    >
      <h2 id={titleId}>{title}</h2>
      {children}
    </dialog>
  );
}

export function AccessDialog({ hasToken, onSave, onClose }: {
  hasToken: boolean; onSave: (token: string) => void; onClose: () => void;
}) {
  const [value, setValue] = useState("");
  function submit(event: FormEvent) {
    event.preventDefault();
    if (value.trim()) onSave(value.trim());
  }
  return (
    <Dialog title="Operator access" onClose={onClose}>
      <p className="muted">Enter the local operator token to control replay and submit reviews. Access resets on page reload.</p>
      <form onSubmit={submit}>
        <label htmlFor="operator-token">Operator token</label>
        <input
          id="operator-token" type="password" autoComplete="off" spellCheck={false} autoFocus
          value={value} onChange={(event) => setValue(event.target.value)} required
        />
        <div className="modal-actions">
          {hasToken && <button type="button" className="subtle" onClick={() => onSave("")}>Clear access</button>}
          <button type="button" className="subtle" onClick={onClose}>Cancel</button>
          <button type="submit" className="primary" disabled={!value.trim()}>Use token</button>
        </div>
      </form>
    </Dialog>
  );
}

export function ReviewDialog({ decision, onSubmit, onClose }: {
  decision: ReviewInput["decision"]; onSubmit: (body: ReviewInput) => Promise<void>; onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const label = decision === "acknowledged" ? "Acknowledge" : "Dismiss";
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      await onSubmit({ decision, reason: reason.trim() });
    } catch (issue) {
      setError(messageOf(issue));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title={`${label} incident`} busy={busy} onClose={onClose}>
      <p className="muted">Your decision and reason will be recorded in the audit timeline.</p>
      <form onSubmit={(event) => { void submit(event); }}>
        <label htmlFor="review-reason">Review reason</label>
        <textarea id="review-reason" autoFocus rows={4} maxLength={500} required
          value={reason} onChange={(event) => setReason(event.target.value)} />
        {error && <p className="error-text" role="alert">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="subtle" disabled={busy} onClick={onClose}>Cancel</button>
          <button type="submit" className="primary" disabled={busy || !reason.trim()}>{busy ? "Saving…" : label}</button>
        </div>
      </form>
    </Dialog>
  );
}

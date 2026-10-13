import { useEffect, useState } from "react";

import { api, type AuditEventInfo } from "../api";
import { downloadCsv, usd, when } from "../format";

const KIND_TEXT: Record<string, string> = {
  upload: "Uploaded",
  upload_rejected: "Upload rejected",
  extraction_done: "Text extracted",
  extraction_failed: "Extraction failed",
  reextract_started: "Re-extracting (newer extractor)",
  run_started: "Run started",
  run_finished: "Run finished",
  run_failed: "Run failed",
  run_stopped_cost_cap: "Run stopped at cost cap",
  run_blocked_cost_cap: "Run refused: estimate over cost cap",
};

function summary(e: AuditEventInfo): string {
  const d = e.details as Record<string, string | number | null | undefined>;
  switch (e.kind) {
    case "upload":
      return `${d.filename} · ${d.pages} pages · ${Math.round(Number(d.size_bytes) / 1024)} KB`;
    case "upload_rejected":
      return `${d.filename}: ${d.reason}`;
    case "extraction_done":
      return `${d.lines} lines · ${d.chars} chars · extractor v${d.extractor_version} · ${d.seconds}s`;
    case "run_started":
      return `${d.strategy} · ${d.model} · est. ${usd(Number(d.estimate_usd))}`;
    case "run_finished":
      return `${d.strategy} · ${d.sections} sections · ${usd(d.cost_usd as number | null)} · ${d.calls} calls`;
    case "run_failed":
    case "run_stopped_cost_cap":
      return `${d.strategy} · ${usd(d.cost_usd as number | null)} spent · ${d.error}`;
    case "run_blocked_cost_cap":
      return `${d.strategy} · est. ${usd(Number(d.estimate_usd))} > cap ${usd(Number(d.cap_usd))}`;
    default:
      return d.error ? String(d.error) : "";
  }
}

type Props = { docId: number; refreshKey: unknown };

/** The document's audit trail, newest first. */
export default function Activity({ docId, refreshKey }: Props) {
  const [events, setEvents] = useState<AuditEventInfo[]>([]);

  useEffect(() => {
    void api<AuditEventInfo[]>(`/documents/${docId}/audit`).then(setEvents).catch(() => undefined);
  }, [docId, refreshKey]);

  return (
    <details className="activity">
      <summary>
        Activity <span className="muted small">({events.length} events)</span>
      </summary>
      <div className="row">
        <button className="ghost" disabled={!events.length} onClick={() => downloadCsv(`document-${docId}-audit.csv`, events)}>
          Export CSV
        </button>
      </div>
      <ul className="events">
        {events.map((e) => (
          <li key={e.id}>
            <span className="small muted">{when(e.created_at)}</span>
            <strong>{KIND_TEXT[e.kind] ?? e.kind}</strong>
            {e.run_id && <span className="small muted">run #{e.run_id}</span>}
            <span className="small">{summary(e)}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

import { useEffect, useState } from "react";

import { api, type LlmCallInfo, type RunInfo } from "../api";
import { downloadCsv, num, secs, usd, when } from "../format";

type Props = { run: RunInfo; onClose: () => void };

/** Every model request a run made, in order, with tokens, cost and latency. */
export default function RunCalls({ run, onClose }: Props) {
  const [calls, setCalls] = useState<LlmCallInfo[] | null>(null);
  const [error, setError] = useState("");
  const live = run.status === "queued" || run.status === "running";

  useEffect(() => {
    let alive = true;
    const load = () =>
      api<LlmCallInfo[]>(`/runs/${run.id}/calls`)
        .then((c) => alive && setCalls(c))
        .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : "Could not load calls"));
    void load();
    const t = live ? window.setInterval(load, 2000) : undefined;
    return () => {
      alive = false;
      if (t) window.clearInterval(t);
    };
  }, [run.id, live]);

  const total = (calls ?? []).reduce((a, c) => a + (c.cost_usd ?? 0), 0);
  const byStep = run.metrics?.cost_by_step;

  return (
    <div className="drawer" role="dialog" aria-label={`Model calls for run ${run.id}`}>
      <div className="drawer-head">
        <h3>Run #{run.id} · model calls</h3>
        <div className="row">
          <button
            className="ghost"
            disabled={!calls?.length}
            onClick={() => calls && downloadCsv(`run-${run.id}-calls.csv`, calls)}
          >
            Export CSV
          </button>
          <button className="ghost" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
      </div>
      <p className="muted small">
        Estimated {usd(run.estimate?.cost_usd)} · actual {usd(total)} over {calls?.length ?? 0} request
        {calls?.length === 1 ? "" : "s"}. Prompts are logged as a SHA-256 fingerprint and length, not their text.
      </p>
      {byStep && Object.keys(byStep).length > 1 && (
        <p className="muted small">
          By step: {Object.entries(byStep).map(([k, v]) => `${k} ${usd(v)}`).join(" · ")}
        </p>
      )}
      {error && <p className="error">{error}</p>}
      {calls && calls.length === 0 && (
        <p className="muted">No calls logged. Runs made before the call log existed have totals only.</p>
      )}
      {calls && calls.length > 0 && (
        <div className="runs-wrap">
          <table className="runs">
            <thead>
              <tr>
                <th>#</th>
                <th>Step</th>
                <th>Try</th>
                <th>Status</th>
                <th>Effort</th>
                <th className="n">In</th>
                <th className="n">Cached</th>
                <th className="n">Out</th>
                <th className="n">Reasoning</th>
                <th className="n">Cost</th>
                <th className="n">Latency</th>
                <th>Prompt</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {calls.map((c) => (
                <tr key={c.id} title={c.error ?? undefined}>
                  <td>{c.seq}</td>
                  <td>{c.step}</td>
                  <td>{c.attempt}</td>
                  <td className={c.status === "ok" ? "" : "err"}>{c.status}</td>
                  <td>{c.reasoning_effort ?? "—"}</td>
                  <td className="n">{num(c.input_tokens)}</td>
                  <td className="n">{num(c.cached_tokens)}</td>
                  <td className="n">{num(c.output_tokens)}</td>
                  <td className="n">{num(c.reasoning_tokens)}</td>
                  <td className="n strong">{usd(c.cost_usd)}</td>
                  <td className="n">{secs(c.latency_ms / 1000)}</td>
                  <td className="mono small" title={c.prompt_sha256}>
                    {c.prompt_sha256.slice(0, 10)}… · {num(c.prompt_chars)} chars
                    {c.images ? ` · ${c.images} img` : ""}
                  </td>
                  <td className="small">{when(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

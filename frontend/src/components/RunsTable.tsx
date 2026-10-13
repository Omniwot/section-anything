import type { Catalog, RunInfo } from "../api";
import { num, pct, secs, usd } from "../format";

type Props = {
  runs: RunInfo[];
  catalog: Catalog;
  selectedId: number | null;
  hasGold: boolean;
  onSelect: (r: RunInfo) => void;
  onCalls: (r: RunInfo) => void;
};

/** Every run on this document side by side: what each strategy cost and how it did. */
export default function RunsTable({ runs, catalog, selectedId, hasGold, onSelect, onCalls }: Props) {
  if (!runs.length) return null;
  const strategy = (id: string) => catalog.strategies.find((s) => s.id === id);
  const metricCols = hasGold ? 7 : 5;
  return (
    <div className="runs-wrap">
      <table className="runs">
        <thead>
          <tr>
            <th>Run</th>
            <th>Strategy</th>
            <th>Model</th>
            <th className="n" title="Estimated before the run started">Est. cost</th>
            <th className="n" title="Actual cost from the model's reported token usage">Cost</th>
            <th className="n" title="Model requests, including retries">Calls</th>
            <th className="n">Time</th>
            <th className="n">Sections</th>
            {hasGold && <th className="n" title="Heading F1 against the golden annotation">F1</th>}
            {hasGold && <th className="n" title="Relative heading depth agreement with gold">Levels</th>}
            <th className="n" title="Start markers found verbatim in the text">Exact starts</th>
            <th className="n" title="End markers consistent with computed boundaries">Ends agree</th>
            <th className="n">Flagged</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const m = r.metrics;
            const usesLlm = strategy(r.strategy)?.uses_llm ?? true;
            const live = r.status === "queued" || r.status === "running";
            const cost = live ? r.progress?.cost_usd : m?.cost_usd;
            const calls = live ? r.progress?.calls : m?.calls;
            return (
              <tr
                key={r.id}
                className={r.id === selectedId ? "sel" : ""}
                onClick={() => r.status === "done" && onSelect(r)}
                aria-disabled={r.status !== "done"}
              >
                <td>
                  #{r.id}
                  {r.stale && (
                    <span className="badge warn" title="Made with an older extraction; highlights may be misplaced">
                      old
                    </span>
                  )}
                </td>
                <td>{strategy(r.strategy)?.label ?? r.strategy}</td>
                <td>{usesLlm ? r.model : "—"}</td>
                <td className="n muted">{usesLlm ? usd(r.estimate?.cost_usd) : "$0"}</td>
                <td className="n strong">{usesLlm ? usd(cost) : "$0"}</td>
                <td className="n">{usesLlm ? num(calls) : "0"}</td>
                <td className="n">{secs(m?.seconds)}</td>
                {r.status === "done" && m ? (
                  <>
                    <td className="n">{num(m.sections)}</td>
                    {hasGold && <td className="n strong">{r.accuracy ? r.accuracy.f1.toFixed(2) : "—"}</td>}
                    {hasGold && <td className="n">{r.accuracy?.level_agreement != null ? r.accuracy.level_agreement.toFixed(2) : "—"}</td>}
                    <td className="n">{pct(m.start_marker_exact)}</td>
                    <td className="n">{pct(m.end_agreement)}</td>
                    <td className="n">{num(m.flagged)}</td>
                  </>
                ) : (
                  <td colSpan={metricCols + 1} className={r.status === "failed" ? "err" : "muted"}>
                    {r.status === "failed"
                      ? r.error
                      : r.progress
                        ? `${Math.round(r.progress.fraction * 100)}% · ${r.progress.message}`
                        : r.status}
                  </td>
                )}
                <td>
                  {usesLlm && (
                    <button
                      className="link"
                      onClick={(e) => {
                        e.stopPropagation();
                        onCalls(r);
                      }}
                    >
                      Calls
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

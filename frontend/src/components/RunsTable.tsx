import type { Catalog, RunInfo } from "../api";
import { num, pct, secs, usd } from "../format";

type Props = {
  runs: RunInfo[];
  catalog: Catalog;
  selectedId: number | null;
  hasGold: boolean;
  onSelect: (r: RunInfo) => void;
};

/** Every run on this document side by side: what each strategy cost and how it did. */
export default function RunsTable({ runs, catalog, selectedId, hasGold, onSelect }: Props) {
  if (!runs.length) return null;
  const label = (id: string) => catalog.strategies.find((s) => s.id === id)?.label ?? id;
  return (
    <div className="runs-wrap">
      <table className="runs">
        <thead>
          <tr>
            <th>Run</th>
            <th>Strategy</th>
            <th>Model</th>
            <th className="n">Sections</th>
            <th className="n">Cost</th>
            <th className="n">Time</th>
            {hasGold && <th className="n" title="Heading F1 against the golden annotation">F1</th>}
            {hasGold && <th className="n" title="Relative heading depth agreement with gold">Levels</th>}
            <th className="n" title="Start markers found verbatim in the text">Exact starts</th>
            <th className="n" title="End markers consistent with computed boundaries">Ends agree</th>
            <th className="n">Flagged</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const m = r.metrics;
            return (
              <tr
                key={r.id}
                className={r.id === selectedId ? "sel" : ""}
                onClick={() => r.status === "done" && onSelect(r)}
                aria-disabled={r.status !== "done"}
              >
                <td>#{r.id}</td>
                <td>{label(r.strategy)}</td>
                <td>{catalog.strategies.find((s) => s.id === r.strategy)?.uses_llm ? r.model : "—"}</td>
                {r.status === "done" && m ? (
                  <>
                    <td className="n">{num(m.sections)}</td>
                    <td className="n">{usd(m.cost_usd)}</td>
                    <td className="n">{secs(m.seconds)}</td>
                    {hasGold && <td className="n strong">{r.accuracy ? r.accuracy.f1.toFixed(2) : "—"}</td>}
                    {hasGold && <td className="n">{r.accuracy?.level_agreement != null ? r.accuracy.level_agreement.toFixed(2) : "—"}</td>}
                    <td className="n">{pct(m.start_marker_exact)}</td>
                    <td className="n">{pct(m.end_agreement)}</td>
                    <td className="n">{num(m.flagged)}</td>
                  </>
                ) : (
                  <td colSpan={hasGold ? 8 : 6} className={r.status === "failed" ? "err" : "muted"}>
                    {r.status === "failed"
                      ? r.error
                      : r.progress
                        ? `${Math.round(r.progress.fraction * 100)}% · ${r.progress.message}`
                        : r.status}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

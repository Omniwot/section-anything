import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, type Catalog, type DocumentInfo, type Estimate, type RunInfo, type Section } from "../api";
import { usd } from "../format";
import Activity from "./Activity";
import PdfPane, { type PdfPaneHandle } from "./PdfPane";
import RunCalls from "./RunCalls";
import RunsTable from "./RunsTable";
import SectionList from "./SectionList";
import StrategyBar from "./StrategyBar";

type Props = { doc: DocumentInfo; catalog: Catalog; onBack: () => void };

export default function Workspace({ doc, catalog, onBack }: Props) {
  const [estimates, setEstimates] = useState<Estimate[]>([]);
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [current, setCurrent] = useState<RunInfo | null>(null);
  const [strategyIndex, setStrategyIndex] = useState(Math.min(2, catalog.strategies.length - 1));
  const [model, setModel] = useState(catalog.models[0] ?? "");
  const [activeId, setActiveId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [callsFor, setCallsFor] = useState<number | null>(null);
  const pane = useRef<PdfPaneHandle>(null);

  const sections: Section[] = useMemo(() => current?.sections ?? [], [current]);
  const busy = runs.some((r) => r.status === "queued" || r.status === "running");
  const spent = runs.reduce(
    (a, r) => a + ((r.status === "queued" || r.status === "running" ? r.progress?.cost_usd : r.metrics?.cost_usd) ?? 0),
    0,
  );
  const runStates = runs.map((r) => `${r.id}:${r.status}`).join(",");
  const callsRun = runs.find((r) => r.id === callsFor) ?? null;

  const loadRun = useCallback(async (id: number) => {
    const full = await api<RunInfo>(`/runs/${id}`);
    setCurrent(full);
    setActiveId(null);
  }, []);

  const refreshRuns = useCallback(async () => {
    const list = await api<RunInfo[]>(`/documents/${doc.id}/runs`);
    setRuns(list);
    return list;
  }, [doc.id]);

  useEffect(() => {
    void api<Estimate[]>(`/documents/${doc.id}/estimates`).then(setEstimates).catch(() => undefined);
    void refreshRuns().then((list) => {
      const latest = list.find((r) => r.status === "done");
      if (latest) void loadRun(latest.id);
    });
  }, [doc.id, refreshRuns, loadRun]);

  // Poll while anything is running; load a run as soon as it finishes.
  useEffect(() => {
    if (!busy) return;
    const watching = new Set(runs.filter((r) => r.status === "queued" || r.status === "running").map((r) => r.id));
    const t = window.setInterval(async () => {
      const list = await refreshRuns().catch(() => null);
      const done = list?.find((r) => watching.has(r.id) && r.status === "done");
      if (done) void loadRun(done.id);
    }, 1500);
    return () => window.clearInterval(t);
  }, [busy, runs, refreshRuns, loadRun]);

  async function onRun() {
    setError("");
    try {
      await api<RunInfo>(`/documents/${doc.id}/runs`, {
        method: "POST",
        body: JSON.stringify({ strategy: catalog.strategies[strategyIndex].id, model }),
      });
      await refreshRuns();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Run failed to start");
      await refreshRuns().catch(() => undefined);
    }
  }

  function select(s: Section, scroll: boolean) {
    setActiveId(s.id);
    if (scroll) pane.current?.scrollToSection(s);
  }

  return (
    <div className="workspace">
      <header className="ws-head">
        <button className="ghost" onClick={onBack}>
          ← Documents
        </button>
        <div className="ws-title">
          <h2>{doc.filename}</h2>
          <span className="muted small">
            {doc.n_pages} pages · {(doc.n_chars ?? 0).toLocaleString()} characters
            {doc.pages_without_text ? ` · ${doc.pages_without_text} pages without a text layer` : ""}
            {doc.has_gold ? " · in golden corpus: runs are scored for accuracy" : ""}
          </span>
        </div>
        <div className="ws-spent" title="Total model cost of every run on this document">
          <span className="eyebrow">Spent on this document</span>
          <strong>{usd(spent)}</strong>
        </div>
      </header>

      <StrategyBar
        catalog={catalog}
        estimates={estimates}
        strategyIndex={strategyIndex}
        model={model}
        busy={busy}
        onStrategy={setStrategyIndex}
        onModel={setModel}
        onRun={onRun}
      />
      {error && <p className="error">{error}</p>}
      <RunsTable
        runs={runs}
        catalog={catalog}
        selectedId={current?.id ?? null}
        hasGold={doc.has_gold}
        onSelect={(r) => void loadRun(r.id)}
        onCalls={(r) => setCallsFor(r.id)}
      />
      {callsRun && <RunCalls run={callsRun} onClose={() => setCallsFor(null)} />}
      <Activity docId={doc.id} refreshKey={runStates} />

      <div className="split">
        <section className="left" aria-label="Document">
          <PdfPane
            docId={doc.id}
            sections={sections}
            activeId={activeId}
            onSelect={(id) => {
              const s = sections.find((x) => x.id === id);
              if (s) select(s, false);
            }}
            handleRef={pane}
          />
        </section>
        <aside className="right" aria-label="Sections">
          <div className="right-head">
            <h3>Sections</h3>
            {current && (
              <span className="muted small">
                Run #{current.id} · {catalog.strategies.find((s) => s.id === current.strategy)?.label}
              </span>
            )}
          </div>
          <SectionList sections={sections} activeId={activeId} onSelect={(s) => select(s, true)} />
        </aside>
      </div>
    </div>
  );
}

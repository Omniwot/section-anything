import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, bridgeNext, bridgeReply, type Catalog, type DocumentInfo, type Estimate, type RunInfo, type Section } from "../api";
import { usd } from "../format";
import { complete, loadConfig, LOCAL_CHOICE, type LocalConfig } from "../localLlm";
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
  const defaultModel = (i: number) => {
    const st = catalog.strategies[i];
    if (!st?.uses_llm) return catalog.models[0] ?? "";
    const preferred = st.default_model ?? catalog.models[0];
    if (preferred && catalog.models.includes(preferred)) return preferred;
    return catalog.local_models.strategies.includes(st.id) ? LOCAL_CHOICE : "";
  };
  const [localConfig, setLocalConfig] = useState<LocalConfig>(() => loadConfig());
  const localRef = useRef(localConfig);
  localRef.current = localConfig;
  const [answered, setAnswered] = useState<Record<number, number>>({});
  const [localError, setLocalError] = useState("");
  const [model, setModel] = useState(() => defaultModel(Math.min(2, catalog.strategies.length - 1)));
  const chooseStrategy = (i: number) => {
    setStrategyIndex(i);
    setModel(defaultModel(i)); // each stop has its own default model; the dropdown can still override it
  };
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

  // Runs on the visitor's own model: answer each prompt the server queues, from this tab.
  const serving = useRef(new Set<number>());
  const localRuns = runs.filter(
    (r) => (r.status === "queued" || r.status === "running") && r.model.startsWith(catalog.local_models.prefix),
  );
  const localRunIds = localRuns.map((r) => r.id).join(",");
  useEffect(() => {
    const stop = new AbortController();
    for (const r of localRuns) {
      if (serving.current.has(r.id)) continue;
      serving.current.add(r.id);
      void (async () => {
        try {
          while (!stop.signal.aborted) {
            const next = await bridgeNext(r.id, stop.signal);
            if (!next.request) {
              if (next.status === "done" || next.status === "failed") break;
              continue;
            }
            try {
              const content = await complete(localRef.current, next.request, stop.signal);
              await bridgeReply(r.id, next.request.id, { content });
              setLocalError("");
              setAnswered((a) => ({ ...a, [r.id]: (a[r.id] ?? 0) + 1 }));
            } catch (e) {
              if (stop.signal.aborted) break;
              const msg = e instanceof Error ? e.message : "local model failed";
              setLocalError(msg);
              await bridgeReply(r.id, next.request.id, { error: msg }).catch(() => undefined);
            }
          }
        } catch {
          /* page closed or signed out: the run times out on the server */
        } finally {
          serving.current.delete(r.id);
        }
      })();
    }
    return () => stop.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localRunIds]);

  async function onRun() {
    setError("");
    const st = catalog.strategies[strategyIndex];
    const modelId =
      model === LOCAL_CHOICE
        ? st.uses_llm
          ? `${catalog.local_models.prefix}${localConfig.model}`
          : ""
        : model;
    try {
      await api<RunInfo>(`/documents/${doc.id}/runs`, {
        method: "POST",
        body: JSON.stringify({ strategy: st.id, model: modelId }),
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
        onStrategy={chooseStrategy}
        onModel={setModel}
        onRun={onRun}
        localConfig={localConfig}
        onLocalConfig={setLocalConfig}
      />
      {error && <p className="error">{error}</p>}
      {localRuns.length > 0 && (
        <p className="local-status small">
          Your local model is working
          {localRuns.map((r) => ` · run #${r.id}: ${answered[r.id] ?? 0} prompt${(answered[r.id] ?? 0) === 1 ? "" : "s"} answered`)}.
          Keep this tab open until it finishes.
        </p>
      )}
      {localError && <p className="error small">{localError}</p>}
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

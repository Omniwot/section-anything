import type { Catalog, Estimate } from "../api";
import { usd } from "../format";
import { LOCAL_CHOICE, type LocalConfig } from "../localLlm";
import LocalModelPanel from "./LocalModelPanel";

type Props = {
  catalog: Catalog;
  estimates: Estimate[];
  strategyIndex: number;
  model: string;
  busy: boolean;
  onStrategy: (i: number) => void;
  onModel: (m: string) => void;
  onRun: () => void;
  localConfig: LocalConfig;
  onLocalConfig: (c: LocalConfig) => void;
};

/** Slider over strategies ordered cheapest → most thorough, with a cost estimate. */
export default function StrategyBar({
  catalog,
  estimates,
  strategyIndex,
  model,
  busy,
  onStrategy,
  onModel,
  onRun,
  localConfig,
  onLocalConfig,
}: Props) {
  const s = catalog.strategies[strategyIndex];
  const est = estimates.find((e) => e.strategy === s.id);
  const localOk = s.uses_llm && catalog.local_models.strategies.includes(s.id);
  const local = s.uses_llm && model === LOCAL_CHOICE;
  const cost = est && !local ? est.cost_usd[model] : undefined;
  const blocked = s.uses_llm && !local && !!est?.blocked[model];
  const noModel = (local && !localConfig.model) || (s.uses_llm && !local && !catalog.models.includes(model));
  const label = busy ? "Running…" : local ? "Run · free on your machine" : `Run${s.uses_llm && cost !== undefined ? ` · ≈ ${usd(cost)}` : " · free"}`;

  return (
    <div className="strategy-bar">
      <div className="slider-block">
        <label htmlFor="strategy" className="eyebrow">
          Strategy
        </label>
        <input
          id="strategy"
          type="range"
          min={0}
          max={catalog.strategies.length - 1}
          step={1}
          value={strategyIndex}
          onChange={(e) => onStrategy(Number(e.target.value))}
          list="strategy-stops"
          aria-valuetext={s.label}
        />
        <div className="stops" style={{ gridTemplateColumns: `repeat(${catalog.strategies.length}, 1fr)` }}>
          {catalog.strategies.map((st, i) => (
            <button key={st.id} className={i === strategyIndex ? "on" : ""} onClick={() => onStrategy(i)}>
              {st.label}
            </button>
          ))}
        </div>
        <div className="stop-ends">
          <span>Cheaper, faster</span>
          <span>More thorough</span>
        </div>
      </div>
      <div className="run-block">
        <p className="strategy-desc">{s.description}</p>
        <div className="run-row">
          <select value={model} onChange={(e) => onModel(e.target.value)} disabled={!s.uses_llm} aria-label="Model">
            {catalog.models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
            {localOk && <option value={LOCAL_CHOICE}>Your local model…</option>}
          </select>
          <button className="primary" onClick={onRun} disabled={busy || blocked || noModel}>
            {label}
          </button>
        </div>
        {blocked && (
          <p className="error small">
            Estimated {usd(cost)} is over the {usd(catalog.limits.run_cost_cap_usd)} per-run cap, so this run is unavailable. Pick a
            cheaper strategy or model, or raise RUN_COST_CAP_USD.
          </p>
        )}
        {local && <LocalModelPanel config={localConfig} onChange={onLocalConfig} />}
        {s.uses_llm && !local && !catalog.paid_models && (
          <p className="muted small">Paid models are not enabled for this account. Use Free, or your own local model.</p>
        )}
        {s.uses_llm && !local && est && !blocked && (
          <p className="muted small">
            Estimate: {est.calls} call{est.calls === 1 ? "" : "s"}, ~{Math.round(est.input_tokens / 1000)}k tokens in. Runs stop at{" "}
            {usd(catalog.limits.run_cost_cap_usd)}.
          </p>
        )}
      </div>
    </div>
  );
}

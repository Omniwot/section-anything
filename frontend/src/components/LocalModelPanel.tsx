import { useState } from "react";

import { DEFAULTS, type LocalConfig, type LocalKind, listModels, saveConfig } from "../localLlm";

type Props = { config: LocalConfig; onChange: (c: LocalConfig) => void };

/** Connect to the visitor's own model (Ollama or an OpenAI-compatible local server). */
export default function LocalModelPanel({ config, onChange }: Props) {
  const [models, setModels] = useState<string[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const origin = window.location.origin;

  const update = (patch: Partial<LocalConfig>) => {
    const next = { ...config, ...patch };
    saveConfig(next);
    onChange(next);
  };

  async function test() {
    setError("");
    setStatus("Connecting…");
    try {
      const found = await listModels(config);
      setModels(found);
      setStatus(found.length ? `Connected: ${found.length} model${found.length === 1 ? "" : "s"} found.` : "Connected, but no models are installed.");
      if (found.length && !found.includes(config.model)) update({ model: found[0] });
    } catch (e) {
      setStatus("");
      setError(e instanceof Error ? e.message : "Could not connect");
    }
  }

  return (
    <div className="local-panel">
      <div className="local-row">
        <label>
          <span className="eyebrow">Runs on</span>
          <select
            value={config.kind}
            onChange={(e) => {
              const kind = e.target.value as LocalKind;
              update({ kind, baseUrl: DEFAULTS[kind], model: "" });
              setModels([]);
            }}
          >
            <option value="ollama">Ollama</option>
            <option value="openai">OpenAI-compatible (LM Studio, llama.cpp server)</option>
          </select>
        </label>
        <label className="grow">
          <span className="eyebrow">Address</span>
          <input value={config.baseUrl} onChange={(e) => update({ baseUrl: e.target.value })} spellCheck={false} />
        </label>
        <button type="button" onClick={test}>
          Test connection
        </button>
      </div>
      <div className="local-row">
        <label className="grow">
          <span className="eyebrow">Model</span>
          {models.length ? (
            <select value={config.model} onChange={(e) => update({ model: e.target.value })}>
              {models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          ) : (
            <input
              value={config.model}
              placeholder="e.g. qwen3:4b (or press Test connection)"
              onChange={(e) => update({ model: e.target.value.trim() })}
              spellCheck={false}
            />
          )}
        </label>
        {config.kind === "ollama" && (
          <label>
            <span className="eyebrow">Context (tokens)</span>
            <select value={config.contextTokens} onChange={(e) => update({ contextTokens: Number(e.target.value) })}>
              {[8192, 16384, 32768].map((n) => (
                <option key={n} value={n}>
                  {n.toLocaleString()}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {status && <p className="muted small">{status}</p>}
      {error && <p className="error small">{error}</p>}
      <details className="small">
        <summary>Set up</summary>
        {config.kind === "ollama" ? (
          <ol>
            <li>
              Install Ollama and a model, for example <code>ollama pull qwen3:4b</code>.
            </li>
            <li>
              Allow this site to call it: quit Ollama, then start it with <code>OLLAMA_ORIGINS="{origin}" ollama serve</code>.
            </li>
            <li>If your browser asks to let this site reach devices on your local network, allow it.</li>
          </ol>
        ) : (
          <ol>
            <li>Start the local server in your app (LM Studio: Developer → Start server) and load a model.</li>
            <li>Turn on CORS in the server settings so this site can call it.</li>
            <li>If your browser asks to let this site reach devices on your local network, allow it.</li>
          </ol>
        )}
        <p className="muted">
          Your PDF is uploaded to this site so its text can be read. Prompts go from this browser to your model and the replies come
          back here; nothing is sent to a paid model provider. Quick check suits small local models best. Keep this tab open while a
          run is going.
        </p>
      </details>
    </div>
  );
}

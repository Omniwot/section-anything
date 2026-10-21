/** The visitor's own model (Ollama or any OpenAI-compatible local server such as LM Studio),
 * called directly from this browser. Prompts come from the server through the run's bridge;
 * replies go back to it. Nothing here talks to a paid provider. */

export type LocalKind = "ollama" | "openai";
export type LocalConfig = { kind: LocalKind; baseUrl: string; model: string; contextTokens: number };
export type BridgeRequest = {
  id: string;
  model: string;
  system: string;
  user: string;
  schema: Record<string, unknown>;
  max_output_tokens: number;
};

const KEY = "section-anything_local_llm";
export const LOCAL_CHOICE = "__local__";
export const DEFAULTS: Record<LocalKind, string> = { ollama: "http://localhost:11434", openai: "http://localhost:1234" };

export function loadConfig(): LocalConfig {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { kind: "ollama", baseUrl: DEFAULTS.ollama, model: "", contextTokens: 16384, ...JSON.parse(raw) };
  } catch {
    /* storage unavailable */
  }
  return { kind: "ollama", baseUrl: DEFAULTS.ollama, model: "", contextTokens: 16384 };
}

export function saveConfig(cfg: LocalConfig) {
  try {
    localStorage.setItem(KEY, JSON.stringify(cfg));
  } catch {
    /* storage unavailable: settings last for this visit */
  }
}

function base(cfg: LocalConfig) {
  return cfg.baseUrl.replace(/\/+$/, "");
}

function unreachable(cfg: LocalConfig, err: unknown): Error {
  const why = err instanceof Error ? err.message : String(err);
  return new Error(
    `Could not reach your model at ${cfg.baseUrl} (${why}). Is it running, and does it allow this site? See "Set up" below.`,
  );
}

export async function listModels(cfg: LocalConfig): Promise<string[]> {
  try {
    if (cfg.kind === "ollama") {
      const res = await fetch(`${base(cfg)}/api/tags`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as { models?: { name: string }[] };
      return (data.models ?? []).map((m) => m.name);
    }
    const res = await fetch(`${base(cfg)}/v1/models`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = (await res.json()) as { data?: { id: string }[] };
    return (data.data ?? []).map((m) => m.id);
  } catch (e) {
    throw unreachable(cfg, e);
  }
}

/** One structured completion on the local model; returns the raw reply text (JSON). */
export async function complete(cfg: LocalConfig, req: BridgeRequest, signal?: AbortSignal): Promise<string> {
  const messages = [
    { role: "system", content: req.system },
    { role: "user", content: req.user },
  ];
  const maxOut = Math.min(req.max_output_tokens, 8192);
  let res: Response;
  try {
    if (cfg.kind === "ollama") {
      // Native API: `format` takes the JSON schema; `num_ctx` keeps long prompts from being cut short.
      res = await fetch(`${base(cfg)}/api/chat`, {
        method: "POST",
        signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: req.model,
          messages,
          stream: false,
          think: false,
          format: req.schema,
          options: { temperature: 0, num_ctx: cfg.contextTokens, num_predict: maxOut },
        }),
      });
    } else {
      res = await fetch(`${base(cfg)}/v1/chat/completions`, {
        method: "POST",
        signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: req.model,
          messages,
          temperature: 0,
          max_tokens: maxOut,
          response_format: { type: "json_schema", json_schema: { name: "result", schema: req.schema, strict: false } },
        }),
      });
    }
  } catch (e) {
    if (signal?.aborted) throw e;
    throw unreachable(cfg, e);
  }
  if (!res.ok) throw new Error(`Your model returned HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`);
  const data = (await res.json()) as {
    message?: { content?: string };
    choices?: { message?: { content?: string } }[];
  };
  return cfg.kind === "ollama" ? data.message?.content ?? "" : data.choices?.[0]?.message?.content ?? "";
}
